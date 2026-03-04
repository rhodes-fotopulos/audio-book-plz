"""Pydantic models for the three-layer emotion system.

Defines:
- EmotionCategory: 8-category taxonomy for scene moods and line overrides
- MoodIntensity: LOW/MEDIUM/HIGH intensity levels
- SceneMood: Per-scene mood annotation
- SceneMoodResult: LLM response schema for scene mood annotation
- LineOverride: Line-level emotion override for extreme contrasts
- LineOverrideResult: LLM response schema for override detection
- EmotionAnnotation: Combined per-chapter output
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class EmotionCategory(str, Enum):
    """8-category emotion taxonomy for audiobook scenes.

    Maps cleanly to post-processing parameters. Covers the range
    of emotions needed for audiobook production without being so
    fine-grained that classification becomes unreliable.
    """

    NEUTRAL = "neutral"
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TENDERNESS = "tenderness"


class MoodIntensity(str, Enum):
    """Intensity level for emotion annotations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SceneMood(BaseModel):
    """Mood annotation for a single scene within a chapter.

    Every scene gets annotated (including neutral scenes).
    Scene boundaries are detected from scene_break and chapter_heading segments.
    """

    model_config = ConfigDict(strict=True)

    scene_id: int
    """Sequential scene ID within the chapter (0-based)."""

    chapter: int
    """1-based chapter number."""

    start_segment_id: int
    """ID of the first segment in this scene."""

    end_segment_id: int
    """ID of the last segment in this scene."""

    mood: EmotionCategory
    """Dominant emotion for this scene."""

    intensity: MoodIntensity
    """How intensely the mood manifests."""

    description: str
    """Brief scene summary (e.g., 'tense confrontation in the library')."""


class SceneMoodResult(BaseModel):
    """LLM response schema for scene mood annotation.

    Passed to Ollama's format parameter via model_json_schema().
    One call per chapter returns all scenes.
    """

    scenes: list[SceneMood]


class LineOverride(BaseModel):
    """Line-level emotion override for extreme emotional contrasts.

    Only lines where emotion SHARPLY breaks from scene mood get overrides.
    Most chapters have few or no overrides (high threshold).
    """

    model_config = ConfigDict(strict=True)

    segment_id: int
    """ID of the segment with the emotional override."""

    emotion: EmotionCategory
    """The OVERRIDE emotion (different from scene mood)."""

    intensity: MoodIntensity
    """Intensity of the override emotion."""

    reason: str
    """Why this line breaks from scene mood (e.g., 'laughing at a funeral')."""


class LineOverrideResult(BaseModel):
    """LLM response schema for line-level override detection.

    Passed to Ollama's format parameter via model_json_schema().
    One call per chapter returns all overrides (may be empty).
    """

    overrides: list[LineOverride]


class EmotionAnnotation(BaseModel):
    """Combined emotion output per chapter.

    Contains all scene moods and line-level overrides for one chapter.
    Written to emotion.json as part of the attribution output.
    """

    chapter: int
    """1-based chapter number."""

    scenes: list[SceneMood]
    """All scene mood annotations for this chapter."""

    overrides: list[LineOverride]
    """Line-level emotion overrides (may be empty)."""
