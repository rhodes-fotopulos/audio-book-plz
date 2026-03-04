"""Speaker attribution pass — segments + registry to attributed segments.

Assigns a speaker to every segment in the book:
- Non-dialogue (narration, chapter_heading, scene_break): "narrator" with
  confidence 1.0 — no LLM call needed (ATTR-04)
- Dialogue: character name from registry via Qwen3 8B with confidence
  scoring and contextual reasoning (ATTR-03)

Uses caching to skip chapters on re-runs (ATTR-06) and respects the 32K
context window budget (ATTR-05).

Requirements covered: ATTR-03, ATTR-04, ATTR-05, ATTR-06
"""

from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path
from typing import Callable

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import CONTEXT_WINDOW, call_llm_structured
from src.attribution.models import (
    CharacterProfile,
    ChapterAttributionResult,
)
from src.attribution.speech_acts import classify_speech_acts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGISTRY_BUDGET_TOKENS = 2000
"""Tokens reserved for the character registry in the attribution prompt."""

SYSTEM_PROMPT_TOKENS = 500
"""Budget for system message overhead in tokens."""

RESPONSE_BUDGET = 4096
"""Maximum tokens reserved for LLM response."""

AVAILABLE_FOR_CONTENT = (
    CONTEXT_WINDOW - SYSTEM_PROMPT_TOKENS - RESPONSE_BUDGET - REGISTRY_BUDGET_TOKENS
)
"""Tokens available for segment text (~26,172)."""

MAX_CONTENT_CHARS = AVAILABLE_FOR_CONTENT * 4
"""Character limit for segment text per LLM call (~104,688 chars at 1:4 ratio)."""

CONFIDENCE_FLAG_THRESHOLD = 0.7
"""Attributions below this confidence are flagged in stats."""

