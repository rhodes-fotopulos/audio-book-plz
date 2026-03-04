"""Tests for audio post-processing speech-act adjustments.

Covers:
- spoken: no change (no-op)
- whispered: volume reduced
- shouted: volume increased (before clipping)
- thought: slower and quieter
- shouted speed increase (fewer samples)
- clipping prevention
- unknown speech-act defaults to spoken
"""

from __future__ import annotations

import numpy as np
import pytest

from src.synthesis.post_processor import (
    SPEECH_ACT_PARAMS,
    apply_speech_act_adjustments,
    get_adjustment_params,
)


class TestSpokenNoChange:
    """Tests for spoken speech-act (no-op)."""

    def test_spoken_no_change(self) -> None:
        """Input audio should equal output audio for 'spoken'."""
        audio = np.random.uniform(-0.5, 0.5, 1000).astype(np.float32)
        result, sr = apply_speech_act_adjustments(audio, 24000, "spoken")
        np.testing.assert_array_equal(result, audio)
        assert sr == 24000

    def test_spoken_same_reference(self) -> None:
        """Spoken should return the exact same array (no copy)."""
        audio = np.ones(100, dtype=np.float32)
        result, _ = apply_speech_act_adjustments(audio, 24000, "spoken")
        # Should be the same object (no unnecessary copy)
        assert result is audio


class TestWhisperedVolume:
    """Tests for whispered speech-act volume reduction."""

    def test_whispered_volume_reduced(self) -> None:
        """Output max amplitude should be less than input for 'whispered'."""
        audio = np.ones(1000, dtype=np.float32) * 0.8
        result, sr = apply_speech_act_adjustments(audio, 24000, "whispered")

        assert result.max() < audio.max()
        assert sr == 24000

    def test_whispered_correct_db_reduction(self) -> None:
        """Whispered should reduce by approximately -4.5 dB."""
        audio = np.ones(1000, dtype=np.float32)
        result, _ = apply_speech_act_adjustments(audio, 24000, "whispered")

        # -4.5 dB = 10^(-4.5/20) = ~0.596
        expected_gain = 10.0 ** (-4.5 / 20.0)
        np.testing.assert_allclose(result.max(), expected_gain, atol=0.01)


class TestShoutedVolume:
    """Tests for shouted speech-act volume increase."""

    def test_shouted_volume_increased(self) -> None:
        """Output amplitude should be greater than input for 'shouted' (before clipping)."""
        # Use a quiet signal to avoid clipping
        audio = np.ones(1000, dtype=np.float32) * 0.3
        result, sr = apply_speech_act_adjustments(audio, 24000, "shouted")

        assert result.max() > audio.max()
        assert sr == 24000

    def test_shouted_speed_increase(self) -> None:
        """Shouted output should have fewer samples (speed > 1.0)."""
        audio = np.ones(10000, dtype=np.float32) * 0.3
        result, _ = apply_speech_act_adjustments(audio, 24000, "shouted")

        # speed_factor = 1.08, so output should be shorter
        assert len(result) < len(audio)

        # Expected length: 10000 / 1.08 ≈ 9259
        expected_length = int(10000 / 1.08)
        assert abs(len(result) - expected_length) <= 1


class TestThoughtAdjustments:
    """Tests for thought speech-act (slower and quieter)."""

    def test_thought_slower_and_quieter(self) -> None:
        """Thought output should be longer (slower) and quieter."""
        audio = np.ones(10000, dtype=np.float32) * 0.5
        result, _ = apply_speech_act_adjustments(audio, 24000, "thought")

        # Quieter
        assert result.max() < audio.max()

        # Slower (speed_factor < 1.0 means more samples)
        assert len(result) > len(audio)

    def test_thought_correct_speed(self) -> None:
        """Thought speed factor should produce ~7% more samples."""
        audio = np.ones(10000, dtype=np.float32) * 0.5
        result, _ = apply_speech_act_adjustments(audio, 24000, "thought")

        # speed_factor = 0.93, so output = 10000 / 0.93 ≈ 10753
        expected_length = int(10000 / 0.93)
        assert abs(len(result) - expected_length) <= 1


class TestClippingPrevention:
    """Tests for audio clipping prevention."""

    def test_clipping_prevention(self) -> None:
        """Loud audio + shouted adjustment should not exceed [-1.0, 1.0]."""
        # Audio already at full volume
        audio = np.ones(1000, dtype=np.float32)
        result, _ = apply_speech_act_adjustments(audio, 24000, "shouted")

        assert result.max() <= 1.0
        assert result.min() >= -1.0

    def test_clipping_prevention_negative(self) -> None:
        """Negative loud audio should also be clipped."""
        audio = np.ones(1000, dtype=np.float32) * -0.9
        result, _ = apply_speech_act_adjustments(audio, 24000, "shouted")

        assert result.min() >= -1.0
        assert result.max() <= 1.0


class TestUnknownSpeechAct:
    """Tests for unknown speech-act types."""

    def test_unknown_speech_act_defaults_to_spoken(self) -> None:
        """Unknown type should be treated as 'spoken' (no-op)."""
        audio = np.random.uniform(-0.5, 0.5, 1000).astype(np.float32)
        result, sr = apply_speech_act_adjustments(audio, 24000, "unknown_type")

        np.testing.assert_array_equal(result, audio)
        assert sr == 24000


class TestGetAdjustmentParams:
    """Tests for get_adjustment_params helper."""

    def test_spoken_params(self) -> None:
        """Spoken params should have zero adjustments."""
        params = get_adjustment_params("spoken")
        assert params["volume_db"] == 0.0
        assert params["speed_factor"] == 1.0

    def test_whispered_params(self) -> None:
        """Whispered params should have negative volume."""
        params = get_adjustment_params("whispered")
        assert params["volume_db"] < 0
        assert params["speed_factor"] == 1.0

    def test_shouted_params(self) -> None:
        """Shouted params should have positive volume and speed > 1."""
        params = get_adjustment_params("shouted")
        assert params["volume_db"] > 0
        assert params["speed_factor"] > 1.0

    def test_thought_params(self) -> None:
        """Thought params should have negative volume and speed < 1."""
        params = get_adjustment_params("thought")
        assert params["volume_db"] < 0
        assert params["speed_factor"] < 1.0

    def test_unknown_defaults_to_spoken(self) -> None:
        """Unknown type should return spoken params."""
        params = get_adjustment_params("totally_unknown")
        assert params == SPEECH_ACT_PARAMS["spoken"]
