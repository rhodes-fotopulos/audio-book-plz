"""Voice-character matching package for Phase 3.

Matches characters from the Phase 2 character registry to real human
voices from the LibriTTS-P dataset using LLM trait comparison with
embedding similarity fallback.

Public API:
    load_speaker_index  — Load and merge LibriTTS-P speaker annotations
    filter_candidates   — Filter speakers by gender and age
    classify_cast       — Classify characters as major/minor by dialogue count
"""

from src.matching.speaker_index import (
    classify_cast,
    filter_candidates,
    load_speaker_index,
)

__all__ = [
    "load_speaker_index",
    "filter_candidates",
    "classify_cast",
]
