"""Audio assembly pipeline for Phase 5.

Concatenates per-segment WAV files into chapter-level and full-book MP3s
with appropriate silence spacing, LUFS normalization, and ID3 metadata.
"""

from src.assembly.concatenator import assemble_chapter
from src.assembly.metadata import extract_epub_metadata
from src.assembly.models import (
    AssemblyConfig,
    AssemblyStats,
    ChapterInfo,
    EpubMetadata,
)

__all__ = [
    "AssemblyConfig",
    "AssemblyStats",
    "ChapterInfo",
    "EpubMetadata",
    "assemble_chapter",
    "extract_epub_metadata",
]
