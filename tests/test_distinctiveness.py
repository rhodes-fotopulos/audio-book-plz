"""Tests for LLM-based distinctiveness pass (PROF-02).

Covers:
- DistinctivenessResult model validation
- run_distinctiveness_pass returns modified profiles (mocked LLM)
- run_distinctiveness_pass falls back to originals on character count mismatch
- run_distinctiveness_pass uses cache with key "distinctiveness_v1"
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.attribution.models import (
    CharacterProfile,
    DistinctivenessResult,
    VoiceProfile,
)
from src.attribution.distinctiveness import run_distinctiveness_pass


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


def _make_profile(name: str, **vp_overrides) -> CharacterProfile:
    vp_dict = _DEFAULT_VP.model_dump()
    vp_dict.update(vp_overrides)
    return CharacterProfile(
        name=name,
        aliases=[],
        gender="male",
        age_range="middle-aged",
        voice_profile=VoiceProfile(**vp_dict),
        personality_traits=["stoic"],
        description=f"Character {name}",
        is_named=True,
    )


# ---------------------------------------------------------------------------
# Tests: DistinctivenessResult model
# ---------------------------------------------------------------------------


class TestDistinctivenessResult:
    def test_validates_correctly(self):
        """DistinctivenessResult validates with characters list and modifications list."""
        profiles = [_make_profile("Alice"), _make_profile("Bob")]
        result = DistinctivenessResult(
            characters=profiles,
            modifications=["Changed Alice's pitch from low to high"],
        )
        assert len(result.characters) == 2
        assert len(result.modifications) == 1

    def test_empty_modifications(self):
        """DistinctivenessResult accepts empty modifications list."""
        result = DistinctivenessResult(characters=[], modifications=[])
        assert len(result.characters) == 0
        assert len(result.modifications) == 0


# ---------------------------------------------------------------------------
# Tests: run_distinctiveness_pass
# ---------------------------------------------------------------------------


class TestRunDistinctivenessPass:
    @patch("src.attribution.distinctiveness.write_cache")
    @patch("src.attribution.distinctiveness.check_cache")
    @patch("src.attribution.distinctiveness.call_llm_structured")
    def test_returns_modified_profiles(self, mock_llm, mock_check, mock_write):
        """run_distinctiveness_pass returns LLM-modified profiles with modifications logged."""
        original = [_make_profile("Alice"), _make_profile("Bob")]

        # LLM returns modified profiles
        modified_alice = _make_profile("Alice", pitch="high", energy="animated")
        modified_bob = _make_profile("Bob", pitch="low", energy="restrained")
        mock_llm.return_value = DistinctivenessResult(
            characters=[modified_alice, modified_bob],
            modifications=["Changed Alice's pitch from low to high"],
        )
        mock_check.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_distinctiveness_pass(original, Path(tmpdir))

        assert len(result) == 2
        # Alice should have updated voice profile
        alice = next(c for c in result if c.name == "Alice")
        assert alice.voice_profile.pitch == "high"
        assert alice.voice_profile.energy == "animated"

    @patch("src.attribution.distinctiveness.write_cache")
    @patch("src.attribution.distinctiveness.check_cache")
    @patch("src.attribution.distinctiveness.call_llm_structured")
    def test_fallback_on_count_mismatch(self, mock_llm, mock_check, mock_write):
        """run_distinctiveness_pass returns originals if LLM returns wrong character count."""
        original = [_make_profile("Alice"), _make_profile("Bob")]

        # LLM returns only one character (mismatch)
        mock_llm.return_value = DistinctivenessResult(
            characters=[_make_profile("Alice", pitch="high")],
            modifications=["Dropped Bob"],
        )
        mock_check.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_distinctiveness_pass(original, Path(tmpdir))

        # Should fall back to originals
        assert len(result) == 2
        alice = next(c for c in result if c.name == "Alice")
        assert alice.voice_profile.pitch == "low"  # Original, not modified

    @patch("src.attribution.distinctiveness.write_cache")
    @patch("src.attribution.distinctiveness.check_cache")
    @patch("src.attribution.distinctiveness.call_llm_structured")
    @patch("src.attribution.distinctiveness.get_cache_key")
    def test_uses_cache_with_correct_key(self, mock_get_key, mock_llm, mock_check, mock_write):
        """run_distinctiveness_pass uses cache with key prefix 'distinctiveness_v1'."""
        original = [_make_profile("Alice")]
        mock_check.return_value = None
        mock_llm.return_value = DistinctivenessResult(
            characters=[_make_profile("Alice")],
            modifications=[],
        )
        mock_get_key.return_value = "test_key"

        with tempfile.TemporaryDirectory() as tmpdir:
            run_distinctiveness_pass(original, Path(tmpdir))

        mock_get_key.assert_called_once()
        call_args = mock_get_key.call_args
        assert call_args[0][1] == "distinctiveness_v1"

    @patch("src.attribution.distinctiveness.write_cache")
    @patch("src.attribution.distinctiveness.check_cache")
    @patch("src.attribution.distinctiveness.call_llm_structured")
    def test_llm_returns_none_fallback(self, mock_llm, mock_check, mock_write):
        """run_distinctiveness_pass returns originals if LLM returns None."""
        original = [_make_profile("Alice"), _make_profile("Bob")]
        mock_llm.return_value = None
        mock_check.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            result = run_distinctiveness_pass(original, Path(tmpdir))

        assert len(result) == 2
        assert result[0].name == "Alice"
