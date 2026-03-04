"""Data models for the audio-book-plz parser."""

from dataclasses import dataclass
from enum import Enum


class SegmentType(str, Enum):
    """Type classification for a text segment."""

    NARRATION = "narration"
    DIALOGUE = "dialogue"
    CHAPTER_HEADING = "chapter_heading"
    SCENE_BREAK = "scene_break"


@dataclass
class Segment:
    """A single speech-ready text segment from an EPUB chapter."""

    id: int
    """Sequential global ID across the entire book."""

    chapter: int
    """1-based chapter number."""

    chapter_title: str
    """Extracted chapter heading, or empty string if untitled."""

    type: str
    """SegmentType value (use SegmentType enum, stored as string)."""

    text: str
    """Clean, speech-ready text."""

    char_count: int
    """Length of text in characters (len(text))."""
