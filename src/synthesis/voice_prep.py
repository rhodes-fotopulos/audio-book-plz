"""Voice reference preparation for TTS synthesis.

Prepares voice reference clips for Qwen3-TTS by:
1. Computing an RMS-based SNR score (no external dependencies)
2. Looking up the normalized transcript from LibriTTS-R
3. Computing actual duration from the audio data

The ``VoiceReference`` dataclass bundles clip path, transcript,
duration, and SNR score for each character's voice.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Voice reference data model
# ---------------------------------------------------------------------------


@dataclass
class VoiceReference:
    """Prepared voice reference for a single character.

    Bundles the clip path, transcript (for Qwen3-TTS ``ref_text``),
    actual duration, and optional SNR quality score.
    """

    clip_path: str
    """Absolute or relative path to the WAV clip."""

    transcript: str | None
    """Normalized transcript of the clip, or None if unavailable."""

    duration_s: float
    """Actual audio duration in seconds."""

    snr_score: float | None
    """RMS-based SNR in dB, or None if computation failed."""


# ---------------------------------------------------------------------------
# SNR computation (RMS-based, no external dependencies)
# ---------------------------------------------------------------------------


def _compute_snr_rms(audio_path: str | Path) -> float | None:
    """Compute a simple RMS-based SNR for a WAV file.

    Splits audio into short frames, classifies frames with RMS below
    1% of the maximum frame RMS as "noise", and computes SNR as
    ``20 * log10(rms_signal / rms_noise)`` dB.

    Returns:
        SNR in dB, or None if the computation fails (e.g. empty audio).
    """
    import numpy as np

    try:
        import soundfile as sf

        audio, sr = sf.read(str(audio_path))
    except Exception as exc:
        logger.warning("Could not read audio for SNR: %s — %s", audio_path, exc)
        return None

    if len(audio) == 0:
        logger.warning("Empty audio file: %s", audio_path)
        return None

    # Ensure 1-D
    if audio.ndim > 1:
        audio = audio[:, 0]

    # Frame-based RMS (30ms frames at the file's sample rate)
    frame_size = int(sr * 0.03)
    if frame_size == 0:
        return None

    num_frames = len(audio) // frame_size
    if num_frames == 0:
        return None

    frames = audio[: num_frames * frame_size].reshape(num_frames, frame_size)
    frame_rms = np.sqrt(np.mean(frames**2, axis=1))

    max_rms = np.max(frame_rms)
    if max_rms == 0:
        logger.warning("All-silence audio: %s", audio_path)
        return None

    # Threshold: frames below 1% of max RMS are "noise"
    noise_threshold = max_rms * 0.01
    noise_mask = frame_rms < noise_threshold
    signal_mask = ~noise_mask

    if not np.any(signal_mask) or not np.any(noise_mask):
        # All signal or all noise — can't compute meaningful SNR
        # If all signal (clean studio audio), that's good
        if np.all(signal_mask):
            return 60.0  # Very clean — return high SNR
        return None

    rms_signal = np.mean(frame_rms[signal_mask])
    rms_noise = np.mean(frame_rms[noise_mask])

    if rms_noise == 0:
        return 60.0

    snr = 20 * math.log10(rms_signal / rms_noise)
    return round(snr, 1)


# ---------------------------------------------------------------------------
# Voice reference preparation
# ---------------------------------------------------------------------------


def prepare_voice_reference(
    speaker_id: str,
    clip_path: str,
    libritts_root: Path,
) -> VoiceReference:
    """Prepare a single voice reference with SNR and transcript.

    Args:
        speaker_id: LibriTTS-P speaker ID.
        clip_path: Relative path to the clip within libritts_root.
        libritts_root: Root directory of LibriTTS-R audio files.

    Returns:
        Populated ``VoiceReference`` with clip, transcript, duration, SNR.
    """
    import numpy as np

    abs_path = libritts_root / clip_path

    # Compute SNR
    snr = _compute_snr_rms(abs_path)
    if snr is not None and snr < 15:
        logger.warning(
            "Low SNR (%.1f dB) for speaker %s clip %s — audio may be noisy",
            snr,
            speaker_id,
            clip_path,
        )

    # Look up transcript
    transcript = None
    txt_path = abs_path.with_suffix(".normalized.txt")
    if txt_path.exists():
        try:
            transcript = txt_path.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.warning("Could not read transcript: %s — %s", txt_path, exc)

    # Compute actual duration from audio data
    duration_s = 0.0
    try:
        import soundfile as sf

        info = sf.info(str(abs_path))
        duration_s = info.duration
    except Exception:
        # Fallback: estimate from file size
        try:
            size = abs_path.stat().st_size
            duration_s = size / (24000 * 2)
        except Exception:
            pass

    return VoiceReference(
        clip_path=str(abs_path),
        transcript=transcript,
        duration_s=duration_s,
        snr_score=snr,
    )


def prepare_all_voice_references(
    voice_map: "VoiceMap",  # noqa: F821
    libritts_root: Path,
) -> dict[str, VoiceReference]:
    """Prepare voice references for all characters in a voice map.

    Args:
        voice_map: Complete voice map with narrator and character
            assignments.
        libritts_root: Root directory of LibriTTS-R audio files.

    Returns:
        Dict keyed by character name (including ``'narrator'``).
    """
    refs: dict[str, VoiceReference] = {}
    warnings = 0
    transcripts_found = 0

    # Narrator
    ref = prepare_voice_reference(
        voice_map.narrator.speaker_id,
        voice_map.narrator.clip_path,
        libritts_root,
    )
    refs["narrator"] = ref
    if ref.transcript:
        transcripts_found += 1
    if ref.snr_score is not None and ref.snr_score < 15:
        warnings += 1

    # Characters
    for assignment in voice_map.characters:
        ref = prepare_voice_reference(
            assignment.speaker_id,
            assignment.clip_path,
            libritts_root,
        )
        refs[assignment.character_name] = ref
        if ref.transcript:
            transcripts_found += 1
        if ref.snr_score is not None and ref.snr_score < 15:
            warnings += 1

    total = len(refs)
    logger.info(
        "Voice references prepared: %d total, %d with transcripts, %d SNR warnings",
        total,
        transcripts_found,
        warnings,
    )

    return refs
