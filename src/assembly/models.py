"""Data models for Phase 5 audio assembly.

Defines configuration, chapter info, EPUB metadata, and run-level statistics
for the audio assembly pipeline.

All models are dataclasses for simplicity and consistency with Phase 1
parser models and Phase 4 synthesis models.  No external dependencies at
import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Pause configuration (Phase 9 — Gaussian-randomized timing)
# ---------------------------------------------------------------------------


@dataclass
class PauseConfig:
    """Gaussian-randomized pause timing for natural narrator feel.

    Each boundary type has a mean, standard deviation, and min/max clamp.
    Durations are sampled from a Gaussian distribution clipped to
    [min, max] range, producing organic timing variation.

    Paragraph breaks use 0.3-0.6s range per user decision.  Speaker
    changes are slightly longer than paragraphs.  Scene breaks and
    chapter breaks are the longest pauses.
    """

    # Sentence break (within paragraph)
    sentence_mean_ms: float = 350.0
    sentence_std_ms: float = 50.0
    sentence_min_ms: float = 250.0
    sentence_max_ms: float = 500.0

    # Paragraph break (0.3-0.6s per user decision)
    paragraph_mean_ms: float = 450.0
    paragraph_std_ms: float = 75.0
    paragraph_min_ms: float = 300.0
    paragraph_max_ms: float = 600.0

    # Speaker change (slightly longer than paragraph)
    speaker_change_mean_ms: float = 600.0
    speaker_change_std_ms: float = 100.0
    speaker_change_min_ms: float = 400.0
    speaker_change_max_ms: float = 900.0

    # Scene break (longer, organic)
    scene_break_mean_ms: float = 2200.0
    scene_break_std_ms: float = 300.0
    scene_break_min_ms: float = 1800.0
    scene_break_max_ms: float = 3000.0

    # Chapter break (longest)
    chapter_mean_ms: float = 3500.0
    chapter_std_ms: float = 400.0
    chapter_min_ms: float = 2800.0
    chapter_max_ms: float = 4500.0

    # Post-announcement silence (fixed — rhythmic consistency)
    post_announcement_silence_ms: int = 800

    # Crossfade duration for segment boundaries (5-10ms range)
    crossfade_ms: int = 8
    """Fade-in/fade-out applied to each segment edge to eliminate clicks."""


# ---------------------------------------------------------------------------
# Assembly configuration
# ---------------------------------------------------------------------------


@dataclass
class AssemblyConfig:
    """Tuneable parameters for audio assembly.

    Silence durations follow audiobook conventions.  Scene breaks use
    ~2-3 seconds per user decision (no audio cues or chimes).  Chapter
    transitions include a TTS-read announcement before content begins.
    """

    # Phase 9: Gaussian-randomized pause timing
    pause_config: PauseConfig = field(default_factory=PauseConfig)
    """Gaussian-randomized pause timing configuration."""

    # Legacy fixed silence durations (deprecated — use pause_config instead)
    sentence_silence_ms: int = 400
    """Deprecated: use pause_config.sentence_mean_ms. Kept for backward compatibility."""

    paragraph_silence_ms: int = 900
    """Deprecated: use pause_config.paragraph_mean_ms. Kept for backward compatibility."""

    scene_break_silence_ms: int = 2500
    """Deprecated: use pause_config.scene_break_mean_ms. Kept for backward compatibility."""

    chapter_silence_ms: int = 1500
    """Deprecated: use pause_config.chapter_mean_ms. Kept for backward compatibility."""

    post_announcement_silence_ms: int = 800
    """Silence after chapter announcement before chapter content."""

    # MP3 encoding
    mp3_bitrate: str = "192k"
    """CBR bitrate for MP3 export (ACX spec: 192kbps or higher)."""

    export_sample_rate: int = 44100
    """Sample rate for MP3 export (ACX spec: 44.1kHz)."""

    # Loudness normalization
    target_lufs: float = -19.0
    """LUFS normalization target (audiobook standard range -23 to -18)."""

    # Anti-truncation
    anti_truncation_padding_ms: int = 100
    """Silence appended before MP3 export to prevent end truncation."""


# ---------------------------------------------------------------------------
# Chapter info (for CHAP/CTOC frames)
# ---------------------------------------------------------------------------


@dataclass
class ChapterInfo:
    """Metadata for a single chapter in the assembled audiobook."""

    chapter_num: int
    """1-based chapter number."""

    title: str
    """Chapter title (from segment data)."""

    start_ms: int
    """Start offset in combined audiobook (milliseconds, for CHAP frame)."""

    end_ms: int
    """End offset in combined audiobook (milliseconds, for CHAP frame)."""

    segment_count: int
    """Number of segments in this chapter."""

    duration_ms: int
    """Chapter audio duration in milliseconds."""

    mp3_path: str
    """Path to the chapter MP3 file."""


# ---------------------------------------------------------------------------
# EPUB metadata
# ---------------------------------------------------------------------------


@dataclass
class EpubMetadata:
    """Metadata extracted from an EPUB file for ID3 tagging."""

    title: str
    """Book title from EPUB Dublin Core metadata."""

    author: str
    """Author name from EPUB Dublin Core metadata."""

    cover_data: bytes | None = None
    """Raw cover image bytes (JPEG/PNG), or None if not found."""

    cover_mime: str | None = None
    """MIME type of cover image (e.g., 'image/jpeg'), or None."""


# ---------------------------------------------------------------------------
# Assembly statistics
# ---------------------------------------------------------------------------


@dataclass
class AssemblyStats:
    """Aggregate statistics for the assembly completion summary."""

    total_chapters: int = 0
    total_segments: int = 0
    total_duration_ms: int = 0
    chapter_mp3s_created: int = 0
    audiobook_created: bool = False
    announcements_generated: int = 0
