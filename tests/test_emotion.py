"""Tests for emotion subpackage: models, scene mood, overrides.

Covers:
- EmotionCategory enum values
- SceneMood and LineOverride model creation
- Scene boundary detection using scene_break/chapter_heading
- Scene boundary for chapters without breaks (single scene)
- Annotate scene moods LLM call
- Override detection for matching mood (empty result)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.attribution.emotion import (
    EmotionCategory,
    MoodIntensity,
    SceneMood,
    LineOverride,
    annotate_scene_moods,
    detect_scene_boundaries,
    detect_overrides,
)
from src.attribution.emotion.models import (
    EmotionAnnotation,
    SceneMoodResult,
    LineOverrideResult,
)


# ---------------------------------------------------------------------------
# Tests: EmotionCategory enum
# ---------------------------------------------------------------------------


class TestEmotionCategory:
    """Tests for EmotionCategory enum values."""

    def test_emotion_category_has_8_values(self) -> None:
        """EmotionCategory should have exactly 8 values."""
        assert len(EmotionCategory) == 8

    def test_emotion_category_values(self) -> None:
        """All 8 expected categories should exist."""
        expected = {
            "neutral", "joy", "sadness", "anger",
            "fear", "surprise", "disgust", "tenderness",
        }
        actual = {e.value for e in EmotionCategory}
        assert actual == expected

    def test_emotion_category_is_string_enum(self) -> None:
        """EmotionCategory values should be strings."""
        for e in EmotionCategory:
            assert isinstance(e.value, str)


# ---------------------------------------------------------------------------
# Tests: SceneMood model
# ---------------------------------------------------------------------------


class TestSceneMoodModel:
    """Tests for SceneMood Pydantic model."""

    def test_scene_mood_creation(self) -> None:
        """Should create SceneMood with all fields."""
        mood = SceneMood(
            scene_id=0,
            chapter=1,
            start_segment_id=0,
            end_segment_id=10,
            mood=EmotionCategory.NEUTRAL,
            intensity=MoodIntensity.LOW,
            description="Calm opening",
        )
        assert mood.scene_id == 0
        assert mood.chapter == 1
        assert mood.mood == EmotionCategory.NEUTRAL
        assert mood.intensity == MoodIntensity.LOW
        assert mood.description == "Calm opening"

    def test_scene_mood_serialization(self) -> None:
        """SceneMood should serialize to dict with string enum values."""
        mood = SceneMood(
            scene_id=0,
            chapter=1,
            start_segment_id=0,
            end_segment_id=5,
            mood=EmotionCategory.JOY,
            intensity=MoodIntensity.HIGH,
            description="Celebration",
        )
        data = mood.model_dump()
        assert data["mood"] == "joy"
        assert data["intensity"] == "high"


# ---------------------------------------------------------------------------
# Tests: LineOverride model
# ---------------------------------------------------------------------------


class TestLineOverrideModel:
    """Tests for LineOverride Pydantic model."""

    def test_line_override_creation(self) -> None:
        """Should create LineOverride with all fields."""
        override = LineOverride(
            segment_id=42,
            emotion=EmotionCategory.JOY,
            intensity=MoodIntensity.HIGH,
            reason="Character laughing at a funeral",
        )
        assert override.segment_id == 42
        assert override.emotion == EmotionCategory.JOY
        assert override.reason == "Character laughing at a funeral"


# ---------------------------------------------------------------------------
# Tests: detect_scene_boundaries
# ---------------------------------------------------------------------------


class TestDetectSceneBoundaries:
    """Tests for scene boundary detection."""

    def test_uses_scene_breaks(self) -> None:
        """Scene breaks should split segments into scenes."""
        segments = [
            {"id": 0, "type": "narration", "text": "Once upon a time."},
            {"id": 1, "type": "dialogue", "text": "Hello there."},
            {"id": 2, "type": "scene_break", "text": "***"},
            {"id": 3, "type": "narration", "text": "Later that day."},
            {"id": 4, "type": "dialogue", "text": "What happened?"},
        ]

        scenes = detect_scene_boundaries(segments)

        assert len(scenes) == 2
        assert len(scenes[0]) == 2  # segs 0-1
        assert len(scenes[1]) == 3  # segs 2-4 (scene_break starts new scene)

    def test_chapter_heading_starts_new_scene(self) -> None:
        """Chapter headings should start new scenes."""
        segments = [
            {"id": 0, "type": "chapter_heading", "text": "Chapter 1"},
            {"id": 1, "type": "narration", "text": "The story begins."},
            {"id": 2, "type": "narration", "text": "It was dark."},
        ]

        scenes = detect_scene_boundaries(segments)

        # First segment is chapter_heading, but there's nothing before it
        # so it's just one scene starting with the heading
        assert len(scenes) == 1
        assert scenes[0][0]["type"] == "chapter_heading"

    def test_chapter_as_single_scene(self) -> None:
        """Chapters without breaks should be a single scene."""
        segments = [
            {"id": 0, "type": "narration", "text": "Just a simple chapter."},
            {"id": 1, "type": "dialogue", "text": "Hello."},
            {"id": 2, "type": "narration", "text": "The end."},
        ]

        scenes = detect_scene_boundaries(segments)

        assert len(scenes) == 1
        assert len(scenes[0]) == 3

    def test_empty_segments(self) -> None:
        """Empty segment list should return empty scenes."""
        scenes = detect_scene_boundaries([])
        assert scenes == []

    def test_multiple_scene_breaks(self) -> None:
        """Multiple scene breaks should create multiple scenes."""
        segments = [
            {"id": 0, "type": "narration", "text": "Scene 1."},
            {"id": 1, "type": "scene_break", "text": "***"},
            {"id": 2, "type": "narration", "text": "Scene 2."},
            {"id": 3, "type": "scene_break", "text": "***"},
            {"id": 4, "type": "narration", "text": "Scene 3."},
        ]

        scenes = detect_scene_boundaries(segments)

        assert len(scenes) == 3


# ---------------------------------------------------------------------------
# Tests: annotate_scene_moods (with mocked LLM)
# ---------------------------------------------------------------------------


class TestAnnotateSceneMoods:
    """Tests for scene mood annotation via LLM."""

    @patch("src.attribution.emotion.scene_mood.call_llm_structured")
    def test_calls_llm_with_scene_mood_result_schema(
        self, mock_llm: MagicMock
    ) -> None:
        """Should call LLM with SceneMoodResult schema."""
        mock_llm.return_value = SceneMoodResult(
            scenes=[
                SceneMood(
                    scene_id=0,
                    chapter=1,
                    start_segment_id=0,
                    end_segment_id=2,
                    mood=EmotionCategory.NEUTRAL,
                    intensity=MoodIntensity.LOW,
                    description="Opening scene",
                )
            ]
        )

        segments = [
            {"id": 0, "type": "narration", "text": "The sun rose."},
            {"id": 1, "type": "dialogue", "text": "Good morning."},
            {"id": 2, "type": "narration", "text": "She smiled."},
        ]

        result = annotate_scene_moods(segments, chapter_num=1)

        assert len(result) == 1
        assert result[0].mood == EmotionCategory.NEUTRAL
        mock_llm.assert_called_once()
        # Verify the schema class was SceneMoodResult
        call_args = mock_llm.call_args
        assert call_args.args[2] == SceneMoodResult

    @patch("src.attribution.emotion.scene_mood.call_llm_structured")
    def test_returns_neutral_default_on_llm_failure(
        self, mock_llm: MagicMock
    ) -> None:
        """Should return neutral defaults when LLM fails."""
        mock_llm.return_value = None

        segments = [
            {"id": 0, "type": "narration", "text": "Something happens."},
        ]

        result = annotate_scene_moods(segments, chapter_num=1)

        assert len(result) == 1
        assert result[0].mood == EmotionCategory.NEUTRAL


# ---------------------------------------------------------------------------
# Tests: detect_overrides
# ---------------------------------------------------------------------------


class TestDetectOverrides:
    """Tests for line-level override detection."""

    @patch("src.attribution.emotion.overrides.call_llm_structured")
    def test_returns_empty_for_matching_mood(
        self, mock_llm: MagicMock
    ) -> None:
        """When all lines match scene mood, should return no overrides."""
        mock_llm.return_value = LineOverrideResult(overrides=[])

        segments = [
            {"id": 0, "chapter": 1, "type": "dialogue", "text": "This is sad."},
        ]
        scene_moods = [
            SceneMood(
                scene_id=0,
                chapter=1,
                start_segment_id=0,
                end_segment_id=0,
                mood=EmotionCategory.SADNESS,
                intensity=MoodIntensity.MEDIUM,
                description="Sad scene",
            )
        ]

        result = detect_overrides(segments, scene_moods)

        assert result == []

    def test_returns_empty_for_empty_inputs(self) -> None:
        """Should return empty list for empty segments or moods."""
        assert detect_overrides([], []) == []


# ---------------------------------------------------------------------------
# Tests: EmotionAnnotation model
# ---------------------------------------------------------------------------


class TestEmotionAnnotation:
    """Tests for EmotionAnnotation combined model."""

    def test_emotion_annotation_creation(self) -> None:
        """Should create EmotionAnnotation with scenes and overrides."""
        annotation = EmotionAnnotation(
            chapter=1,
            scenes=[
                SceneMood(
                    scene_id=0,
                    chapter=1,
                    start_segment_id=0,
                    end_segment_id=5,
                    mood=EmotionCategory.JOY,
                    intensity=MoodIntensity.HIGH,
                    description="Party scene",
                )
            ],
            overrides=[],
        )
        assert annotation.chapter == 1
        assert len(annotation.scenes) == 1
        assert len(annotation.overrides) == 0
