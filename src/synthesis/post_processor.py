"""Audio post-processing for speech-act adjustments.

Applies volume and speed adjustments based on speech-act type:
- spoken:    No change (baseline)
- whispered: -4.5 dB volume
- shouted:   +4.5 dB volume, 8% speed increase
- thought:   -3.0 dB volume, 7% speed decrease

Adjustments are ABSOLUTE per speech-act type, NOT cumulative with
scene mood (per user decision). Scene mood annotations are stored
for future enrichment but do not modify audio in v1.1.
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Speech-act parameter mapping
# ---------------------------------------------------------------------------

SPEECH_ACT_PARAMS: dict[str, dict[str, float]] = {
    "spoken":    {"volume_db": 0.0,  "speed_factor": 1.0},
    "whispered": {"volume_db": -4.5, "speed_factor": 1.0},
    "shouted":   {"volume_db": 4.5,  "speed_factor": 1.08},
    "thought":   {"volume_db": -3.0, "speed_factor": 0.93},
}
"""Volume and speed adjustments per speech-act type.

volume_db: Decibel adjustment (negative = quieter, positive = louder).
speed_factor: Playback speed multiplier (>1.0 = faster, <1.0 = slower).

Whispered: -4.5 dB (midpoint of -3 to -6 dB range)
Shouted:   +4.5 dB (midpoint of +3 to +6 dB range), 8% speed increase
Thought:   -3.0 dB quieter, 7% speed decrease (reflective pacing)
Spoken:    No adjustment (baseline)
"""


def get_adjustment_params(speech_act: str) -> dict[str, float]:
    """Return the adjustment parameters for a speech-act type.

    Args:
        speech_act: One of 'spoken', 'thought', 'shouted', 'whispered'.
            Unknown types default to 'spoken' (no-op).

    Returns:
        Dict with 'volume_db' and 'speed_factor' keys.
    """
    return SPEECH_ACT_PARAMS.get(speech_act, SPEECH_ACT_PARAMS["spoken"])


def apply_speech_act_adjustments(
    audio: np.ndarray,
    sample_rate: int,
    speech_act: str,
) -> tuple[np.ndarray, int]:
    """Apply volume and speed adjustments based on speech-act type.

    Args:
        audio: Audio samples as numpy array (float32, range [-1.0, 1.0]).
        sample_rate: Sample rate in Hz.
        speech_act: One of 'spoken', 'thought', 'shouted', 'whispered'.
            Unknown types default to 'spoken' (no-op).

    Returns:
        Tuple of (adjusted_audio, sample_rate). Audio is clipped to
        [-1.0, 1.0] to prevent clipping artifacts.
    """
    params = get_adjustment_params(speech_act)
    volume_db = params["volume_db"]
    speed_factor = params["speed_factor"]

    # Fast path: no adjustments needed for spoken
    if volume_db == 0.0 and speed_factor == 1.0:
        return audio, sample_rate

    # Make a copy to avoid modifying the input
    adjusted = audio.copy()

    # Volume adjustment: multiply by linear gain factor
    if volume_db != 0.0:
        gain = 10.0 ** (volume_db / 20.0)
        adjusted = adjusted * gain
        # Clip to prevent clipping artifacts
        adjusted = np.clip(adjusted, -1.0, 1.0)

    # Speed adjustment: resample using numpy interpolation
    if speed_factor != 1.0:
        original_length = len(adjusted)
        new_length = int(original_length / speed_factor)
        if new_length > 0:
            adjusted = np.interp(
                np.linspace(0, original_length - 1, new_length),
                np.arange(original_length),
                adjusted,
            ).astype(adjusted.dtype)

    logger.debug(
        "Applied %s adjustments: volume=%.1f dB, speed=%.2fx, "
        "samples %d -> %d",
        speech_act, volume_db, speed_factor,
        len(audio), len(adjusted),
    )

    return adjusted, sample_rate
