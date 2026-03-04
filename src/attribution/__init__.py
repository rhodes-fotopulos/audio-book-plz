"""Public API for the audio-book-plz attribution package.

Exposes the three-stage attribution pipeline:
  1. extract_all_characters — per-chapter character extraction via LLM
  2. merge_characters — three-stage alias deduplication
  3. attribute_all_segments — speaker assignment for every segment

Also exposes LLM model lifecycle functions:
  - select_model — choose 14B or 8B based on available RAM
  - preload_model — pin model in Ollama memory with keep_alive=-1
  - get_active_model — return the currently loaded model name
  - unload_model — evict model from Ollama with keep_alive=0
"""

from src.attribution.attributor import attribute_all_segments
from src.attribution.cache import clear_cache
from src.attribution.extractor import extract_all_characters
from src.attribution.llm_client import (
    get_active_model,
    preload_model,
    select_model,
    unload_model,
)
from src.attribution.merger import merge_characters

__all__ = [
    "extract_all_characters",
    "merge_characters",
    "attribute_all_segments",
    "select_model",
    "preload_model",
    "get_active_model",
    "unload_model",
    "clear_cache",
]
