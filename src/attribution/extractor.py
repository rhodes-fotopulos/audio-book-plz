"""Character extraction pass — chapters to per-chapter character lists.

Processes each chapter from segments.json through Qwen3 8B to extract
character profiles. Uses caching to skip chapters on re-runs (ATTR-06)
and splits oversized chapters to fit the 32K context window (ATTR-05).

Requirements covered: ATTR-01, ATTR-05, ATTR-06
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import CONTEXT_WINDOW, TruncationError, call_llm_structured, estimate_tokens, get_max_workers
from src.attribution.models import CharacterProfile, ChapterExtractionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TOKENS = 500
"""Budget for system message overhead in tokens."""

RESPONSE_BUDGET = 16384
"""Maximum tokens reserved for LLM response."""

AVAILABLE_FOR_CONTENT = CONTEXT_WINDOW - SYSTEM_PROMPT_TOKENS - RESPONSE_BUDGET
"""Tokens available for chapter text (~28,172)."""

MAX_CONTENT_CHARS = AVAILABLE_FOR_CONTENT * 4
"""Character limit for chapter text (~112,688 chars at 1:4 ratio)."""

MIN_CHUNK_CHARS = 1000
"""Minimum chunk size to avoid trivially small LLM requests."""

EXTRACTION_SYSTEM_PROMPT = """\
You are a character extraction specialist for audiobook production. \
Extract ONLY characters who SPEAK dialogue from the provided chapter text.

For each character found:
- name: The character's most commonly used name in this chapter
- aliases: Other names, titles, or forms of address used FOR THIS SAME PERSON \
(e.g. "Mr. Darcy" / "Fitzwilliam" / "Darcy"). Do NOT include names of other \
characters they speak to, write to, or mention. Letter salutations like \
"Dearest Jane" belong to Jane, not to the letter's author.
- gender: male, female, non-binary, or unknown
- age_range: child, young adult, middle-aged, elderly, or unknown
- voice_profile: Unified voice description with 9 fields:
  - pitch: Vocal pitch ("high", "medium", "low", or "unknown")
  - pace: Speech pace ("fast", "moderate", "slow", or "unknown")
  - tone: Vocal tone (e.g. "warm", "gruff", "silky", "monotone", or "unknown")
  - accent: Accent if mentioned (e.g. "British", "Southern American", or "unknown")
  - pace_style: Nuanced speaking style (e.g. "measured", "rapid", "clipped", or "unknown")
  - tone_style: Nuanced vocal quality (e.g. "gravelly", "melodic", "breathy", or "unknown")
  - energy: Energy level (e.g. "restrained", "animated", or "unknown")
  - typical_emotion: Default emotional register (e.g. "sardonic", "cheerful", or "unknown")
  - description: One-sentence voice summary
- personality_traits: Key personality characteristics shown in this chapter
- description: One-sentence character summary
- is_named: true if character has a proper name, false if referred to by \
description only (e.g. "the bartender")

WRONG examples (DO NOT do this):
- Mrs. Bennet with aliases=["Elizabeth", "Jane", "Lydia"]
  (These are her DAUGHTERS, not aliases for Mrs. Bennet)
- Mr. Darcy with aliases=["Miss Darcy", "Georgiana"]
  (Miss Darcy/Georgiana is his SISTER, a separate character)
