"""Tests for voice_overrides.yaml loading and application (PROF-03).

Covers:
- load_voice_overrides returns None when no file exists
- load_voice_overrides parses valid YAML with voice_profile and speaker_id fields
- load_voice_overrides returns None for empty YAML file
- apply_voice_overrides updates matching character's voice_profile fields
- apply_voice_overrides is case-insensitive on character name matching
- apply_voice_overrides leaves non-matching characters unchanged
- apply_voice_overrides handles speaker_id field in override
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.attribution.models import CharacterProfile, VoiceProfile
from src.voice_overrides import (
    VoiceOverride,
    VoiceOverrides,
    apply_voice_overrides,
    load_voice_overrides,
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
# Tests: load_voice_overrides
# ---------------------------------------------------------------------------


class TestLoadVoiceOverrides:
    def test_returns_none_when_no_file(self):
        """load_voice_overrides returns None when no voice_overrides.yaml exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = load_voice_overrides(Path(tmpdir))
        assert result is None

    def test_parses_valid_yaml(self):
        """load_voice_overrides parses valid YAML with voice_profile and speaker_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "voice_overrides.yaml"
            yaml_path.write_text(
                'characters:\n'
                '  "Elizabeth Bennet":\n'
                '    voice_profile:\n'
                '      pitch: "high"\n'
                '      pace: "fast"\n'
                '  "Mr. Darcy":\n'
                '    speaker_id: "7335"\n',
                encoding="utf-8",
            )
            result = load_voice_overrides(Path(tmpdir))

        assert result is not None
        assert "Elizabeth Bennet" in result.characters
        assert result.characters["Elizabeth Bennet"].voice_profile == {
            "pitch": "high",
            "pace": "fast",
        }
        assert result.characters["Mr. Darcy"].speaker_id == "7335"

    def test_returns_none_for_empty_yaml(self):
        """load_voice_overrides returns None for empty YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_path = Path(tmpdir) / "voice_overrides.yaml"
            yaml_path.write_text("", encoding="utf-8")
            result = load_voice_overrides(Path(tmpdir))
        assert result is None


# ---------------------------------------------------------------------------
# Tests: apply_voice_overrides
# ---------------------------------------------------------------------------


class TestApplyVoiceOverrides:
    def test_updates_matching_character(self):
        """apply_voice_overrides updates matching character's voice_profile fields."""
        characters = [_make_profile("Alice"), _make_profile("Bob")]
        overrides = VoiceOverrides(
            characters={
                "Alice": VoiceOverride(voice_profile={"pitch": "high", "energy": "animated"}),
            }
        )

        result = apply_voice_overrides(characters, overrides)
        alice = next(c for c in result if c.name == "Alice")
        assert alice.voice_profile.pitch == "high"
        assert alice.voice_profile.energy == "animated"
        # Non-overridden fields preserved
        assert alice.voice_profile.pace == "slow"

    def test_case_insensitive_matching(self):
        """apply_voice_overrides is case-insensitive on character name matching."""
        characters = [_make_profile("Elizabeth Bennet")]
        overrides = VoiceOverrides(
            characters={
                "elizabeth bennet": VoiceOverride(
                    voice_profile={"pitch": "high"}
                ),
            }
        )

        result = apply_voice_overrides(characters, overrides)
        assert result[0].voice_profile.pitch == "high"

    def test_leaves_non_matching_unchanged(self):
        """apply_voice_overrides leaves non-matching characters unchanged."""
        characters = [_make_profile("Alice"), _make_profile("Bob")]
        overrides = VoiceOverrides(
            characters={
                "Charlie": VoiceOverride(voice_profile={"pitch": "high"}),
            }
        )

        result = apply_voice_overrides(characters, overrides)
        assert result[0].voice_profile.pitch == "low"
        assert result[1].voice_profile.pitch == "low"

    def test_handles_speaker_id(self):
        """apply_voice_overrides handles speaker_id field in override."""
        characters = [_make_profile("Alice")]
        overrides = VoiceOverrides(
            characters={
                "Alice": VoiceOverride(speaker_id="7335"),
            }
        )

        # speaker_id is stored in override but doesn't affect voice_profile
        # It's consumed later by the matching pipeline
        result = apply_voice_overrides(characters, overrides)
        assert result[0].voice_profile.pitch == "low"  # unchanged
