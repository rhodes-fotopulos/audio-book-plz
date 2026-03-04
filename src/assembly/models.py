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
# Assembly configuration
# ---------------------------------------------------------------------------


@dataclass
class AssemblyConfig:
    """Tuneable parameters for audio assembly.

    Silence durations follow audiobook conventions.  Scene breaks use
    ~2-3 seconds per user decision (no audio cues or chimes).  Chapter
    transitions include a TTS-read announcement before content begins.
    """

    # Silence durations (milliseconds)
    sentence_silence_ms: int = 400
    """Silence between sentences within a paragraph."""

    paragraph_silence_ms: int = 900
    """Silence between paragraphs."""

    scene_break_silence_ms: int = 2500
    """Silence at scene breaks (~2-3s, no audio cue per user decision)."""

    chapter_silence_ms: int = 1500
    """Silence before chapter announcement."""

    post_announcement_silence_ms: int = 800
    """Silence after chapter announcement before chapter content."""

    # MP3 encoding
    mp3_bitrate: str = "64k"
    """CBR bitrate for spoken word MP3 (ACX/Audible standard)."""

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
