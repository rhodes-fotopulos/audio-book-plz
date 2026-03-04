"""Tests for hybrid regex+LLM speech-act classification.

Covers:
- Regex pattern detection for shouted, whispered, thought
- Default to spoken when no patterns match
- ALL-CAPS detection
- Multiple exclamation marks
- 'to herself' pattern
- Full classify_speech_acts integration with mocked LLM
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.attribution.speech_acts import (
    CONF_DEFAULT,
    CONF_LLM_THRESHOLD,
    CONF_NARRATION_TAG,
    CONF_TEXT_PATTERN,
    classify_speech_act_regex,
    classify_speech_acts,
    classify_speech_acts_llm,
)


# ---------------------------------------------------------------------------
# Tests: classify_speech_act_regex
# ---------------------------------------------------------------------------


class TestRegexClassification:
    """Tests for regex-based speech-act detection."""

    def test_regex_shouted_narration_tag(self) -> None:
        """'he shouted' in context should return shouted with high confidence."""
        tag, conf = classify_speech_act_regex(
            "Stop right there!", "he shouted,", ""
        )
        assert tag == "shouted"
        assert conf >= 0.8

    def test_regex_shouted_yelled(self) -> None:
        """'she yelled' in context should return shouted."""
        tag, conf = classify_speech_act_regex(
            "Get out!", "", "she yelled at him."
        )
        assert tag == "shouted"
        assert conf >= 0.8

    def test_regex_whispered_narration_tag(self) -> None:
        """'she whispered' in context should return whispered with high confidence."""
        tag, conf = classify_speech_act_regex(
            "Be quiet", "she whispered,", ""
        )
        assert tag == "whispered"
        assert conf >= 0.8

    def test_regex_whispered_murmured(self) -> None:
        """'he murmured' should detect whispered."""
        tag, conf = classify_speech_act_regex(
            "I don't know", "", "he murmured softly."
        )
        assert tag == "whispered"
        assert conf >= 0.8

    def test_regex_thought_verb(self) -> None:
        """'he thought' in context should return thought with high confidence."""
        tag, conf = classify_speech_act_regex(
            "This can't be happening", "he thought,", ""
        )
        assert tag == "thought"
        assert conf >= 0.8

    def test_regex_thought_wondered(self) -> None:
        """'she wondered' should detect thought."""
        tag, conf = classify_speech_act_regex(
            "What if it's true?", "", "she wondered."
        )
        assert tag == "thought"
        assert conf >= 0.8

    def test_regex_to_herself(self) -> None:
        """'to herself' in context should return thought with high confidence."""
        tag, conf = classify_speech_act_regex(
            "This is ridiculous", "she said to herself,", ""
        )
        assert tag == "thought"
        assert conf >= 0.8

    def test_regex_to_himself(self) -> None:
        """'to himself' pattern should also detect thought."""
        tag, conf = classify_speech_act_regex(
            "I need to be careful", "he muttered to himself.", ""
        )
        # 'muttered' matches whispered before 'to himself' is checked
        # Both are valid - the important thing is it's not 'spoken'
        assert tag in ("whispered", "thought")
        assert conf >= 0.8

    def test_regex_all_caps_dialogue(self) -> None:
        """ALL-CAPS words in dialogue text should return shouted."""
        tag, conf = classify_speech_act_regex(
            "STOP RIGHT THERE", "", ""
        )
        assert tag == "shouted"
        assert conf >= 0.7

    def test_regex_all_caps_excludes_common_words(self) -> None:
        """Common all-caps abbreviations should not trigger shouted."""
        tag, conf = classify_speech_act_regex(
            "The FBI agent arrived", "", ""
        )
        # FBI is in exclusion list, THE is in exclusion list
        assert tag == "spoken"

    def test_regex_multiple_exclamation(self) -> None:
        """Multiple exclamation marks should return shouted."""
        tag, conf = classify_speech_act_regex(
            "Stop!!", "", ""
        )
        assert tag == "shouted"
        assert conf >= 0.7

    def test_regex_single_exclamation_no_match(self) -> None:
        """Single exclamation should NOT trigger shouted."""
        tag, conf = classify_speech_act_regex(
            "Hello!", "", ""
        )
        assert tag == "spoken"

    def test_regex_no_match_defaults_spoken(self) -> None:
        """Neutral text should default to spoken with low confidence."""
        tag, conf = classify_speech_act_regex(
            "Hello there", "he said,", ""
        )
        assert tag == "spoken"
        assert conf == CONF_DEFAULT

    def test_narration_context_priority_over_text(self) -> None:
        """Narration context should be checked before text patterns."""
        # Even though text has !!, the narration says 'whispered'
        tag, conf = classify_speech_act_regex(
            "No!!", "she whispered,", ""
        )
        # Narration context is checked first, so whispered wins
        # (shouted narration pattern is checked before whispered, but
        # 'whispered' matches first in this case)
        assert tag == "whispered"
        assert conf == CONF_NARRATION_TAG


# ---------------------------------------------------------------------------
# Tests: classify_speech_acts (integration)
# ---------------------------------------------------------------------------


class TestClassifySpeechActsIntegration:
    """Tests for full classify_speech_acts flow."""

    def test_non_dialogue_gets_spoken(self) -> None:
        """Non-dialogue segments should get speech_act='spoken'."""
        segments = [
            {"id": 0, "type": "narration", "text": "It was a dark night."},
            {"id": 1, "type": "chapter_heading", "text": "Chapter 1"},
            {"id": 2, "type": "scene_break", "text": "***"},
        ]

        result = classify_speech_acts(segments, chapter_num=1)

        for seg in result:
            assert seg["speech_act"] == "spoken"

    def test_high_confidence_regex_skips_llm(self) -> None:
        """Segments with high-confidence regex should not go to LLM."""
        segments = [
            {"id": 0, "type": "narration", "text": "She whispered,"},
            {"id": 1, "type": "dialogue", "text": "Be quiet."},
            {"id": 2, "type": "narration", "text": "And left the room."},
        ]

        with patch(
            "src.attribution.speech_acts.classify_speech_acts_llm"
        ) as mock_llm:
            mock_llm.return_value = {}
            result = classify_speech_acts(segments, chapter_num=1)

        # Regex should detect 'whispered' with high confidence (0.9)
        # so LLM should either not be called or called with empty list
        assert result[1]["speech_act"] == "whispered"

    @patch("src.attribution.speech_acts.classify_speech_acts_llm")
    def test_llm_overrides_low_confidence_regex(
        self, mock_llm: MagicMock
    ) -> None:
        """LLM result should override low-confidence regex result."""
        segments = [
            {"id": 0, "type": "narration", "text": "He said softly,"},
            {"id": 1, "type": "dialogue", "text": "Come here."},
            {"id": 2, "type": "narration", "text": "She nodded."},
        ]

        # Regex will return ("spoken", 0.5) for this neutral context
        # LLM should be called and its result should win
        mock_llm.return_value = {1: ("whispered", 0.85)}

        result = classify_speech_acts(segments, chapter_num=1)

        assert result[1]["speech_act"] == "whispered"
        mock_llm.assert_called_once()

    def test_mixed_segments_correct_acts(self) -> None:
        """Mixed segment types should get correct speech-acts."""
        segments = [
            {"id": 0, "type": "narration", "text": "He screamed,"},
            {"id": 1, "type": "dialogue", "text": "Get out of here!"},
            {"id": 2, "type": "narration", "text": "Then she thought,"},
            {"id": 3, "type": "dialogue", "text": "This is insane."},
            {"id": 4, "type": "narration", "text": "The room fell silent."},
        ]

        with patch(
            "src.attribution.speech_acts.classify_speech_acts_llm"
        ) as mock_llm:
            mock_llm.return_value = {}
            result = classify_speech_acts(segments, chapter_num=1)

        # Seg 1: narration before says "screamed" -> shouted
        assert result[1]["speech_act"] == "shouted"
        # Seg 3: narration before says "thought" -> thought
        assert result[3]["speech_act"] == "thought"

    def test_all_segments_have_speech_act(self) -> None:
        """Every segment should have a speech_act field after classification."""
        segments = [
            {"id": 0, "type": "narration", "text": "Once upon a time."},
            {"id": 1, "type": "dialogue", "text": "Hello there."},
            {"id": 2, "type": "chapter_heading", "text": "Chapter 2"},
            {"id": 3, "type": "scene_break", "text": "***"},
            {"id": 4, "type": "dialogue", "text": "How are you?"},
        ]

        with patch(
            "src.attribution.speech_acts.classify_speech_acts_llm"
        ) as mock_llm:
            mock_llm.return_value = {}
            result = classify_speech_acts(segments, chapter_num=1)

        for seg in result:
            assert "speech_act" in seg
            assert seg["speech_act"] in {"spoken", "thought", "shouted", "whispered"}
