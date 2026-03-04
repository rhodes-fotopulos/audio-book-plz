"""MP3 encoding for chapter and combined audiobook output.

Uses pydub with ffmpeg backend for MP3 encoding.  Provides FFmpeg
validation, per-chapter MP3 export, and combined audiobook assembly
from chapter MP3s.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from pydub import AudioSegment


def check_ffmpeg() -> None:
    """Verify that FFmpeg is available in PATH.

    FFmpeg is required by pydub for MP3 encoding and decoding.  This
    should be called once at the start of assembly to fail early with
    a clear error message.

    Raises:
        RuntimeError: If ffmpeg is not found in PATH.
    """
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg is required for MP3 encoding but was not found in PATH.\n"
            "Install with: brew install ffmpeg"
        )


def export_chapter_mp3(
    audio: AudioSegment,
    output_path: Path,
    bitrate: str = "192k",
    sample_rate: int = 44100,
) -> Path:
    """Export an AudioSegment to MP3 with ACX-compliant settings.

    Forces mono output at 44.1kHz 192kbps CBR for ACX compliance.

    Args:
        audio: Chapter AudioSegment to encode.
        output_path: Destination path for the MP3 file.
        bitrate: CBR bitrate string (default "192k" for ACX).
        sample_rate: Output sample rate (default 44100 for ACX).

    Returns:
        The output_path for chaining.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio.export(
        str(output_path),
        format="mp3",
        bitrate=bitrate,
        parameters=["-ac", "1", "-ar", str(sample_rate)],
    )

    return output_path


def combine_chapter_mp3s(
    chapter_mp3_paths: list[Path],
    output_path: Path,
    bitrate: str = "192k",
    sample_rate: int = 44100,
) -> Path:
    """Concatenate chapter MP3s into a single audiobook MP3.

    Loads each chapter MP3 sequentially and concatenates.  MP3s are
    much smaller than raw audio, so this is memory-safe even for long
    books.  Appends 100ms silence at the end to prevent truncation.

    Args:
        chapter_mp3_paths: Ordered list of chapter MP3 file paths.
        output_path: Destination path for the combined audiobook MP3.
        bitrate: CBR bitrate string (default "192k" for ACX).
        sample_rate: Output sample rate (default 44100 for ACX).

    Returns:
        The output_path for chaining.
    """
    combined = AudioSegment.empty()

    for mp3_path in chapter_mp3_paths:
        chapter = AudioSegment.from_mp3(str(mp3_path))
        combined += chapter

    # Anti-truncation padding
    combined += AudioSegment.silent(duration=100)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    combined.export(
        str(output_path),
        format="mp3",
        bitrate=bitrate,
        parameters=["-ac", "1", "-ar", str(sample_rate)],
    )

    return output_path
