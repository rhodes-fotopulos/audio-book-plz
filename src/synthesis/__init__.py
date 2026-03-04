"""TTS synthesis package for audio-book-plz.

Provides multi-engine TTS support (Qwen3-TTS via MLX, Chatterbox via PyTorch),
checkpoint/resume with engine versioning, text chunking, voice reference
preparation, and progress reporting for overnight audiobook synthesis runs.
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
from src.synthesis.chunker import chunk_text_chatterbox, chunk_text_qwen
from src.synthesis.engine_base import AudioResult, TTSEngineBase
from src.synthesis.engine_factory import create_engine
from src.synthesis.models import SegmentResult, SynthesisConfig, SynthesisStats
from src.synthesis.post_processor import apply_speech_act_adjustments
from src.synthesis.synthesizer import run_synthesis

__all__ = [
    # Engine abstraction
    "TTSEngineBase",
    "AudioResult",
    "create_engine",
    # Config and models
    "SynthesisConfig",
    "SegmentResult",
    "SynthesisStats",
    # Synthesis entry point
    "run_synthesis",
    # Text chunking
    "chunk_text_qwen",
    "chunk_text_chatterbox",
    # Post-processing
    "apply_speech_act_adjustments",
    # Checkpoint
    "create_checkpoint",
    "save_checkpoint",
    "load_checkpoint",
    "validate_checkpoint",
    "get_pending_segments",
    "mark_completed",
    "mark_failed",
]
