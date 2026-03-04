"""Reference audio clip selection from LibriTTS-R.

Selects the best (longest) WAV file for each assigned speaker to use
as Chatterbox TTS voice-cloning reference. WAV file size at constant
24kHz/16-bit/mono is directly proportional to duration.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Minimum file size for a usable reference clip (~5 seconds at 24kHz mono 16-bit)
_MIN_CLIP_BYTES = 120_000


def select_reference_clip(speaker_id: str, libritts_root: Path) -> str | None:
    """Select the longest WAV file for a speaker from LibriTTS-R.

    Searches all splits (train-clean-100, train-clean-360, etc.) for
    the speaker directory and picks the largest WAV file as a proxy
    for the longest duration.

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

    # Collect all WAV files across all chapters/splits for this speaker
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

    if best_size < _MIN_CLIP_BYTES:
        logger.warning(
            "Best clip for speaker %s is only %d bytes (~%.1fs) — "
            "may be too short for voice cloning",
            speaker_id,
            best_size,
            best_size / (24000 * 2),  # 24kHz, 16-bit = 2 bytes/sample
        )

    # Return relative path from libritts_root
    rel_path = best_wav.relative_to(libritts_root)
    logger.info("Selected clip for speaker %s: %s (%d bytes)", speaker_id, rel_path, best_size)
    return str(rel_path)
