"""Data models for Phase 4 TTS synthesis.

Defines configuration, per-segment results, and run-level statistics
for the Chatterbox TTS synthesis pipeline.

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

    Defaults are optimised for natural-sounding audiobook narration on
    Apple Silicon MPS with the Chatterbox 500M standard model.
    """

    # Voice tuning — different defaults for narration vs dialogue
    narration_exaggeration: float = 0.25
    """Low exaggeration for calm, steady narration delivery."""

    dialogue_exaggeration: float = 0.45
    """Higher exaggeration for expressive character voices."""

    cfg_weight: float = 0.3
    """Classifier-free guidance weight.  Low for natural pacing."""

    # Retry / failure
    max_retries: int = 3
    """Per-segment retry count before marking as failed."""

    failure_threshold: float = 0.15
    """Stop run if failure rate exceeds this fraction (0-1)."""

    # Memory management
    cleanup_interval: int = 15
    """Run gc.collect + MPS cache clear every N segments."""

    # WAV validation
    min_wav_duration_s: float = 0.1
    """WAV shorter than this is treated as corrupted."""

    # Device selection
    device: str = "auto"
    """'auto' detects MPS/CPU; also accepts 'mps' or 'cpu'."""


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
