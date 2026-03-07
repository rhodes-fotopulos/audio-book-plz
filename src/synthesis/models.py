"""Data models for TTS synthesis.

Defines configuration, per-segment results, and run-level statistics
for the Qwen3-TTS synthesis pipeline.

All models are dataclasses for simplicity and consistency with Phase 1
parser models.  No external dependencies at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Synthesis configuration
# ---------------------------------------------------------------------------


@dataclass
class SynthesisConfig:
    """Tuneable parameters for a synthesis run.

    Uses Qwen3-TTS via MLX for Apple Silicon TTS.
    Engine selection via ``engine_type`` field.
    """

    # Engine selection
    engine_type: str = "qwen3"
    """TTS engine: 'qwen3' (MLX)."""

    # Retry / failure
    max_retries: int = 3
    """Per-segment retry count before marking as failed."""

    failure_threshold: float = 0.15
    """Stop run if failure rate exceeds this fraction (0-1)."""

    # Memory management — Qwen3-TTS (MLX Metal)
    mlx_cache_limit_gb: float = 4.0
    """MLX Metal cache limit in GB.  On 16GB machine, 4GB leaves room for OS."""

    mlx_cleanup_interval: int = 50
    """Run mx.metal.clear_cache() every N segments (Qwen3-TTS)."""

    # WAV validation
    min_wav_duration_s: float = 0.1
    """WAV shorter than this is treated as corrupted."""

    # Device selection
    device: str = "auto"
    """'auto' detects available hardware; also accepts 'mps' or 'cpu'."""

    # Speech-act post-processing
    speech_act_fx: bool = False
    """Apply speech-act audio post-processing (volume/speed adjustments for whispered/shouted/thought). Default OFF — TTS engine natural prosody is trusted."""

    # Batch-by-character synthesis
    batch_by_character: bool = False
    """Synthesize all segments per character consecutively instead of chapter-by-chapter. Reduces MLX cache thrashing between voices."""


# ---------------------------------------------------------------------------
# Per-segment result
# ---------------------------------------------------------------------------


@dataclass
class SegmentResult:
    """Outcome of synthesising a single text segment."""

    segment_id: int
    wav_path: str
    duration_s: float
    generation_time_s: float
    character_name: str
    success: bool
    error: str | None = None
    attempts: int = 1


# ---------------------------------------------------------------------------
# Run-level statistics
# ---------------------------------------------------------------------------


@dataclass
class SynthesisStats:
    """Aggregate statistics for the completion summary table."""

    total_segments: int = 0
    completed: int = 0
    failed: int = 0
    skipped_cached: int = 0
    total_audio_duration_s: float = 0.0
    total_wall_time_s: float = 0.0
    chapters_completed: int = 0
    total_chapters: int = 0