- Elizabeth with aliases=["Mrs. Bennet"]
  (Mrs. Bennet is Elizabeth's MOTHER, not an alias)
- "the doctor" with aliases=["Dr. Smith"]
  (Only merge if the text confirms they are the same person)
- Letter recipients: "Dear Jane" in a letter FROM Elizabeth does NOT make \
Jane an alias of Elizabeth

RIGHT examples:
- Elizabeth Bennet with aliases=["Lizzy", "Eliza", "Miss Bennet"]
  (These are all names for the same person)
- Mr. Darcy with aliases=["Fitzwilliam Darcy", "Darcy"]
  (These are all names for the same person)
- Mrs. Bennet with aliases=[] (no aliases -- other Bennets are separate characters)

Rules:
- Extract ONLY characters who have dialogue lines marked with [DIALOGUE]. \
Do NOT extract characters who are merely mentioned, described, or written \
about but never speak.
- Characters referenced only in narration or spoken about by others but who \
never speak themselves in this chapter should NOT be included.
- For unnamed speakers (e.g. "the old man", "a soldier"), create profiles \
with is_named=false
- Infer voice_profile from context: "the old man grumbled" implies elderly \
male, low pitch, slow pace, gruff tone
- When unsure about a trait, use "unknown" — do not guess without textual evidence
- CRITICAL: A character's aliases must only be names for THAT SAME PERSON. \
Never list another character's name as an alias. If character A writes a letter \
to character B, "B" is NOT an alias of A.
- Do NOT use pronoun-based references as aliases (e.g. "his sister", "my father", \
"her master", "your friend"). These are ambiguous and could refer to multiple \
characters. Only use proper names, titles, or unique descriptors \
(e.g. "Mr. Darcy", "Miss Bingley", "the housekeeper")."""

OPINIONATED_ADDENDUM = """\

OPINIONATED MODE — Push for distinctiveness:
- NEVER use these bland descriptors: "moderate", "medium", "average", "normal", "standard", "typical", "ordinary", "neutral" (for voice traits — "neutral" is OK for accent)
- For pace: choose "fast", "slow", "rapid", "deliberate", "languid", "clipped" — NEVER "moderate"
- For pitch: choose "high" or "low" — NEVER "medium" unless truly average
- For energy: choose "restrained", "intense", "animated", "subdued" — NEVER "moderate"
- Push every trait to its distinctive extreme based on textual evidence
- When evidence is weak, make a bold literary inference rather than defaulting to bland middle-ground
- "unknown" is acceptable ONLY for accent when no accent evidence exists
- The description field should be vivid and specific, not generic"""


def get_extraction_prompt(opinionated: bool = False) -> str:
    """Return the extraction system prompt, optionally with opinionated addendum.

    Args:
        opinionated: If True, append OPINIONATED_ADDENDUM to push for
            distinctive, extreme voice profile descriptors.

    Returns:
        The system prompt string.
    """
    if opinionated:
        return EXTRACTION_SYSTEM_PROMPT + OPINIONATED_ADDENDUM
    return EXTRACTION_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_chapter_text(segments: list[dict]) -> str:
    """Concatenate segment text for a chapter with type prefixes.

    Prefixes each segment with its type in brackets to help the LLM
    distinguish dialogue from narration for better extraction.

    Args:
        segments: List of segment dicts from segments.json for one chapter.

    Returns:
        Formatted chapter text with type annotations.
    """
    lines: list[str] = []
    for seg in segments:
        seg_type = seg.get("type", "narration").upper()
        text = seg.get("text", "").strip()
        if text:
            lines.append(f"[{seg_type}] {text}")
    return "\n".join(lines)


def _split_chapter_text(chapter_text: str, max_chars: int) -> list[str]:
    """Split oversized chapter text into chunks that fit in context window.

    Prefers splitting at scene breaks (lines starting with [SCENE_BREAK]),
    falls back to paragraph boundaries (double newlines), and finally
    splits at single newlines if necessary.

    Args:
        chapter_text: Formatted chapter text from _build_chapter_text().
        max_chars: Maximum characters per chunk.

    Returns:
        List of text chunks, each within max_chars.
    """
    if len(chapter_text) <= max_chars:
        return [chapter_text]

    chunks: list[str] = []

    # Try splitting at scene breaks first
    scene_parts = chapter_text.split("[SCENE_BREAK]")
    if len(scene_parts) > 1:
        current_chunk: list[str] = []
        current_len = 0
        for i, part in enumerate(scene_parts):
            part_with_marker = f"[SCENE_BREAK]{part}" if i > 0 else part
            if current_len + len(part_with_marker) > max_chars and current_chunk:
                chunks.append("".join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(part_with_marker)
            current_len += len(part_with_marker)
        if current_chunk:
            chunks.append("".join(current_chunk))

        # Check if all chunks fit
        if all(len(c) <= max_chars for c in chunks):
            return [c for c in chunks if len(c.strip()) >= MIN_CHUNK_CHARS or len(chunks) == 1]

    # Fall back to paragraph boundaries
    chunks = []
    paragraphs = chapter_text.split("\n\n")
    current_chunk_parts: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) + 2 > max_chars and current_chunk_parts:
            chunks.append("\n\n".join(current_chunk_parts))
            current_chunk_parts = []
            current_len = 0
        current_chunk_parts.append(para)
        current_len += len(para) + 2

    if current_chunk_parts:
        chunks.append("\n\n".join(current_chunk_parts))

    # Final fallback: split at lines if chunks still too large
    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            lines = chunk.split("\n")
            sub_parts: list[str] = []
            sub_len = 0
            for line in lines:
                if sub_len + len(line) + 1 > max_chars and sub_parts:
                    final_chunks.append("\n".join(sub_parts))
                    sub_parts = []
                    sub_len = 0
                sub_parts.append(line)
                sub_len += len(line) + 1
            if sub_parts:
                final_chunks.append("\n".join(sub_parts))

    # Filter out trivially small chunks (unless it's the only one)
    if len(final_chunks) > 1:
        final_chunks = [c for c in final_chunks if len(c.strip()) >= MIN_CHUNK_CHARS]

    return final_chunks if final_chunks else [chapter_text[:max_chars]]


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------


def _extract_chunk(
    chunk: str,
    label: str,
    system_prompt: str = EXTRACTION_SYSTEM_PROMPT,
) -> list[CharacterProfile]:
    """Extract characters from a text chunk, auto-splitting on truncation.

    If the LLM output is truncated (too many characters for the context
    window), recursively splits the chunk in half and retries each sub-chunk.

    Args:
        chunk: Text to extract characters from.
        label: Human-readable label for logging (e.g., "Chapter 19").
        system_prompt: System prompt to use for the LLM call.

    Returns:
        List of CharacterProfile objects found in this chunk.
    """
    try:
        result = call_llm_structured(
            system_prompt,
            chunk,
            ChapterExtractionResult,
        )
        if result is None:
            logger.warning("%s: extraction failed after retries", label)
            return []
        return list(result.characters)
    except TruncationError:
        if len(chunk) <= MIN_CHUNK_CHARS * 2:
            logger.warning("%s: truncated but too small to split further", label)
            return []
        logger.info("%s: output truncated, splitting and retrying", label)
        sub_chunks = _split_chapter_text(chunk, len(chunk) // 2)
        characters: list[CharacterProfile] = []
        for j, sub in enumerate(sub_chunks):
            sub_label = f"{label} sub-{j + 1}/{len(sub_chunks)}"
            characters.extend(_extract_chunk(sub, sub_label, system_prompt=system_prompt))
        return characters


def extract_characters_from_chapter(
    chapter_text: str,
    chapter_num: int,
    cache_dir: Path,
    opinionated: bool = False,
) -> list[CharacterProfile]:
    """Extract character profiles from a single chapter via LLM.

    Checks cache first, splits oversized chapters, and caches results.
    If extraction is truncated, automatically splits the chapter into
    smaller chunks and retries.

    Args:
        chapter_text: Formatted chapter text from _build_chapter_text().
        chapter_num: 1-based chapter number (for logging).
        cache_dir: Directory for cache files.
        opinionated: If True, use opinionated extraction prompt and
            separate cache key.

    Returns:
        List of CharacterProfile objects found in this chapter.
    """
    # Check cache
    cache_prefix = "extraction_v3_opinionated" if opinionated else "extraction_v3"
    cache_key = get_cache_key(chapter_text, cache_prefix)
    cached = check_cache(cache_dir, cache_key)
    if cached is not None:
        logger.info("Chapter %d: cache hit, skipping LLM call", chapter_num)
        return [CharacterProfile.model_validate(c) for c in cached]

    # Build system prompt for this extraction mode
    system_prompt = get_extraction_prompt(opinionated)

    # Split if needed
    chunks = _split_chapter_text(chapter_text, MAX_CONTENT_CHARS)
    all_characters: list[CharacterProfile] = []

    for i, chunk in enumerate(chunks):
        chunk_label = (
            f"Chapter {chapter_num}" if len(chunks) == 1
            else f"Chapter {chapter_num} chunk {i + 1}/{len(chunks)}"
        )
        logger.info("Extracting characters from %s (%d chars)", chunk_label, len(chunk))
        all_characters.extend(_extract_chunk(chunk, chunk_label, system_prompt=system_prompt))

    # Cache the result
    cache_data = [c.model_dump() for c in all_characters]
    write_cache(cache_dir, cache_key, cache_data)

    logger.info(
        "Chapter %d: extracted %d character(s)", chapter_num, len(all_characters)
    )
    return all_characters


def extract_all_characters(
    segments: list[dict],
    cache_dir: Path,
    progress_callback: Callable[[int, int], None] | None = None,
    opinionated: bool = False,
) -> dict[int, list[CharacterProfile]]:
    """Extract characters from all chapters in the book.

    Groups segments by chapter, processes each chapter through the LLM,
    and returns per-chapter character lists.

    Args:
        segments: List of segment dicts from segments.json.
        cache_dir: Directory for cache files.
        progress_callback: Optional callback(chapter_num, total_chapters)
                          called after each chapter completes.
        opinionated: If True, use opinionated extraction prompt variant.

    Returns:
        Dict mapping chapter_num -> list of CharacterProfile.
    """
    # Group segments by chapter
    chapters: dict[int, list[dict]] = defaultdict(list)
    for seg in segments:
        chapters[seg["chapter"]].append(seg)

    chapter_nums = sorted(chapters.keys())
    total = len(chapter_nums)
    result: dict[int, list[CharacterProfile]] = {}

    max_workers = get_max_workers()

    def _process_chapter(chapter_num: int) -> tuple[int, list[CharacterProfile]]:
        chapter_text = _build_chapter_text(chapters[chapter_num])
        token_estimate = estimate_tokens(chapter_text)
        logger.info(
            "Chapter %d: %d segments, ~%d tokens",
            chapter_num, len(chapters[chapter_num]), token_estimate,
        )
        characters = extract_characters_from_chapter(
            chapter_text, chapter_num, cache_dir, opinionated=opinionated
        )
        return chapter_num, characters

    if max_workers > 1:
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_process_chapter, cn): cn for cn in chapter_nums
            }
            for future in as_completed(futures):
                chapter_num, characters = future.result()
                result[chapter_num] = characters
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)
    else:
        for completed, chapter_num in enumerate(chapter_nums, 1):
            chapter_num, characters = _process_chapter(chapter_num)
            result[chapter_num] = characters
            if progress_callback:
                progress_callback(completed, total)

    total_chars = sum(len(chars) for chars in result.values())
    logger.info(
        "Extraction complete: %d chapters, %d total character entries",
        total, total_chars,
    )
    return result
