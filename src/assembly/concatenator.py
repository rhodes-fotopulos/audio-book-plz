"""WAV segment concatenation with boundary-aware silence insertion.

Assembles per-segment WAV files into chapter-level AudioSegments with
appropriate silence gaps between segments based on boundary type (sentence,
paragraph, scene break, chapter).
"""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from src.assembly.models import AssemblyConfig


def _get_silence_ms(
    prev_segment: dict,
    curr_segment: dict,
    config: AssemblyConfig,
) -> int:
    """Determine silence duration between two adjacent segments.

    Priority order:
    1. Chapter heading -> chapter_silence_ms
    2. Scene break (either side) -> scene_break_silence_ms
    3. Default -> paragraph_silence_ms

    The sentence_silence_ms exists in config for future use if sub-paragraph
    segments are detected.  Phase 1 segmenter produces paragraph-level
    segments, so paragraph_silence_ms is the correct default.

    Args:
        prev_segment: Metadata dict for the preceding segment.
        curr_segment: Metadata dict for the current segment.
        config: Assembly configuration with silence durations.

    Returns:
        Silence duration in milliseconds.
    """
    curr_type = curr_segment.get("type", "")
    prev_type = prev_segment.get("type", "")

    # Chapter heading gets chapter-level silence
    if curr_type == "chapter_heading":
        return config.chapter_silence_ms

    # Scene break on either side
    if prev_type == "scene_break" or curr_type == "scene_break":
        return config.scene_break_silence_ms

    # Default: paragraph-level silence
    return config.paragraph_silence_ms


def assemble_chapter(
    segment_wavs: list[tuple[dict, Path]],
    config: AssemblyConfig,
    announcement_wav: Path | None = None,
) -> AudioSegment:
    """Assemble WAV segments into a single chapter AudioSegment.

    Loads each segment WAV, inserts boundary-appropriate silence between
    segments, optionally prepends a chapter announcement, and appends
    anti-truncation padding.

    Args:
        segment_wavs: List of (segment_metadata_dict, wav_file_path) tuples
            in reading order.  Each metadata dict should have at least
            'type' and 'id' keys.
        config: Assembly configuration with silence durations.
        announcement_wav: Optional path to a chapter announcement WAV file
            (TTS-generated "Chapter X: Title").

    Returns:
        A pydub AudioSegment containing the full chapter audio ready for
        normalization and MP3 encoding.
    """
    chapter_audio = AudioSegment.empty()

    # Prepend chapter announcement if provided
    if announcement_wav is not None and Path(announcement_wav).exists():
        announcement = AudioSegment.from_wav(str(announcement_wav))
        chapter_audio += announcement
        chapter_audio += AudioSegment.silent(
            duration=config.post_announcement_silence_ms,
        )

    # Concatenate segments with silence
    prev_meta: dict | None = None

    for meta, wav_path in segment_wavs:
        segment_audio = AudioSegment.from_wav(str(wav_path))

        # Insert silence between segments (not before the first one)
        if prev_meta is not None:
            silence_ms = _get_silence_ms(prev_meta, meta, config)
            chapter_audio += AudioSegment.silent(duration=silence_ms)

        chapter_audio += segment_audio
        prev_meta = meta

    # Anti-truncation padding (prevents MP3 export end truncation)
    chapter_audio += AudioSegment.silent(
        duration=config.anti_truncation_padding_ms,
    )

    return chapter_audio
