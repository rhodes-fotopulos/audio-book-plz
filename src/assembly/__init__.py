"""Audio assembly pipeline for Phase 5.

Concatenates per-segment WAV files into chapter-level and full-book MP3s
with appropriate silence spacing, LUFS normalization, and ID3 metadata.
"""

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
]
