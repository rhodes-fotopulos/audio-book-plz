"""WAV segment concatenation with Gaussian-randomized pauses and crossfades.

Assembles per-segment WAV files into chapter-level AudioSegments with
Gaussian-randomized silence gaps between segments based on boundary type
(sentence, paragraph, speaker change, scene break, chapter).  Applies
fade-in/fade-out crossfades at segment edges to eliminate audible clicks.

Phase 9 upgrade: replaces fixed silence durations with organic,
slightly-varied timing for a natural narrator feel.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
from pydub import AudioSegment

from src.assembly.models import AssemblyConfig, PauseConfig

logger = logging.getLogger(__name__)


def gaussian_pause_ms(
    mean: float,
    std: float,
    min_val: float,
    max_val: float,
) -> int:
    """Sample a pause duration from a clipped Gaussian distribution.

    Args:
        mean: Mean pause duration in milliseconds.
        std: Standard deviation in milliseconds.
        min_val: Minimum allowed duration (clamp floor).
        max_val: Maximum allowed duration (clamp ceiling).

    Returns:
        Integer pause duration in milliseconds, clipped to [min_val, max_val].
    """
    value = np.random.normal(mean, std)
    return int(np.clip(value, min_val, max_val))


def _get_silence_ms(
    prev_segment: dict,
    curr_segment: dict,
    pause_config: PauseConfig,
) -> int:
    """Determine silence duration between two adjacent segments.

    Uses Gaussian-randomized durations based on boundary type.

    Priority order:
    1. Chapter heading -> chapter break pause
    2. Scene break (either side) -> scene break pause
    3. Speaker change -> speaker change pause
    4. Default -> paragraph pause

    Args:
        prev_segment: Metadata dict for the preceding segment.
        curr_segment: Metadata dict for the current segment.
        pause_config: Gaussian pause configuration.

    Returns:
        Silence duration in milliseconds (Gaussian-sampled, clipped).
    """
    curr_type = curr_segment.get("type", "")
    prev_type = prev_segment.get("type", "")

    # Chapter heading gets chapter-level silence
    if curr_type == "chapter_heading":
        return gaussian_pause_ms(
            pause_config.chapter_mean_ms,
            pause_config.chapter_std_ms,
            pause_config.chapter_min_ms,
            pause_config.chapter_max_ms,
        )

    # Scene break on either side
    if prev_type == "scene_break" or curr_type == "scene_break":
        return gaussian_pause_ms(
            pause_config.scene_break_mean_ms,
            pause_config.scene_break_std_ms,
            pause_config.scene_break_min_ms,
            pause_config.scene_break_max_ms,
        )

    # Speaker change detection
    prev_speaker = prev_segment.get("speaker", "narrator")
    curr_speaker = curr_segment.get("speaker", "narrator")
    if prev_speaker != curr_speaker:
        return gaussian_pause_ms(
            pause_config.speaker_change_mean_ms,
            pause_config.speaker_change_std_ms,
            pause_config.speaker_change_min_ms,
            pause_config.speaker_change_max_ms,
        )

    # Default: paragraph-level silence
    return gaussian_pause_ms(
        pause_config.paragraph_mean_ms,
        pause_config.paragraph_std_ms,
        pause_config.paragraph_min_ms,
        pause_config.paragraph_max_ms,
    )


def _apply_crossfade(
    segment_audio: AudioSegment,
    fade_ms: int,
) -> AudioSegment:
    """Apply fade-in and fade-out to a segment's edges.

    Guards against segments shorter than 2 * fade_ms by clamping
    the fade duration.

    Args:
        segment_audio: Audio segment to apply fades to.
        fade_ms: Desired fade duration in milliseconds.

    Returns:
        AudioSegment with fade-in and fade-out applied.
    """
    if len(segment_audio) == 0:
        return segment_audio

    # Clamp fade to at most half the segment length
    safe_fade = min(fade_ms, len(segment_audio) // 2)
    if safe_fade <= 0:
        return segment_audio

    return segment_audio.fade_in(safe_fade).fade_out(safe_fade)


def assemble_chapter(
    segment_wavs: list[tuple[dict, Path]],
    config: AssemblyConfig,
    announcement_wav: Path | None = None,
) -> AudioSegment:
    """Assemble WAV segments into a single chapter AudioSegment.

    Loads each segment WAV, applies fade-in/fade-out crossfades at
    segment edges, inserts Gaussian-randomized boundary-appropriate
    silence between segments, optionally prepends a chapter announcement,
    and appends anti-truncation padding.

    Args:
        segment_wavs: List of (segment_metadata_dict, wav_file_path) tuples
            in reading order.  Each metadata dict should have at least
            'type' and 'id' keys.
        config: Assembly configuration with pause timing.
        announcement_wav: Optional path to a chapter announcement WAV file
            (TTS-generated "Chapter X: Title").

    Returns:
        A pydub AudioSegment containing the full chapter audio ready for
        effects processing, normalization, and MP3 encoding.
    """
    pause_config = config.pause_config
    fade_ms = pause_config.crossfade_ms
    chapter_audio = AudioSegment.empty()

    # Prepend chapter announcement if provided
    if announcement_wav is not None and Path(announcement_wav).exists():
        announcement = AudioSegment.from_wav(str(announcement_wav))
        chapter_audio += announcement
        chapter_audio += AudioSegment.silent(
            duration=pause_config.post_announcement_silence_ms,
        )

    # Concatenate segments with Gaussian-randomized silence and crossfades
    prev_meta: dict | None = None

    for meta, wav_path in segment_wavs:
        segment_audio = AudioSegment.from_wav(str(wav_path))

        # Apply crossfade to segment edges
        segment_audio = _apply_crossfade(segment_audio, fade_ms)

        # Insert silence between segments (not before the first one)
        if prev_meta is not None:
            silence_ms = _get_silence_ms(prev_meta, meta, pause_config)
            chapter_audio += AudioSegment.silent(duration=silence_ms)

        chapter_audio += segment_audio
        prev_meta = meta

    # Anti-truncation padding (prevents MP3 export end truncation)
    chapter_audio += AudioSegment.silent(
        duration=config.anti_truncation_padding_ms,
    )

    return chapter_audio