ATTRIBUTION_SYSTEM_PROMPT = """\
You are a dialogue attribution specialist for audiobook production. \
For each segment, identify who is speaking.

Character Registry (these are the characters in this book):
{registry_json}

Rules:
- For dialogue segments: Identify the speaker from the character registry. \
Use the canonical name from the registry.
- For narration, chapter headings, and scene breaks: Set speaker to "narrator".
- Internal monologue and thoughts: Set speaker to the CHARACTER \
who is thinking (not narrator). These will be tagged as "thought" speech-act.
- Group dialogue ("they all shouted"): Set speaker to "narrator".
- When a dialogue line has no explicit tag ("said X"), infer the speaker from:
  1. Turn-taking pattern (alternating speakers in conversation)
  2. Surrounding narration context ("she turned to him" before a dialogue line)
  3. Content/vocabulary matching known character speech patterns
- Confidence scoring:
  - 1.0: Explicit attribution ("X said") or non-dialogue (always narrator)
  - 0.8-0.99: Strong contextual evidence (clear turn-taking, adjacent narration)
  - 0.5-0.79: Moderate inference (conversation flow, some ambiguity)
  - 0.1-0.49: Weak guess (multiple candidates, little context)
- Always provide your best guess — never leave speaker empty or null
- The reasoning field should briefly explain WHY you chose this speaker \
(1 sentence)"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_registry_for_prompt(characters: list[CharacterProfile]) -> str:
    """Format the character registry as a compact summary for the LLM prompt.

    Each character is rendered on one line with name, aliases, gender,
    age_range, and personality traits. Kept concise to stay within
    REGISTRY_BUDGET_TOKENS.

    Args:
        characters: List of CharacterProfile objects from the merged registry.

    Returns:
        Formatted string suitable for embedding in the system prompt.
    """
    lines: list[str] = []
    for char in characters:
        parts = [char.name]
        if char.aliases:
            parts.append(f"(aliases: {', '.join(char.aliases)})")
        parts.append(f"- {char.gender}, {char.age_range}")
        if char.personality_traits:
            traits = ", ".join(char.personality_traits[:5])  # Limit to 5 traits
            parts.append(f"traits: [{traits}]")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def attribute_non_dialogue(segments: list[dict]) -> list[dict]:
    """Assign narrator to all non-dialogue segments without LLM calls.

    Segments with type "narration", "chapter_heading", or "scene_break"
    are attributed to the narrator with confidence 1.0. Dialogue segments
    are left untouched.

    Args:
        segments: List of segment dicts (modified in place).

    Returns:
        The same list of segments with non-dialogue segments attributed.
    """
    non_dialogue_types = {"narration", "chapter_heading", "scene_break"}
    for seg in segments:
        if seg.get("type", "") in non_dialogue_types:
            seg["speaker"] = "narrator"
            seg["confidence"] = 1.0
    return segments


def _build_dialogue_prompt(
    segments: list[dict],
    dialogue_indices: list[int],
) -> str:
    """Build user prompt content with numbered dialogue segments and context.

    Each dialogue segment is presented with its surrounding context (up to
    2 segments before and after) to help the LLM infer the speaker.

    Args:
        segments: Full chapter segment list.
        dialogue_indices: Indices into segments of dialogue segments.

    Returns:
        Formatted prompt string for the LLM.
    """
    lines: list[str] = []
    for idx in dialogue_indices:
        seg = segments[idx]
        lines.append(f"Segment {seg['id']} (type: {seg['type']}): {seg['text']}")

        # Context before (up to 2 segments)
        prev_context: list[str] = []
        for offset in range(1, 3):
            prev_idx = idx - offset
            if prev_idx >= 0:
                prev_seg = segments[prev_idx]
                prev_context.insert(0, prev_seg.get("text", "")[:200])
        if prev_context:
            lines.append(f'[Context before: "{" | ".join(prev_context)}"]')

        # Context after (up to 2 segments)
        next_context: list[str] = []
        for offset in range(1, 3):
            next_idx = idx + offset
            if next_idx < len(segments):
                next_seg = segments[next_idx]
                next_context.append(next_seg.get("text", "")[:200])
        if next_context:
            lines.append(f'[Context after: "{" | ".join(next_context)}"]')

        lines.append("")  # Blank line between segments

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core attribution
# ---------------------------------------------------------------------------


def attribute_chapter(
    chapter_segments: list[dict],
    characters: list[CharacterProfile],
    chapter_num: int,
    cache_dir: Path,
) -> list[dict]:
    """Attribute speakers for all segments in a single chapter.

    Non-dialogue segments are assigned to narrator immediately. Dialogue
    segments are sent to the LLM with the character registry for speaker
    identification. Results are cached for incremental re-runs.

    Args:
        chapter_segments: List of segment dicts for this chapter.
        characters: Merged character registry.
        chapter_num: 1-based chapter number (for logging).
        cache_dir: Directory for cache files.

    Returns:
        The chapter segments list with speaker and confidence fields added.
    """
    # Step 1: Attribute non-dialogue segments
    attribute_non_dialogue(chapter_segments)

    # Step 2: Find dialogue segments that need LLM attribution
    dialogue_indices: list[int] = []
    for i, seg in enumerate(chapter_segments):
        if "speaker" not in seg:
            dialogue_indices.append(i)

    if not dialogue_indices:
        logger.info("Chapter %d: no dialogue segments, all narrator", chapter_num)
        return chapter_segments

    # Step 3: Check cache
    dialogue_text = "\n".join(
        chapter_segments[i].get("text", "") for i in dialogue_indices
    )
    cache_key = get_cache_key(dialogue_text, "attribution")
    cached = check_cache(cache_dir, cache_key)
    if cached is not None:
        logger.info("Chapter %d: attribution cache hit, skipping LLM", chapter_num)
        # Apply cached attributions by segment_id
        cached_map = {a["segment_id"]: a for a in cached}
        for idx in dialogue_indices:
            seg = chapter_segments[idx]
            seg_id = seg["id"]
            if seg_id in cached_map:
                seg["speaker"] = cached_map[seg_id]["speaker"]
                seg["confidence"] = cached_map[seg_id]["confidence"]
            else:
                seg["speaker"] = "unknown"
                seg["confidence"] = 0.0
        return chapter_segments

    # Step 4: Build prompt
    registry_text = _format_registry_for_prompt(characters)
    system_prompt = ATTRIBUTION_SYSTEM_PROMPT.replace("{registry_json}", registry_text)

    # Step 5: Split into batches if needed
    full_prompt = _build_dialogue_prompt(chapter_segments, dialogue_indices)

    if len(full_prompt) <= MAX_CONTENT_CHARS:
        batches = [(dialogue_indices, full_prompt)]
    else:
        # Split dialogue indices into batches that fit
        batches = []
        current_indices: list[int] = []
        current_len = 0
        for idx in dialogue_indices:
            seg = chapter_segments[idx]
            # Rough estimate of this segment's contribution
            seg_text_len = len(seg.get("text", "")) + 300  # +300 for context overhead
            if current_len + seg_text_len > MAX_CONTENT_CHARS and current_indices:
                batch_prompt = _build_dialogue_prompt(
                    chapter_segments, current_indices
                )
                batches.append((current_indices, batch_prompt))
                current_indices = []
                current_len = 0
            current_indices.append(idx)
            current_len += seg_text_len
        if current_indices:
            batch_prompt = _build_dialogue_prompt(
                chapter_segments, current_indices
            )
            batches.append((current_indices, batch_prompt))

    # Step 6: Call LLM for each batch
    all_attributions: list[dict] = []
    for batch_num, (batch_indices, batch_prompt) in enumerate(batches, 1):
        batch_label = (
            f"Chapter {chapter_num}"
            if len(batches) == 1
            else f"Chapter {chapter_num} batch {batch_num}/{len(batches)}"
        )
        logger.info(
            "Attributing %d dialogue segments in %s (%d chars)",
            len(batch_indices),
            batch_label,
            len(batch_prompt),
        )

        result = call_llm_structured(
            system_prompt,
            batch_prompt,
            ChapterAttributionResult,
        )

        if result is None:
            logger.warning(
                "%s: LLM attribution failed after retries", batch_label
            )
            for idx in batch_indices:
                seg = chapter_segments[idx]
                seg["speaker"] = "unknown"
                seg["confidence"] = 0.0
                all_attributions.append(
                    {
                        "segment_id": seg["id"],
                        "speaker": "unknown",
                        "confidence": 0.0,
                        "reasoning": "LLM call failed",
                    }
                )
            continue

        # Match attributions to segments by segment_id
        attr_map = {a.segment_id: a for a in result.attributions}
        for idx in batch_indices:
            seg = chapter_segments[idx]
            seg_id = seg["id"]
            if seg_id in attr_map:
                attr = attr_map[seg_id]
                seg["speaker"] = attr.speaker
                seg["confidence"] = attr.confidence
                all_attributions.append(
                    {
                        "segment_id": seg_id,
                        "speaker": attr.speaker,
                        "confidence": attr.confidence,
                        "reasoning": attr.reasoning,
                    }
                )
            else:
                seg["speaker"] = "unknown"
                seg["confidence"] = 0.0
                all_attributions.append(
                    {
                        "segment_id": seg_id,
                        "speaker": "unknown",
                        "confidence": 0.0,
                        "reasoning": "Not in LLM response",
                    }
                )

    # Step 7: Cache results
    write_cache(cache_dir, cache_key, all_attributions)

    attributed_count = sum(
        1
        for idx in dialogue_indices
        if chapter_segments[idx].get("speaker", "unknown") != "unknown"
    )
    logger.info(
        "Chapter %d: attributed %d/%d dialogue segments",
        chapter_num,
        attributed_count,
        len(dialogue_indices),
    )
    return chapter_segments


def attribute_all_segments(
    segments: list[dict],
    characters: list[CharacterProfile],
    cache_dir: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[dict]:
    """Attribute speakers for all segments across all chapters.

    Groups segments by chapter, processes each chapter through
    attribute_chapter, and returns the flat list of all segments
    with speaker and confidence fields added.

    Args:
        segments: List of segment dicts from segments.json.
        characters: Merged character registry.
        cache_dir: Directory for cache files.
        progress_callback: Optional callback(chapter_num, total_chapters)
                          called after each chapter completes.

    Returns:
        Flat list of all segments with speaker and confidence fields.
    """
    # Group segments by chapter
    chapters: dict[int, list[dict]] = defaultdict(list)
    chapter_order: dict[int, list[int]] = defaultdict(list)

    for i, seg in enumerate(segments):
        chapter_num = seg["chapter"]
        chapters[chapter_num].append(seg)
        chapter_order[chapter_num].append(i)

    chapter_nums = sorted(chapters.keys())
    total = len(chapter_nums)

    for chapter_num in chapter_nums:
        logger.info(
            "Attributing chapter %d/%d (%d segments)",
            chapter_num,
            total,
            len(chapters[chapter_num]),
        )

        attribute_chapter(
            chapters[chapter_num],
            characters,
            chapter_num,
            cache_dir,
        )

        # Run speech-act classification after attribution
        classify_speech_acts(chapters[chapter_num], chapter_num)

        if progress_callback:
            progress_callback(chapter_num, total)

    # Flatten back to original order (segments were modified in place)
    total_dialogue = sum(
        1 for seg in segments if seg.get("type") == "dialogue"
    )
    total_attributed = sum(
        1
        for seg in segments
        if seg.get("type") == "dialogue"
        and seg.get("speaker", "unknown") != "unknown"
    )
    logger.info(
        "Attribution complete: %d chapters, %d/%d dialogue segments attributed",
        total,
        total_attributed,
        total_dialogue,
    )

    return segments
