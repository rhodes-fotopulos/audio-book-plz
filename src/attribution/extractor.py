"""Character extraction pass — chapters to per-chapter character lists.

Processes each chapter from segments.json through Qwen3 8B to extract
character profiles. Uses caching to skip chapters on re-runs (ATTR-06)
and splits oversized chapters to fit the 32K context window (ATTR-05).

Requirements covered: ATTR-01, ATTR-05, ATTR-06
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Callable

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import CONTEXT_WINDOW, call_llm_structured, estimate_tokens
from src.attribution.models import CharacterProfile, ChapterExtractionResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TOKENS = 500
"""Budget for system message overhead in tokens."""

RESPONSE_BUDGET = 4096
"""Maximum tokens reserved for LLM response."""

AVAILABLE_FOR_CONTENT = CONTEXT_WINDOW - SYSTEM_PROMPT_TOKENS - RESPONSE_BUDGET
"""Tokens available for chapter text (~28,172)."""

MAX_CONTENT_CHARS = AVAILABLE_FOR_CONTENT * 4
"""Character limit for chapter text (~112,688 chars at 1:4 ratio)."""

MIN_CHUNK_CHARS = 1000
"""Minimum chunk size to avoid trivially small LLM requests."""

EXTRACTION_SYSTEM_PROMPT = """\
You are a character extraction specialist for audiobook production. \
Extract ALL characters from the provided chapter text.

For each character found:
- name: The character's most commonly used name in this chapter
- aliases: Any other names, titles, or references used for this character
- gender: male, female, non-binary, or unknown
- age_range: child, young adult, middle-aged, elderly, or unknown
- voice_qualities: Infer pitch, pace, tone, and accent from text descriptions \
and dialogue style
- personality_traits: Key personality characteristics shown in this chapter
- relationships: Known relationships to other characters
- description: One-sentence character summary
- is_named: true if character has a proper name, false if referred to by \
description only (e.g. "the bartender")
- voice_baseline: Default speaking style with 5 fields:
  - pace: How fast they typically speak (e.g. "measured", "rapid", "languid", "clipped")
  - tone: Quality of their voice (e.g. "warm", "gravelly", "melodic", "flat", "breathy")
  - energy: How animated they are (e.g. "restrained", "animated", "intense", "subdued")
  - typical_emotion: Default emotional register (e.g. "sardonic", "cheerful", "weary")
  - description: One-sentence voice summary (e.g. "A slow, gravelly voice with weary patience")

Rules:
- Extract EVERY character who speaks or is mentioned by name, no matter how minor
- For unnamed speakers (e.g. "the old man", "a soldier"), create profiles \
with is_named=false
- Infer voice qualities from context: "the old man grumbled" implies elderly \
male, low pitch, slow pace, gruff tone
- Infer voice_baseline from dialogue style, narration descriptions, and personality
- Include character relationships when evident from text
- When unsure about a trait, use "unknown" — do not guess without textual evidence"""


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


def extract_characters_from_chapter(
    chapter_text: str,
    chapter_num: int,
    cache_dir: Path,
) -> list[CharacterProfile]:
    """Extract character profiles from a single chapter via LLM.

    Checks cache first, splits oversized chapters, and caches results.

    Args:
        chapter_text: Formatted chapter text from _build_chapter_text().
        chapter_num: 1-based chapter number (for logging).
        cache_dir: Directory for cache files.

    Returns:
        List of CharacterProfile objects found in this chapter.
    """
    # Check cache
    cache_key = get_cache_key(chapter_text, "extraction")
    cached = check_cache(cache_dir, cache_key)
    if cached is not None:
        logger.info("Chapter %d: cache hit, skipping LLM call", chapter_num)
        return [CharacterProfile.model_validate(c) for c in cached]

    # Split if needed
    chunks = _split_chapter_text(chapter_text, MAX_CONTENT_CHARS)
    all_characters: list[CharacterProfile] = []

    for i, chunk in enumerate(chunks):
        chunk_label = (
            f"Chapter {chapter_num}" if len(chunks) == 1
            else f"Chapter {chapter_num} chunk {i + 1}/{len(chunks)}"
        )
        logger.info("Extracting characters from %s (%d chars)", chunk_label, len(chunk))

        result = call_llm_structured(
            EXTRACTION_SYSTEM_PROMPT,
            chunk,
            ChapterExtractionResult,
        )

        if result is None:
            logger.warning("%s: LLM extraction failed after retries", chunk_label)
            continue

        all_characters.extend(result.characters)

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
) -> dict[int, list[CharacterProfile]]:
    """Extract characters from all chapters in the book.

    Groups segments by chapter, processes each chapter through the LLM,
    and returns per-chapter character lists.

    Args:
        segments: List of segment dicts from segments.json.
        cache_dir: Directory for cache files.
        progress_callback: Optional callback(chapter_num, total_chapters)
                          called after each chapter completes.

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

    for chapter_num in chapter_nums:
        chapter_text = _build_chapter_text(chapters[chapter_num])
        token_estimate = estimate_tokens(chapter_text)
        logger.info(
            "Chapter %d: %d segments, ~%d tokens",
            chapter_num, len(chapters[chapter_num]), token_estimate,
        )

        characters = extract_characters_from_chapter(
            chapter_text, chapter_num, cache_dir
        )
        result[chapter_num] = characters

        if progress_callback:
            progress_callback(chapter_num, total)

    total_chars = sum(len(chars) for chars in result.values())
    logger.info(
        "Extraction complete: %d chapters, %d total character entries",
        total, total_chars,
    )
    return result
