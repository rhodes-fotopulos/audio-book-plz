"""Tests for opinionated extraction prompt variant (PROF-01).

Covers:
- get_extraction_prompt returns original when opinionated=False
- get_extraction_prompt appends OPINIONATED_ADDENDUM when opinionated=True
- Opinionated prompt contains banned-word list and "NEVER"
- _extract_chunk uses get_extraction_prompt result (system_prompt parameter)
- extract_characters_from_chapter uses different cache key for opinionated mode
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.attribution.extractor import (
    EXTRACTION_SYSTEM_PROMPT,
    OPINIONATED_ADDENDUM,
    get_extraction_prompt,
    _extract_chunk,
    extract_characters_from_chapter,
)
from src.attribution.models import (
    CharacterProfile,
    ChapterExtractionResult,
    VoiceProfile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_VP = VoiceProfile(
    pitch="low",
    pace="slow",
    tone="gruff",
    accent="unknown",
    pace_style="measured",
    tone_style="gravelly",
    energy="restrained",
    typical_emotion="weary",
    description="A slow, gravelly voice with weary patience",
)


def _make_profile(name: str = "TestChar") -> CharacterProfile:
    return CharacterProfile(
        name=name,
        aliases=[],
        gender="male",
        age_range="middle-aged",
        voice_profile=_DEFAULT_VP,
        personality_traits=["stoic"],
        description="A test character",
        is_named=True,
    )


# ---------------------------------------------------------------------------
# Tests: get_extraction_prompt
# ---------------------------------------------------------------------------


class TestGetExtractionPrompt:
    def test_non_opinionated_returns_original(self):
        """get_extraction_prompt(False) returns EXTRACTION_SYSTEM_PROMPT unchanged."""
        result = get_extraction_prompt(opinionated=False)
        assert result == EXTRACTION_SYSTEM_PROMPT

    def test_opinionated_includes_addendum(self):
        """get_extraction_prompt(True) includes OPINIONATED_ADDENDUM."""
        result = get_extraction_prompt(opinionated=True)
        assert OPINIONATED_ADDENDUM in result
        assert result.startswith(EXTRACTION_SYSTEM_PROMPT)

    def test_opinionated_contains_never_and_banned_words(self):
        """Opinionated prompt contains 'NEVER' and banned word 'moderate'."""
        result = get_extraction_prompt(opinionated=True)
        assert "NEVER" in result
        assert "moderate" in result

    def test_opinionated_addendum_bans_expected_words(self):
        """OPINIONATED_ADDENDUM contains all expected banned words."""
        banned = ["moderate", "medium", "average", "normal", "standard", "typical", "ordinary"]
        for word in banned:
            assert word in OPINIONATED_ADDENDUM, f"Missing banned word: {word}"


# ---------------------------------------------------------------------------
# Tests: _extract_chunk system_prompt parameter
# ---------------------------------------------------------------------------


class TestExtractChunkSystemPrompt:
    @patch("src.attribution.extractor.call_llm_structured")
    def test_uses_provided_system_prompt(self, mock_llm):
        """_extract_chunk passes system_prompt to call_llm_structured."""
        mock_llm.return_value = ChapterExtractionResult(characters=[_make_profile()])
        custom_prompt = "Custom system prompt for testing"
        _extract_chunk("some text", "Chapter 1", system_prompt=custom_prompt)
        mock_llm.assert_called_once()
        assert mock_llm.call_args[0][0] == custom_prompt


# ---------------------------------------------------------------------------
# Tests: extract_characters_from_chapter opinionated cache key
# ---------------------------------------------------------------------------


class TestExtractCharactersOpinionatedCache:
    @patch("src.attribution.extractor.call_llm_structured")
    @patch("src.attribution.extractor.check_cache")
    @patch("src.attribution.extractor.write_cache")
    @patch("src.attribution.extractor.get_cache_key")
    def test_opinionated_uses_different_cache_key(
        self, mock_get_key, mock_write, mock_check, mock_llm
    ):
        """extract_characters_from_chapter uses 'extraction_v3_opinionated' cache key when opinionated=True."""
        mock_check.return_value = None
        mock_llm.return_value = ChapterExtractionResult(characters=[])
        mock_get_key.return_value = "test_key"

        with tempfile.TemporaryDirectory() as tmpdir:
            extract_characters_from_chapter(
                "some chapter text", 1, Path(tmpdir), opinionated=True
            )

        # Check the cache key prefix used
        mock_get_key.assert_called_once()
        call_args = mock_get_key.call_args
        assert call_args[0][1] == "extraction_v3_opinionated"

    @patch("src.attribution.extractor.call_llm_structured")
    @patch("src.attribution.extractor.check_cache")
    @patch("src.attribution.extractor.write_cache")
    @patch("src.attribution.extractor.get_cache_key")
    def test_non_opinionated_uses_standard_cache_key(
        self, mock_get_key, mock_write, mock_check, mock_llm
    ):
        """extract_characters_from_chapter uses 'extraction_v3' cache key when opinionated=False."""
        mock_check.return_value = None
        mock_llm.return_value = ChapterExtractionResult(characters=[])
        mock_get_key.return_value = "test_key"

        with tempfile.TemporaryDirectory() as tmpdir:
            extract_characters_from_chapter(
                "some chapter text", 1, Path(tmpdir), opinionated=False
            )

        mock_get_key.assert_called_once()
        call_args = mock_get_key.call_args
        assert call_args[0][1] == "extraction_v3"
