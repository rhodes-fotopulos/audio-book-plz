"""Audio signal analysis for expressiveness-aware clip selection.

Computes SNR, pitch variance, energy variance, and syllable rate from
WAV files using numpy + soundfile (no librosa dependency).  These metrics
feed into a composite expressiveness score used by clip_selector.py to
pick the best reference clip for voice cloning.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import soundfile as sf

from src.attribution.models import VoiceProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pace-to-rate mapping (CLIP-02)
# ---------------------------------------------------------------------------

PACE_TO_RATE: dict[str, float | None] = {
    "fast": 5.5,
    "rapid": 6.0,
    "clipped": 5.5,
    "moderate": 4.0,
    "measured": 3.5,
    "slow": 2.5,
    "deliberate": 3.0,
    "languid": 2.0,
    "unknown": None,
}


# ---------------------------------------------------------------------------
# Core analysis functions
# ---------------------------------------------------------------------------


def analyze_clip(wav_path: Path) -> dict:
    """Compute expressiveness metrics for a WAV clip.

    Args:
        wav_path: Path to a WAV file.

    Returns:
        Dict with keys: snr_db, pitch_variance, energy_variance,
        syllable_rate, duration_s.
    """
    data, sr = sf.read(wav_path)

    # Convert stereo to mono
    if data.ndim > 1:
        data = data.mean(axis=1)

    duration_s = len(data) / sr

    # For very short clips (<2s), skip SNR estimation (Pitfall 3)
    if duration_s < 2.0:
        snr_db = 0.0
    else:
        snr_db = _compute_snr(data)

    return {
        "snr_db": snr_db,
        "pitch_variance": _compute_pitch_variance(data, sr),
        "energy_variance": _compute_energy_variance(data, sr),
        "syllable_rate": _estimate_syllable_rate(data, sr),
        "duration_s": duration_s,
    }


def _compute_snr(data: np.ndarray) -> float:
    """Estimate SNR using signal RMS vs noise floor.

    Bottom 10% of sorted amplitudes approximates the noise floor.
    Returns SNR in decibels. Clamps noise floor to 1e-10 minimum.
    """
    sorted_abs = np.sort(np.abs(data))
    n = len(sorted_abs)
    noise_floor = sorted_abs[: n // 10]

    signal_rms = np.sqrt(np.mean(data**2))
    noise_rms = (
        np.sqrt(np.mean(noise_floor**2)) if len(noise_floor) > 0 else 1e-10
    )

    # Clamp to avoid log(0) and handle silent signals
    noise_rms = max(noise_rms, 1e-10)
    signal_rms = max(signal_rms, 1e-10)

    return float(20 * np.log10(signal_rms / noise_rms))


def _compute_pitch_variance(data: np.ndarray, sr: int) -> float:
    """Estimate F0 variance via autocorrelation on overlapping frames.

    Uses 30ms frames with 10ms hop.  Silent frames (max amplitude < 0.01)
    are skipped.  Returns 0.0 if fewer than 3 voiced frames detected.
    """
    frame_size = int(0.03 * sr)  # 30ms frames
    hop = int(0.01 * sr)  # 10ms hop
    f0s: list[float] = []

    for start in range(0, len(data) - frame_size, hop):
        frame = data[start : start + frame_size]
        if np.max(np.abs(frame)) < 0.01:
            continue

        corr = np.correlate(frame, frame, mode="full")
        corr = corr[len(corr) // 2 :]

        # Search for first autocorrelation peak in valid F0 range
        min_lag = int(sr / 500)  # 500 Hz max
        max_lag = int(sr / 60)  # 60 Hz min
        if max_lag > len(corr):
            continue

        segment = corr[min_lag:max_lag]
        if len(segment) == 0:
            continue

        peak_idx = int(np.argmax(segment)) + min_lag
        if corr[peak_idx] > 0.3 * corr[0]:  # confidence threshold
            f0s.append(sr / peak_idx)

    return float(np.var(f0s)) if len(f0s) > 2 else 0.0


def _compute_energy_variance(data: np.ndarray, sr: int) -> float:
    """Compute variance of frame-level RMS energy.

    Uses 30ms frames with 10ms hop.
    """
    frame_size = int(0.03 * sr)
    hop = int(0.01 * sr)
    energies: list[float] = []

    for start in range(0, len(data) - frame_size, hop):
        frame = data[start : start + frame_size]
        energies.append(float(np.sqrt(np.mean(frame**2))))

    return float(np.var(energies)) if energies else 0.0


def _estimate_syllable_rate(data: np.ndarray, sr: int) -> float:
    """Estimate syllables per second via energy envelope peak counting.

    Computes RMS envelope (20ms frames, 10ms hop), smooths with 5-sample
    moving average, counts peaks above 0.5*mean threshold.
    """
    frame_size = int(0.02 * sr)  # 20ms
    hop = int(0.01 * sr)
    envelope: list[float] = []

    for start in range(0, len(data) - frame_size, hop):
        envelope.append(float(np.sqrt(np.mean(data[start : start + frame_size] ** 2))))

    envelope_arr = np.array(envelope)
    if len(envelope_arr) < 3:
        return 0.0

    # Smooth envelope
    kernel = np.ones(5) / 5
    smoothed = np.convolve(envelope_arr, kernel, mode="same")

    # Count peaks above threshold (syllable nuclei)
    threshold = np.mean(smoothed) * 0.5
    peaks = 0
    above = False
    for val in smoothed:
        if val > threshold and not above:
            peaks += 1
            above = True
        elif val < threshold:
            above = False

    duration = len(data) / sr
    return peaks / duration if duration > 0 else 0.0


# ---------------------------------------------------------------------------
# Composite scoring (CLIP-01)
# ---------------------------------------------------------------------------


def score_clip(metrics: dict, target_rate: float | None = None) -> float:
    """Compute expressiveness composite score.

    Weights: 0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match.
    All components normalized to 0-1 range before weighting.
    """
    # Normalize SNR: 0-40 dB range mapped to 0-1
    snr_score = min(max(metrics["snr_db"], 0), 40) / 40

    # Normalize pitch variance: higher = more expressive
    pitch_score = min(metrics["pitch_variance"] / 5000, 1.0)

    # Normalize energy variance: higher = more dynamic
    energy_score = min(metrics["energy_variance"] / 0.01, 1.0)

    # Rate match: 1.0 = perfect match, 0.0 = worst mismatch
    if target_rate is not None and metrics["syllable_rate"] > 0:
        rate_diff = abs(metrics["syllable_rate"] - target_rate)
        rate_score = max(0, 1.0 - rate_diff / 5.0)
    else:
        rate_score = 0.5  # neutral when no target

    return 0.4 * snr_score + 0.3 * pitch_score + 0.2 * energy_score + 0.1 * rate_score


# ---------------------------------------------------------------------------
# Pace mapping (CLIP-02)
# ---------------------------------------------------------------------------


def get_target_rate(voice_profile: VoiceProfile) -> float | None:
    """Get target syllable rate from character's pace descriptors.

    Tries pace_style first (more specific), falls back to pace.
    Returns None for 'unknown' (neutral rate matching).
    """
    rate = PACE_TO_RATE.get(voice_profile.pace_style.lower())
    if rate is not None:
        return rate
    # pace_style was "unknown" or not mapped -- fall back to pace
    return PACE_TO_RATE.get(voice_profile.pace.lower())
