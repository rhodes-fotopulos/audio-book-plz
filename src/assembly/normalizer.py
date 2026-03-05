"""LUFS loudness normalization for consistent audiobook volume.

Uses pyloudnorm (ITU-R BS.1770-4) to measure and normalize audio to a
target LUFS level.  Applied per-chapter (not per-segment) to avoid
measurement instability on short clips.
"""

from __future__ import annotations

import logging

import numpy as np
import pyloudnorm as pyln
from pydub import AudioSegment

logger = logging.getLogger(__name__)

# pyloudnorm requires at least 400ms (one gating block) for valid measurement
_MIN_DURATION_MS = 400


def normalize_audio(
    audio_segment: AudioSegment,
    target_lufs: float = -19.0,
) -> AudioSegment:
    """Normalize an AudioSegment to a target LUFS loudness.

    Converts the pydub AudioSegment to a numpy array, measures integrated
    loudness via pyloudnorm, applies gain to hit the target LUFS, and
    converts back to an AudioSegment.

    Edge cases:
    - Silent audio (LUFS = -inf): returned unchanged.
    - Audio shorter than 400ms: returned unchanged (insufficient for
      ITU-R BS.1770 gating blocks).

    Args:
        audio_segment: Input audio to normalize.
        target_lufs: Target loudness in LUFS (default -19.0, audiobook
            standard range is -23 to -18).

    Returns:
        Normalized AudioSegment with the same sample rate and channels.
    """
    # Guard: too short for valid LUFS measurement
    if len(audio_segment) < _MIN_DURATION_MS:
        logger.warning(
            "Audio too short (%dms < %dms) for LUFS measurement — skipping normalization",
            len(audio_segment),
            _MIN_DURATION_MS,
        )
        return audio_segment

    # Convert to float32 numpy array in [-1.0, 1.0] range
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
    max_val = float(2 ** (audio_segment.sample_width * 8 - 1))
    samples = samples / max_val

    # Handle stereo (reshape to 2D) — TTS output is mono but be safe
    if audio_segment.channels > 1:
        samples = samples.reshape((-1, audio_segment.channels))

    # Measure current loudness
    meter = pyln.Meter(audio_segment.frame_rate)
    current_lufs = meter.integrated_loudness(samples)

    # Silent audio — nothing to normalize
    if current_lufs == float("-inf"):
        logger.debug("Audio is silent (LUFS = -inf) — skipping normalization")
        return audio_segment

    # Apply loudness normalization
    normalized = pyln.normalize.loudness(samples, current_lufs, target_lufs)

    # Clip to [-1.0, 1.0] and convert back to int16
    normalized = np.clip(normalized, -1.0, 1.0)

    # Flatten back if we reshaped for stereo
    if normalized.ndim > 1:
        normalized = normalized.flatten()

    normalized_int = (normalized * (2**15 - 1)).astype(np.int16)

    logger.debug(
        "Normalized: %.1f LUFS -> %.1f LUFS (gain: %+.1f dB)",
        current_lufs,
        target_lufs,
        target_lufs - current_lufs,
    )

    return audio_segment._spawn(normalized_int.tobytes())
