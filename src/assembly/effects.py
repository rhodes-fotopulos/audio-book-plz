"""Pedalboard mastering effects chain with A/B validation.

Applies a transparent mastering chain (noise gate, compressor, high-pass EQ
at 80Hz, limiter) to chapter audio.  Measures LUFS and peak dB before and
after processing and flags regressions.

Phase 9 upgrade: professional post-processing for ACX-grade output.
"""

from __future__ import annotations

import logging

import numpy as np
import pyloudnorm as pyln
from pedalboard import (
    Compressor,
    HighpassFilter,
    Limiter,
    NoiseGate,
    Pedalboard,
)
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Minimum audio length in ms for valid LUFS measurement
_MIN_LUFS_MS = 400

# ACX peak ceiling: -3dB = 10^(-3/20) ~= 0.7079
_ACX_PEAK_CEILING = 10 ** (-3.0 / 20.0)


def create_mastering_chain() -> Pedalboard:
    """Build the pedalboard mastering effects chain.

    Order: NoiseGate -> Compressor -> HighpassFilter(80Hz) -> Limiter(-3dB).

    Parameters follow user decisions:
    - Noise gate: aggressive (threshold -40dB, ratio 10, fast attack)
    - Compressor: moderate (threshold -20dB, ratio 3:1)
    - High-pass: 80Hz cutoff (removes rumble)
    - Limiter: -3dB threshold (ACX peak compliance)

    Returns:
        Pedalboard instance with 4 effects in correct order.
    """
    return Pedalboard([
        NoiseGate(
            threshold_db=-40.0,
            ratio=10.0,
            attack_ms=1.0,
            release_ms=100.0,
        ),
        Compressor(
            threshold_db=-20.0,
            ratio=3.0,
            attack_ms=10.0,
            release_ms=150.0,
        ),
        HighpassFilter(cutoff_frequency_hz=80.0),
        Limiter(
            threshold_db=-3.0,
            release_ms=100.0,
        ),
    ])


def measure_audio_metrics(
    audio: np.ndarray,
    sample_rate: int,
) -> dict:
    """Measure LUFS loudness and peak dB of an audio array.

    Args:
        audio: Float32 numpy array in [-1.0, 1.0] range.
        sample_rate: Audio sample rate in Hz.

    Returns:
        Dict with ``lufs`` (float) and ``peak_db`` (float) keys.
    """
    # Peak dB
    peak_abs = float(np.max(np.abs(audio)))
    if peak_abs > 0:
        peak_db = 20.0 * np.log10(peak_abs)
    else:
        peak_db = float("-inf")

    # LUFS via pyloudnorm
    lufs = float("-inf")
    duration_samples = len(audio) if audio.ndim == 1 else audio.shape[0]
    duration_ms = (duration_samples / sample_rate) * 1000
    if duration_ms >= _MIN_LUFS_MS:
        try:
            meter = pyln.Meter(sample_rate)
            lufs = meter.integrated_loudness(audio)
        except Exception as exc:
            logger.debug("LUFS measurement failed: %s", exc)

    return {
        "lufs": lufs,
        "peak_db": peak_db,
    }


def apply_effects_chain(
    chapter_audio: AudioSegment,
    board: Pedalboard,
) -> tuple[AudioSegment, dict]:
    """Apply the mastering effects chain to a chapter AudioSegment.

    Converts to float32 numpy, measures before metrics, applies pedalboard,
    measures after metrics, checks for regressions, and converts back.

    Args:
        chapter_audio: Input chapter AudioSegment.
        board: Pedalboard mastering chain from ``create_mastering_chain()``.

    Returns:
        Tuple of (processed AudioSegment, metrics dict).
        The metrics dict contains ``before_lufs``, ``before_peak_db``,
        ``after_lufs``, ``after_peak_db`` keys.
    """
    if len(chapter_audio) == 0:
        return chapter_audio, {
            "before_lufs": float("-inf"),
            "before_peak_db": float("-inf"),
            "after_lufs": float("-inf"),
            "after_peak_db": float("-inf"),
        }

    sample_rate = chapter_audio.frame_rate

    # Convert AudioSegment to float32 numpy array in [-1.0, 1.0]
    # Same pattern as normalizer.py (lines 55-57)
    samples = np.array(chapter_audio.get_array_of_samples(), dtype=np.float32)
    max_val = float(2 ** (chapter_audio.sample_width * 8 - 1))
    audio_f32 = samples / max_val

    # Handle stereo (reshape to 2D)
    if chapter_audio.channels > 1:
        audio_f32 = audio_f32.reshape((-1, chapter_audio.channels))

    # Measure before metrics
    before_metrics = measure_audio_metrics(audio_f32, sample_rate)

    # Apply pedalboard effects chain
    # pedalboard expects shape (num_samples,) for mono or (num_samples, channels) for stereo
    processed = board(audio_f32, sample_rate)

    # Enforce hard peak ceiling at -3dB for ACX compliance.
    # pedalboard's Limiter includes makeup gain, so we clip explicitly.
    processed = np.clip(processed, -_ACX_PEAK_CEILING, _ACX_PEAK_CEILING)

    # Measure after metrics
    after_metrics = measure_audio_metrics(processed, sample_rate)

    # Check for regressions
    if (
        after_metrics["peak_db"] != float("-inf")
        and before_metrics["peak_db"] != float("-inf")
        and after_metrics["peak_db"] > before_metrics["peak_db"] + 1.0
    ):
        logger.warning(
            "Effects chain regression detected: peak increased from %.1fdB to %.1fdB",
            before_metrics["peak_db"],
            after_metrics["peak_db"],
        )

    if (
        after_metrics["lufs"] != float("-inf")
        and before_metrics["lufs"] != float("-inf")
        and before_metrics["lufs"] - after_metrics["lufs"] > 6.0
    ):
        logger.warning(
            "Effects chain regression detected: LUFS dropped from %.1f to %.1f (>6dB)",
            before_metrics["lufs"],
            after_metrics["lufs"],
        )

    # Clip to [-1.0, 1.0] and convert back to int16
    # Same pattern as normalizer.py (lines 76-82)
    processed = np.clip(processed, -1.0, 1.0)

    # Flatten if stereo
    if processed.ndim > 1:
        processed = processed.flatten()

    processed_int = (processed * (2**15 - 1)).astype(np.int16)

    # Build metrics dict
    metrics = {
        "before_lufs": before_metrics["lufs"],
        "before_peak_db": before_metrics["peak_db"],
        "after_lufs": after_metrics["lufs"],
        "after_peak_db": after_metrics["peak_db"],
    }

    return chapter_audio._spawn(processed_int.tobytes()), metrics
