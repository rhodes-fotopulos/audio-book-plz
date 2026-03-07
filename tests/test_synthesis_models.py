"""Tests for Phase 4 synthesis models and checkpoint system."""

from __future__ import annotations

from pathlib import Path

from src.synthesis.checkpoint import (
    create_checkpoint,
    get_pending_segments,
    load_checkpoint,
    mark_completed,
    mark_failed,
    save_checkpoint,
    validate_checkpoint,
)
from src.synthesis.models import SynthesisConfig


def test_synthesis_config_defaults():
    """Verify all SynthesisConfig defaults match spec values."""
    config = SynthesisConfig()

    assert config.max_retries == 3
    assert config.failure_threshold == 0.15
    assert config.mlx_cleanup_interval == 50
    assert config.min_wav_duration_s == 0.1
    assert config.device == "auto"


def test_create_checkpoint():
    """create_checkpoint returns valid structure with correct fields."""
    config = SynthesisConfig()
    cp = create_checkpoint("test-book", 100, config)

    assert cp["book_slug"] == "test-book"
    assert cp["total_segments"] == 100
    assert cp["completed"] == {}
    assert cp["failed"] == {}
    assert "started_at" in cp
    assert "updated_at" in cp
    assert cp["config"]["model"] == "qwen3-tts-1.7b"


def test_save_load_checkpoint(tmp_path: Path):
    """Round-trip save/load preserves checkpoint data."""
    config = SynthesisConfig()
    cp = create_checkpoint("round-trip", 50, config)
    mark_completed(cp, 0, "wavs/ch01/seg_0000.wav", 3.2, 4.1)
    mark_failed(cp, 1, "MPS OOM", 3)

    save_checkpoint(cp, tmp_path)
    loaded = load_checkpoint(tmp_path)

    assert loaded is not None
    assert loaded["book_slug"] == "round-trip"
    assert loaded["total_segments"] == 50
    assert "0" in loaded["completed"]
    assert loaded["completed"]["0"]["duration_s"] == 3.2
    assert "1" in loaded["failed"]
    assert loaded["failed"]["1"]["error"] == "MPS OOM"


def test_validate_checkpoint_removes_missing_wavs(tmp_path: Path):
    """validate_checkpoint re-queues segments whose WAV is missing."""
    config = SynthesisConfig()
    cp = create_checkpoint("validate", 10, config)

    # Mark two segments completed — only create the WAV for one
    mark_completed(cp, 0, "wavs/ch01/seg_0000.wav", 3.0, 4.0)
    mark_completed(cp, 1, "wavs/ch01/seg_0001.wav", 2.5, 3.5)

    wavs_dir = tmp_path / "wavs"
    wavs_dir.mkdir()
    ch_dir = wavs_dir / "ch01"
    ch_dir.mkdir()

    # Only create the first WAV file
    (ch_dir / "seg_0000.wav").write_bytes(b"\x00" * 100)
    # seg_0001.wav intentionally missing

    cleaned, re_queue = validate_checkpoint(cp, wavs_dir)

    assert "0" in cleaned["completed"]
    assert "1" not in cleaned["completed"]
    assert "1" in re_queue


def test_mark_completed_removes_from_failed():
    """mark_completed moves segment from failed to completed."""
    config = SynthesisConfig()
    cp = create_checkpoint("move-test", 10, config)

    mark_failed(cp, 5, "timeout", 2)
    assert "5" in cp["failed"]

    mark_completed(cp, 5, "wavs/ch01/seg_0005.wav", 2.0, 3.0)
    assert "5" in cp["completed"]
    assert "5" not in cp["failed"]


def test_batch_by_character_config_default():
    """SynthesisConfig().batch_by_character is False by default."""
    config = SynthesisConfig()
    assert config.batch_by_character is False


def test_batch_by_character_config_set():
    """SynthesisConfig(batch_by_character=True).batch_by_character is True."""
    config = SynthesisConfig(batch_by_character=True)
    assert config.batch_by_character is True


def test_get_pending_segments():
    """get_pending_segments filters out completed segments."""
    config = SynthesisConfig()
    cp = create_checkpoint("pending", 5, config)

    mark_completed(cp, 0, "w/s0.wav", 1.0, 1.0)
    mark_completed(cp, 2, "w/s2.wav", 1.0, 1.0)
    mark_failed(cp, 4, "error", 1)

    pending = get_pending_segments(cp, [0, 1, 2, 3, 4])

    # 0 and 2 are completed — not pending
    # 1, 3 are untouched — pending
    # 4 is failed but still in all_segment_ids — pending (can retry)
    assert 0 not in pending
    assert 2 not in pending
    assert 1 in pending
    assert 3 in pending
    assert 4 in pending
