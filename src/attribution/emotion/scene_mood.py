"""Scene boundary detection and mood annotation via LLM.

Detects scene boundaries using existing segment types (scene_break,
chapter_heading), then annotates each scene's mood via a single
LLM call per chapter.

Every scene gets annotated — neutral is valid and useful.
"""

from __future__ import annotations

import logging

from src.attribution.emotion.models import (
    EmotionCategory,
    MoodIntensity,
    SceneMood,
    SceneMoodResult,
)
from src.attribution.llm_client import call_llm_structured

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scene boundary detection
# ---------------------------------------------------------------------------

_SCENE_MOOD_SYSTEM_PROMPT = """\
You are an emotion analyst for audiobook production. \
For each scene in the chapter, annotate the dominant mood.

Emotion categories (pick ONE per scene):
- neutral: Calm, everyday, expository, no strong emotion
- joy: Happiness, celebration, relief, humor, excitement
- sadness: Grief, loss, melancholy, disappointment
- anger: Rage, frustration, hostility, confrontation
- fear: Terror, anxiety, dread, suspense
- surprise: Shock, revelation, unexpected turn
- disgust: Revulsion, contempt, moral outrage
- tenderness: Love, affection, intimacy, compassion

Intensity levels:
- low: Subtle, understated
- medium: Clear, present
- high: Dominant, overwhelming

Rules:
- EVERY scene must have an annotation — neutral is valid and useful
- Use the scene text to determine mood, not just keywords
- Description should be a brief scene summary (5-10 words)
- scene_id must be sequential starting from 0
- start_segment_id and end_segment_id must match the provided segment IDs\
"""


def detect_scene_boundaries(segments: list[dict]) -> list[list[dict]]:
    """Group segments into scenes using existing boundary markers.

    Scene boundaries are detected from:
    1. scene_break type segments
    2. chapter_heading segments (chapter start = new scene)

    If no explicit boundaries are found, the entire chapter is one scene.

    Args:
        segments: List of segment dicts for one chapter.

    Returns:
        List of scene groups (each group is a list of segment dicts).
    """
    if not segments:
        return []

    scenes: list[list[dict]] = []
    current_scene: list[dict] = []

    for seg in segments:
        seg_type = seg.get("type", "")

        # Scene break or chapter heading starts a new scene
        if seg_type in ("scene_break", "chapter_heading") and current_scene:
            scenes.append(current_scene)
            current_scene = []

        current_scene.append(seg)

    # Don't forget the last scene
    if current_scene:
        scenes.append(current_scene)

    return scenes


def annotate_scene_moods(
    segments: list[dict],
    chapter_num: int,
) -> list[SceneMood]:
    """Annotate scene moods for a chapter via LLM.

    Detects scene boundaries, builds a prompt with scene text (first 500
    chars per scene for efficiency), and calls the LLM once per chapter
    to annotate all scenes.

    Args:
        segments: List of segment dicts for one chapter.
        chapter_num: 1-based chapter number.

    Returns:
        List of SceneMood objects, one per scene.
    """
    scene_groups = detect_scene_boundaries(segments)

    if not scene_groups:
        logger.warning("Chapter %d: no segments for scene mood annotation", chapter_num)
        return []

    # Build prompt with scene text summaries
    lines: list[str] = []
    for scene_idx, scene_segs in enumerate(scene_groups):
        start_id = scene_segs[0]["id"]
        end_id = scene_segs[-1]["id"]

        # Concatenate scene text (first 500 chars for efficiency)
        scene_text = " ".join(
            seg.get("text", "").strip()
            for seg in scene_segs
            if seg.get("text", "").strip()
        )[:500]

        lines.append(
            f"Scene {scene_idx} (segments {start_id}-{end_id}):\n"
            f"{scene_text}\n"
        )

    user_content = (
        f"Chapter {chapter_num} — {len(scene_groups)} scene(s):\n\n"
        + "\n".join(lines)
    )

    logger.info(
        "Chapter %d: annotating %d scene(s) (%d chars prompt)",
        chapter_num, len(scene_groups), len(user_content),
    )

    result = call_llm_structured(
        _SCENE_MOOD_SYSTEM_PROMPT,
        user_content,
        SceneMoodResult,
    )

    if result is None:
        logger.warning(
            "Chapter %d: LLM scene mood annotation failed, returning neutral defaults",
            chapter_num,
        )
        # Return neutral defaults for all scenes
        defaults = []
        for scene_idx, scene_segs in enumerate(scene_groups):
            defaults.append(
                SceneMood(
                    scene_id=scene_idx,
                    chapter=chapter_num,
                    start_segment_id=scene_segs[0]["id"],
                    end_segment_id=scene_segs[-1]["id"],
                    mood=EmotionCategory.NEUTRAL,
                    intensity=MoodIntensity.LOW,
                    description="LLM annotation failed — neutral default",
                )
            )
        return defaults

    # Validate and fill gaps
    result_scenes = list(result.scenes)

    # Ensure every scene has an annotation by filling gaps with neutral
    annotated_ids = {s.scene_id for s in result_scenes}
    for scene_idx, scene_segs in enumerate(scene_groups):
        if scene_idx not in annotated_ids:
            result_scenes.append(
                SceneMood(
                    scene_id=scene_idx,
                    chapter=chapter_num,
                    start_segment_id=scene_segs[0]["id"],
                    end_segment_id=scene_segs[-1]["id"],
                    mood=EmotionCategory.NEUTRAL,
                    intensity=MoodIntensity.LOW,
                    description="No LLM annotation — neutral default",
                )
            )

    # Sort by scene_id
    result_scenes.sort(key=lambda s: s.scene_id)

    logger.info(
        "Chapter %d: %d scene mood(s) annotated",
        chapter_num, len(result_scenes),
    )

    return result_scenes
