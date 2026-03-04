"""Public API for the audio-book-plz attribution package.

Exposes the three-stage attribution pipeline:
  1. extract_all_characters — per-chapter character extraction via LLM
  2. merge_characters — three-stage alias deduplication
  3. attribute_all_segments — speaker assignment for every segment
"""

from src.attribution.attributor import attribute_all_segments
from src.attribution.cache import clear_cache
from src.attribution.extractor import extract_all_characters
from src.attribution.llm_client import unload_model
from src.attribution.merger import merge_characters

__all__ = [
    "extract_all_characters",
    "merge_characters",
    "attribute_all_segments",
    "unload_model",
    "clear_cache",
]
