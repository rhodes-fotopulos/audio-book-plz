"""TTS synthesis package for audio-book-plz (Phase 4).

Provides Chatterbox TTS engine, checkpoint/resume, and progress
reporting for overnight audiobook synthesis runs.
"""

from src.synthesis.checkpoint import (
    create_checkpoint,
    get_pending_segments,
    load_checkpoint,
    mark_completed,
    mark_failed,
    save_checkpoint,
    validate_checkpoint,
)
from src.synthesis.models import SegmentResult, SynthesisConfig, SynthesisStats
from src.synthesis.synthesizer import run_synthesis
from src.synthesis.tts_engine import TTSEngine

__all__ = [
    "TTSEngine",
    "SynthesisConfig",
    "SegmentResult",
    "SynthesisStats",
    "run_synthesis",
    "create_checkpoint",
    "save_checkpoint",
    "load_checkpoint",
    "validate_checkpoint",
    "get_pending_segments",
    "mark_completed",
    "mark_failed",
]
