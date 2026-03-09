"""Tests for audio_analyzer: SNR, pitch variance, energy variance, syllable rate, scoring."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.matching.audio_analyzer import (
    PACE_TO_RATE,
    _compute_energy_variance,
    _compute_pitch_variance,
    _compute_snr,
    _estimate_syllable_rate,
    analyze_clip,
    get_target_rate,
    score_clip,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_wav(data: np.ndarray, sr: int = 24000, channels: int = 1) -> Path:
    """Write a numpy array to a temporary WAV file and return its path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    if channels == 2:
        stereo = np.column_stack([data, data])
        sf.write(tmp.name, stereo, sr)
    else:
        sf.write(tmp.name, data, sr)
    return Path(tmp.name)


def _make_tone(freq: float = 440.0, duration: float = 5.0, sr: int = 24000,
               amplitude: float = 0.5) -> np.ndarray:
    """Generate a pure sine tone."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _make_speech_like(duration: float = 5.0, sr: int = 24000) -> np.ndarray:
    """Generate a speech-like signal with amplitude modulation (syllable pulses)."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Carrier: mix of frequencies
    carrier = 0.3 * np.sin(2 * np.pi * 200 * t) + 0.2 * np.sin(2 * np.pi * 350 * t)
    # Modulator: slow amplitude envelope simulating syllables (~4 syl/s)
    modulator = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t)
    return (carrier * modulator).astype(np.float32)


def _make_voice_profile(**kwargs):
    """Build a VoiceProfile with defaults."""
    from src.attribution.models import VoiceProfile
    defaults = dict(
        pitch="medium", pace="moderate", tone="warm", accent="unknown",
        pace_style="unknown", tone_style="clear", energy="moderate",
        typical_emotion="neutral", description="Test voice",
    )
    defaults.update(kwargs)
    return VoiceProfile(**defaults)


# ---------------------------------------------------------------------------
# analyze_clip tests
# ---------------------------------------------------------------------------


class TestAnalyzeClip:
    def test_returns_required_keys(self):
        """analyze_clip returns dict with all 5 expected keys."""
        data = _make_speech_like(5.0)
        wav = _write_wav(data)
        result = analyze_clip(wav)
        assert set(result.keys()) == {
            "snr_db", "pitch_variance", "energy_variance",
            "syllable_rate", "duration_s",
        }

    def test_handles_stereo(self):
        """analyze_clip converts stereo WAV to mono without error."""
        data = _make_speech_like(5.0)
        wav = _write_wav(data, channels=2)
        result = analyze_clip(wav)
        assert "snr_db" in result
        assert result["duration_s"] > 4.0

    def test_silent_audio(self):
        """analyze_clip on silence returns near-zero metrics."""
        data = np.zeros(24000 * 5, dtype=np.float32)
        wav = _write_wav(data)
        result = analyze_clip(wav)
        # SNR should be near 0 for silent signal
        assert abs(result["snr_db"]) < 1.0
        # Variances should be 0 for constant signal
        assert result["energy_variance"] == pytest.approx(0.0, abs=1e-10)

    def test_short_clip_snr_zero(self):
        """analyze_clip on clip < 2s returns snr_db=0."""
        data = _make_tone(duration=1.0)
        wav = _write_wav(data)
        result = analyze_clip(wav)
        assert result["snr_db"] == 0.0


# ---------------------------------------------------------------------------
# _compute_snr tests
# ---------------------------------------------------------------------------


class TestComputeSNR:
    def test_positive_snr_for_clean_signal(self):
        """Clean speech-like signal should have positive SNR."""
        data = _make_speech_like(5.0)
        snr = _compute_snr(data)
        assert snr > 0.0


# ---------------------------------------------------------------------------
# _compute_energy_variance tests
# ---------------------------------------------------------------------------


class TestComputeEnergyVariance:
    def test_zero_for_constant_amplitude(self):
        """Constant-amplitude signal has near-zero energy variance."""
        data = _make_tone(duration=5.0, amplitude=0.5)
        var = _compute_energy_variance(data, 24000)
        # Pure tone has near-constant energy per frame -> very low variance
        # (slight variance from frame boundary effects is expected)
        assert var < 1e-4


