"""Emotion subpackage for the three-layer emotion system.

Provides:
- EmotionCategory: 8-category taxonomy (neutral, joy, sadness, anger, fear,
  surprise, disgust, tenderness)
- MoodIntensity: LOW/MEDIUM/HIGH intensity levels
- SceneMood: Per-scene mood annotation
- LineOverride: Line-level emotion override for extreme contrasts
- EmotionAnnotation: Combined per-chapter output
- annotate_scene_moods(): Scene boundary detection + LLM mood annotation
- detect_overrides(): Line-level override detection via LLM
"""

from src.attribution.emotion.models import (
    EmotionAnnotation,
    EmotionCategory,
    LineOverride,
    LineOverrideResult,
    MoodIntensity,
    SceneMood,
    SceneMoodResult,
)
from src.attribution.emotion.overrides import detect_overrides
from src.attribution.emotion.scene_mood import (
    annotate_scene_moods,
    detect_scene_boundaries,
)

__all__ = [
    "EmotionCategory",
    "MoodIntensity",
    "SceneMood",
    "SceneMoodResult",
    "LineOverride",
    "LineOverrideResult",
    "EmotionAnnotation",
    "annotate_scene_moods",
    "detect_scene_boundaries",
    "detect_overrides",
]
