"""Line-level emotion override detection.

Detects dialogue segments where emotion SHARPLY breaks from the scene
mood. Uses a high threshold — only extreme contrasts get flagged:
- Joy/laughter in a sadness/anger scene
- Fear/sadness in a joy/tenderness scene
- Anger/shouting in a neutral/tenderness scene

Most chapters have few or no overrides. This is correct behavior.
"""

from __future__ import annotations

import logging

from src.attribution.emotion.models import (
    LineOverride,
    LineOverrideResult,
    SceneMood,
)
from src.attribution.llm_client import call_llm_structured

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_OVERRIDE_SYSTEM_PROMPT = """\
You are an emotion analyst for audiobook production. \
Identify dialogue lines where emotion SHARPLY contrasts the scene mood.

HIGH THRESHOLD — only flag EXTREME contrasts:
- Joy/laughter in a sadness/anger scene
- Fear/sadness in a joy/tenderness scene
- Anger/shouting in a neutral/tenderness scene
- Disgust in a joy/tenderness scene

DO NOT flag:
- Lines that simply match scene mood (even intense ones)
- Subtle emotional variation within the scene's general mood
- Lines where emotion is similar but slightly different
- Neutral dialogue in any scene

Most chapters should have FEW or NO overrides. An empty list is correct \
when all lines follow the scene mood.

Emotion categories: neutral, joy, sadness, anger, fear, surprise, disgust, tenderness
Intensity levels: low, medium, high

For each override, provide:
- segment_id: The segment that contrasts
- emotion: The OVERRIDE emotion (different from scene mood)
- intensity: How intense the override is
- reason: Brief explanation (e.g., "character laughing at a funeral")\
"""


# ---------------------------------------------------------------------------
# Core override detection
# ---------------------------------------------------------------------------


def detect_overrides(
    segments: list[dict],
    scene_moods: list[SceneMood],
) -> list[LineOverride]:
    """Detect line-level emotion overrides for extreme contrasts.

    For each scene, identifies dialogue segments where emotion sharply
    breaks from the scene mood. Uses one LLM call per chapter with all
    scenes bundled.

    Args:
        segments: List of segment dicts for one chapter.
        scene_moods: Scene mood annotations for this chapter.

    Returns:
        List of LineOverride objects (may be empty — most chapters
        have few or no overrides).
    """
    if not segments or not scene_moods:
        return []

    chapter_num = segments[0].get("chapter", 0)

    # Build segment-to-scene mapping
    seg_id_to_scene: dict[int, SceneMood] = {}
    for mood in scene_moods:
        for seg in segments:
            seg_id = seg["id"]
            if mood.start_segment_id <= seg_id <= mood.end_segment_id:
                seg_id_to_scene[seg_id] = mood

    # Build prompt with scenes and their dialogue
    lines: list[str] = []
    dialogue_count = 0

    for mood in scene_moods:
        lines.append(
            f"Scene {mood.scene_id} — Mood: {mood.mood.value} "
            f"({mood.intensity.value}) — {mood.description}"
        )

        # Include dialogue segments in this scene
        for seg in segments:
            seg_id = seg["id"]
            if (
                mood.start_segment_id <= seg_id <= mood.end_segment_id
                and seg.get("type") == "dialogue"
            ):
                text = seg.get("text", "")[:300]
                lines.append(f"  Segment {seg_id}: {text}")
                dialogue_count += 1

        lines.append("")

    if dialogue_count == 0:
        logger.info(
            "Chapter %d: no dialogue segments for override detection",
            chapter_num,
        )
        return []

    user_content = (
        f"Chapter {chapter_num} — {len(scene_moods)} scene(s), "
        f"{dialogue_count} dialogue segments:\n\n"
        + "\n".join(lines)
    )

    logger.info(
        "Chapter %d: checking %d dialogue segments for emotion overrides (%d chars)",
        chapter_num, dialogue_count, len(user_content),
    )

    result = call_llm_structured(
        _OVERRIDE_SYSTEM_PROMPT,
        user_content,
        LineOverrideResult,
    )

    if result is None:
        logger.warning(
            "Chapter %d: LLM override detection failed, returning empty",
            chapter_num,
        )
        return []

    overrides = list(result.overrides)

    if overrides:
        logger.info(
            "Chapter %d: %d line-level override(s) detected",
            chapter_num, len(overrides),
        )
    else:
        logger.info(
            "Chapter %d: no line-level overrides (all lines follow scene mood)",
            chapter_num,
        )

    return overrides
