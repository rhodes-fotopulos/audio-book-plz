"""Tests for pedalboard mastering effects chain.

Covers:
- Chain has exactly 4 effects in correct order
- apply_effects_chain returns AudioSegment and metrics dict
- Limiter reduces peak below threshold
- measure_audio_metrics returns expected keys
"""

from __future__ import annotations

import numpy as np
from pedalboard import Compressor, HighpassFilter, Limiter, NoiseGate
from pydub import AudioSegment

from src.assembly.effects import (
    apply_effects_chain,
    create_mastering_chain,
    measure_audio_metrics,
)


def _make_sine_audio(
    freq: float = 440.0,
    duration_ms: int = 1000,
    sample_rate: int = 24000,
    amplitude: float = 0.8,
) -> AudioSegment:
    """Generate a sine wave AudioSegment for testing."""
    num_samples = int(sample_rate * duration_ms / 1000)
    t = np.linspace(0, duration_ms / 1000, num_samples, endpoint=False)
    samples = (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    # Convert to int16
    samples_int16 = (samples * (2**15 - 1)).astype(np.int16)
    audio = AudioSegment(
        data=samples_int16.tobytes(),
        sample_width=2,
        frame_rate=sample_rate,
        channels=1,
    )
    return audio


def test_create_mastering_chain_has_four_effects():
    """Chain should have exactly 4 effects in correct order."""
    board = create_mastering_chain()
    assert len(board) == 4, f"Expected 4 effects, got {len(board)}"
    assert isinstance(board[0], NoiseGate), f"Effect 0 should be NoiseGate, got {type(board[0])}"
    assert isinstance(board[1], Compressor), f"Effect 1 should be Compressor, got {type(board[1])}"
    assert isinstance(board[2], HighpassFilter), f"Effect 2 should be HighpassFilter, got {type(board[2])}"
    assert isinstance(board[3], Limiter), f"Effect 3 should be Limiter, got {type(board[3])}"


def test_apply_effects_returns_audio_and_metrics():
    """Processing should return an AudioSegment and metrics dict."""
    audio = _make_sine_audio(duration_ms=1000)
    board = create_mastering_chain()

    result_audio, metrics = apply_effects_chain(audio, board)

    assert isinstance(result_audio, AudioSegment), f"Expected AudioSegment, got {type(result_audio)}"
    assert isinstance(metrics, dict), f"Expected dict, got {type(metrics)}"
    assert "before_lufs" in metrics
    assert "after_lufs" in metrics
    assert "before_peak_db" in metrics
    assert "after_peak_db" in metrics


def test_effects_chain_reduces_peak():
    """Limiter at -3dB should reduce peak of loud audio."""
    # Create loud audio (amplitude near 1.0 = 0 dBFS)
    loud_audio = _make_sine_audio(amplitude=0.95, duration_ms=1000)
    board = create_mastering_chain()

    _, metrics = apply_effects_chain(loud_audio, board)

    # After limiter at -3dB, peak should be <= -3dB (with some tolerance)
    assert metrics["after_peak_db"] <= -2.5, (
        f"Expected peak <= -2.5dB after limiter, got {metrics['after_peak_db']:.1f}dB"
    )


def test_measure_audio_metrics_keys():
    """Metrics dict should have 'lufs' and 'peak_db' keys."""
    audio = np.random.randn(24000).astype(np.float32) * 0.1
    metrics = measure_audio_metrics(audio, 24000)

    assert "lufs" in metrics, "Missing 'lufs' key"
    assert "peak_db" in metrics, "Missing 'peak_db' key"
    assert isinstance(metrics["lufs"], float)
    assert isinstance(metrics["peak_db"], float)


def test_empty_audio_passthrough():
    """Empty AudioSegment should pass through unchanged."""
    empty = AudioSegment.empty()
    board = create_mastering_chain()

    result, metrics = apply_effects_chain(empty, board)
    assert len(result) == 0
    assert metrics["before_lufs"] == float("-inf")