# ---------------------------------------------------------------------------
# _estimate_syllable_rate tests
# ---------------------------------------------------------------------------


class TestEstimateSyllableRate:
    def test_reasonable_range_for_speech(self):
        """Speech-like signal should give syllable rate in 1-8 syl/s range."""
        data = _make_speech_like(5.0)
        rate = _estimate_syllable_rate(data, 24000)
        assert 1.0 <= rate <= 8.0


# ---------------------------------------------------------------------------
# score_clip tests
# ---------------------------------------------------------------------------


class TestScoreClip:
    def test_no_target_rate_uses_neutral(self):
        """score_clip without target_rate uses 0.5 for rate_score."""
        metrics = {
            "snr_db": 20.0,
            "pitch_variance": 1000.0,
            "energy_variance": 0.005,
            "syllable_rate": 4.0,
            "duration_s": 10.0,
        }
        score = score_clip(metrics)
        # Manual calc: snr=20/40=0.5, pitch=1000/5000=0.2, energy=0.005/0.01=0.5, rate=0.5
        # 0.4*0.5 + 0.3*0.2 + 0.2*0.5 + 0.1*0.5 = 0.2+0.06+0.1+0.05 = 0.41
        assert score == pytest.approx(0.41, abs=0.001)

    def test_matching_rate_higher_than_mismatched(self):
        """score_clip with matching target_rate > mismatched."""
        metrics = {
            "snr_db": 20.0,
            "pitch_variance": 1000.0,
            "energy_variance": 0.005,
            "syllable_rate": 4.0,
            "duration_s": 10.0,
        }
        score_match = score_clip(metrics, target_rate=4.0)
        score_mismatch = score_clip(metrics, target_rate=8.0)
        assert score_match > score_mismatch

    def test_weights(self):
        """score_clip weights are 0.4*SNR + 0.3*pitch + 0.2*energy + 0.1*rate."""
        metrics = {
            "snr_db": 40.0,   # -> 1.0
            "pitch_variance": 5000.0,  # -> 1.0
            "energy_variance": 0.01,  # -> 1.0
            "syllable_rate": 4.0,
            "duration_s": 10.0,
        }
        # No target rate -> rate_score = 0.5
        score = score_clip(metrics)
        # 0.4*1.0 + 0.3*1.0 + 0.2*1.0 + 0.1*0.5 = 0.4+0.3+0.2+0.05 = 0.95
        assert score == pytest.approx(0.95, abs=0.001)

        # With perfect rate match -> rate_score = 1.0
        score_perfect = score_clip(metrics, target_rate=4.0)
        # 0.4+0.3+0.2+0.1 = 1.0
        assert score_perfect == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# get_target_rate tests
# ---------------------------------------------------------------------------


class TestGetTargetRate:
    def test_fast_maps_to_5_5(self):
        """'fast' pace maps to 5.5 syl/s."""
        vp = _make_voice_profile(pace="fast")
        assert get_target_rate(vp) == 5.5

    def test_slow_maps_to_2_5(self):
        """'slow' pace maps to 2.5 syl/s."""
        vp = _make_voice_profile(pace="slow")
        assert get_target_rate(vp) == 2.5

    def test_unknown_maps_to_none(self):
        """'unknown' pace returns None."""
        vp = _make_voice_profile(pace="unknown")
        assert get_target_rate(vp) is None

    def test_pace_style_takes_precedence(self):
        """pace_style is tried first, pace is fallback."""
        vp = _make_voice_profile(pace="slow", pace_style="rapid")
        # pace_style="rapid" -> 6.0, not pace="slow" -> 2.5
        assert get_target_rate(vp) == 6.0

    def test_pace_style_unknown_falls_back_to_pace(self):
        """If pace_style='unknown', falls back to pace."""
        vp = _make_voice_profile(pace="fast", pace_style="unknown")
        assert get_target_rate(vp) == 5.5
