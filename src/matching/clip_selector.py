"""Reference audio clip selection from LibriTTS-R.

Selects the best WAV file for each assigned speaker to use as TTS
voice-cloning reference.  Targets 10-15 second clips (optimal for
Qwen3-TTS) and can bundle the corresponding normalized transcript.

WAV file size at constant 24kHz/16-bit/mono is directly proportional
to duration: ``duration_s = file_size / (24000 * 2)``.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum file size for a usable reference clip (~5 seconds at 24kHz mono 16-bit)
_MIN_CLIP_BYTES = 120_000

# Target duration range for voice reference clips
_TARGET_DURATION_S = 12.5  # midpoint of 10-15s range
_MIN_DURATION_S = 5.0
_MAX_DURATION_S = 25.0  # longer clips can cause generation hangs

# Bytes per second at 24kHz, 16-bit mono (+ ~44-byte WAV header, negligible)
_BYTES_PER_SECOND = 24000 * 2


def _duration_from_size(file_size: int) -> float:
    """Estimate WAV duration from file size (24kHz, 16-bit mono)."""
    return file_size / _BYTES_PER_SECOND


def select_reference_clip(speaker_id: str, libritts_root: Path) -> str | None:
    """Select the best WAV file for a speaker from LibriTTS-R.

    Targets clips closest to 12.5 seconds (midpoint of 10-15s range)
    for optimal Qwen3-TTS voice cloning.  Falls back to the longest
    clip under 25 seconds if no clips are in the ideal range.

    Args:
        speaker_id: LibriTTS-P speaker ID (e.g., '7335').
        libritts_root: Root directory of LibriTTS-R audio files.

    Returns:
        Relative path from libritts_root to the selected WAV file,
        or None if the speaker is not found in the audio files.
    """
    # Search across all splits for this speaker
    speaker_dirs = list(libritts_root.glob(f"*/{speaker_id}"))
    if not speaker_dirs:
        logger.warning("Speaker %s not found in %s", speaker_id, libritts_root)
        return None

    # Collect all WAV files with duration estimates
    candidates: list[tuple[Path, float, float]] = []  # (path, duration, score)

    for speaker_dir in speaker_dirs:
        for wav_file in speaker_dir.rglob("*.wav"):
            size = wav_file.stat().st_size
            if size < _MIN_CLIP_BYTES:
                continue

            duration = _duration_from_size(size)

            # Filter out too-short or too-long clips
            if duration < _MIN_DURATION_S or duration > _MAX_DURATION_S:
                continue

            # Score: prefer clips closest to target duration
            score = 1.0 / (1.0 + abs(duration - _TARGET_DURATION_S))
            candidates.append((wav_file, duration, score))

    if not candidates:
        # Fallback: try ANY clip for this speaker (original behavior)
        best_wav: Path | None = None
        best_size = 0
        for speaker_dir in speaker_dirs:
            for wav_file in speaker_dir.rglob("*.wav"):
                size = wav_file.stat().st_size
                if size > best_size:
                    best_size = size
                    best_wav = wav_file

        if best_wav is None:
            logger.warning("No WAV files found for speaker %s", speaker_id)
            return None

        duration = _duration_from_size(best_size)
        logger.warning(
            "No clips in %.0f-%.0fs range for speaker %s — "
            "using longest available (%.1fs)",
            _MIN_DURATION_S,
            _MAX_DURATION_S,
            speaker_id,
            duration,
        )
        rel_path = best_wav.relative_to(libritts_root)
        logger.info(
            "Selected clip for speaker %s: %s (%.1fs)",
            speaker_id,
            rel_path,
            duration,
        )
        return str(rel_path)

    # Pick the highest-scoring candidate
    candidates.sort(key=lambda c: c[2], reverse=True)
    best_path, best_duration, _ = candidates[0]

    rel_path = best_path.relative_to(libritts_root)
    logger.info(
        "Selected clip for speaker %s: %s (%.1fs, target %.1fs)",
        speaker_id,
        rel_path,
        best_duration,
        _TARGET_DURATION_S,
    )
    return str(rel_path)


def select_reference_clip_with_transcript(
    speaker_id: str,
    libritts_root: Path,
) -> tuple[str | None, str | None]:
    """Select a reference clip and its normalized transcript.

    LibriTTS-R naming convention:
    ``{speaker}_{chapter}_{utt_start}_{utt_end}.wav`` has a matching
    ``{speaker}_{chapter}_{utt_start}_{utt_end}.normalized.txt`` in the
    same directory.

    Args:
        speaker_id: LibriTTS-P speaker ID.
        libritts_root: Root directory of LibriTTS-R audio files.

    Returns:
        Tuple of ``(clip_relative_path, transcript_text)`` or
        ``(clip_relative_path, None)`` if transcript not found.
        Returns ``(None, None)`` if speaker not found.
    """
    clip_rel = select_reference_clip(speaker_id, libritts_root)
    if clip_rel is None:
        return None, None

    # Look for corresponding normalized transcript
    clip_path = libritts_root / clip_rel
    txt_path = clip_path.with_suffix(".normalized.txt")

    transcript = None
    if txt_path.exists():
        try:
            transcript = txt_path.read_text(encoding="utf-8").strip()
            logger.debug(
                "Found transcript for speaker %s: %s",
                speaker_id,
                transcript[:80] + "..." if len(transcript) > 80 else transcript,
            )
        except Exception as exc:
            logger.warning(
                "Could not read transcript for speaker %s: %s", speaker_id, exc
            )
    else:
        logger.debug(
            "No normalized transcript found for speaker %s at %s",
            speaker_id,
            txt_path,
        )

    return clip_rel, transcript
