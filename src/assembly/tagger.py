"""ID3 metadata tagging for audiobook MP3 files.

Applies standard ID3 tags (title, artist, album, genre, track number,
cover art) to individual chapter MP3s and CHAP/CTOC chapter markers to
the combined audiobook MP3 for player support (e.g., Audiobookshelf).

Uses zero-padded element IDs (chp000, chp001...) to prevent chapter
ordering issues in players.
"""

from __future__ import annotations

import logging
from pathlib import Path

from mutagen.id3 import (
    APIC,
    CHAP,
    CTOC,
    TALB,
    TCON,
    TIT2,
    TPE1,
    TRCK,
    CTOCFlags,
    Encoding,
)
from mutagen.mp3 import MP3

from src.assembly.models import ChapterInfo

logger = logging.getLogger(__name__)


def _get_or_create_tags(mp3_path: Path) -> MP3:
    """Load an MP3 file, creating ID3 tags if none exist.

    Args:
        mp3_path: Path to the MP3 file.

    Returns:
        MP3 object with tags ready for modification.
    """
    audio = MP3(str(mp3_path))
    if audio.tags is None:
        audio.add_tags()
    return audio


def tag_chapter(
    mp3_path: Path,
    title: str,
    author: str,
    chapter_title: str,
    track_number: int,
    total_tracks: int,
    cover_data: bytes | None = None,
    cover_mime: str | None = None,
) -> None:
    """Apply ID3 metadata to an individual chapter MP3.

    Sets title (chapter title), artist, album (book title), genre
    (Audiobook), track number, and optional cover art.

    Args:
        mp3_path: Path to the chapter MP3 file.
        title: Book title (used as album).
        author: Author name.
        chapter_title: Chapter-specific title (e.g., "Chapter 1: The Beginning").
        track_number: 1-based track number for this chapter.
        total_tracks: Total number of chapters.
        cover_data: Optional raw cover image bytes.
        cover_mime: Optional MIME type of cover image.
    """
    audio = _get_or_create_tags(mp3_path)

    audio.tags.add(TIT2(encoding=Encoding.UTF8, text=[chapter_title]))
    audio.tags.add(TPE1(encoding=Encoding.UTF8, text=[author]))
    audio.tags.add(TALB(encoding=Encoding.UTF8, text=[title]))
    audio.tags.add(TCON(encoding=Encoding.UTF8, text=["Audiobook"]))
    audio.tags.add(TRCK(encoding=Encoding.UTF8, text=[f"{track_number}/{total_tracks}"]))

    if cover_data is not None and cover_mime is not None:
        audio.tags.add(
            APIC(
                encoding=Encoding.UTF8,
                mime=cover_mime,
                type=3,  # Front cover
                desc="Cover",
                data=cover_data,
            )
        )

    audio.save()
    logger.debug("Tagged chapter: %s", mp3_path)


def tag_audiobook(
    mp3_path: Path,
    title: str,
    author: str,
    chapters: list[ChapterInfo],
    cover_data: bytes | None = None,
    cover_mime: str | None = None,
) -> None:
    """Apply ID3 metadata with chapter markers to the combined audiobook MP3.

    Sets basic tags (title, artist, album, genre), optional cover art,
    and CHAP/CTOC frames for chapter navigation in audiobook players
    like Audiobookshelf.

    Chapter markers use zero-padded element IDs (chp000, chp001...) to
    prevent ordering issues in players.

    Args:
        mp3_path: Path to the combined audiobook MP3 file.
        title: Book title.
        author: Author name.
        chapters: List of ChapterInfo with start_ms/end_ms offsets.
        cover_data: Optional raw cover image bytes.
        cover_mime: Optional MIME type of cover image.
    """
    audio = _get_or_create_tags(mp3_path)

    # Basic tags
    audio.tags.add(TIT2(encoding=Encoding.UTF8, text=[title]))
    audio.tags.add(TPE1(encoding=Encoding.UTF8, text=[author]))
    audio.tags.add(TALB(encoding=Encoding.UTF8, text=[title]))
    audio.tags.add(TCON(encoding=Encoding.UTF8, text=["Audiobook"]))

    # Cover art
    if cover_data is not None and cover_mime is not None:
        audio.tags.add(
            APIC(
                encoding=Encoding.UTF8,
                mime=cover_mime,
                type=3,  # Front cover
                desc="Cover",
                data=cover_data,
            )
        )

    # Chapter markers (CHAP/CTOC)
    child_ids = [f"chp{i:03d}" for i in range(len(chapters))]

    # Table of contents
    audio.tags.add(
        CTOC(
            element_id="toc",
            flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
            child_element_ids=child_ids,
            sub_frames=[
                TIT2(encoding=Encoding.UTF8, text=["Table of Contents"]),
            ],
        )
    )

    # Individual chapter frames
    for i, ch in enumerate(chapters):
        chapter_title = ch.title if ch.title else f"Chapter {ch.chapter_num}"
        audio.tags.add(
            CHAP(
                element_id=f"chp{i:03d}",
                start_time=ch.start_ms,
                end_time=ch.end_ms,
                sub_frames=[
                    TIT2(encoding=Encoding.UTF8, text=[chapter_title]),
                ],
            )
        )

    audio.save()
    logger.info(
        "Tagged audiobook with %d chapter markers: %s", len(chapters), mp3_path
    )
