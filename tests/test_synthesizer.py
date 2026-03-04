"""Tests for the core synthesis loop (run_synthesis).

All tests use mocked TTSEngine to avoid loading Chatterbox/torch.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.synthesis.models import SynthesisConfig


def _make_voice_map(book_dir: Path) -> Path:
    """Create a minimal voice_map.json for testing."""
    vm = {
        "book_slug": "test-book",
        "narrator": {
            "character_name": "narrator",
            "speaker_id": "100",
            "clip_path": "ref/narrator.wav",
            "reasoning": "test",
            "confidence": 0.9,
            "is_major": False,
            "method": "test",
            "warning": None,
        },
        "characters": [
            {
                "character_name": "Alice",
                "speaker_id": "200",
                "clip_path": "ref/alice.wav",
                "reasoning": "test",
                "confidence": 0.8,
                "is_major": True,
                "method": "test",
                "warning": None,
            },
        ],
        "metadata": {"created_at": "2026-01-01"},
    }
    path = book_dir / "voice_map.json"
    path.write_text(json.dumps(vm), encoding="utf-8")
    return path


def _make_segments(chapters: int = 2, per_chapter: int = 3) -> list[dict]:
    """Create a list of attributed segment dicts."""
    segments = []
    seg_id = 0
    for ch in range(1, chapters + 1):
        for _ in range(per_chapter):
            segments.append(
                {
                    "id": seg_id,
                    "chapter": ch,
                    "chapter_title": f"Chapter {ch}",
                    "type": "narration" if seg_id % 2 == 0 else "dialogue",
                    "text": f"Test segment {seg_id}.",
                    "speaker": "narrator" if seg_id % 2 == 0 else "Alice",
                    "confidence": 0.9,
                }
            )
            seg_id += 1
    return segments


class FakeTensor:
    """Minimal tensor-like object for testing."""

    def __init__(self, length: int = 24000):
        self._length = length

    @property
    def shape(self):
        return (1, self._length)

    def __getitem__(self, idx):
        return self


def _mock_engine(fail_ids: set | None = None, fail_permanently: set | None = None):
    """Create a mocked TTSEngine that optionally fails on certain segment IDs."""
    engine = MagicMock()
    engine.device = "cpu"
    engine.sample_rate = 24000
    engine.model = MagicMock()
    engine.model.sr = 24000
    engine.config = SynthesisConfig()

    fail_ids = fail_ids or set()
    fail_permanently = fail_permanently or set()
    call_counts: dict[str, int] = {}

    def generate_side_effect(text, ref_clip, seg_type=None, **kwargs):
        # Extract seg_id from text
        for fid in fail_permanently:
            if f"segment {fid}" in text:
                raise RuntimeError(f"Permanent fail for segment {fid}")

        for fid in fail_ids:
            if f"segment {fid}" in text:
                key = str(fid)
                call_counts[key] = call_counts.get(key, 0) + 1
                if call_counts[key] <= 2:  # fail first 2 attempts
                    raise RuntimeError(f"Transient fail for segment {fid}")

        return FakeTensor(24000)  # 1 second of audio

    engine.generate.side_effect = generate_side_effect
    engine.save_wav_atomic.return_value = True
    engine.cleanup_memory.return_value = None
    engine.unload.return_value = None
    engine.load_model.return_value = None

    return engine


@patch("src.synthesis.synthesizer.TTSEngine")
def test_run_synthesis_skips_completed_segments(MockEngine, tmp_path):
    """Completed segments in checkpoint are not re-generated."""
    from src.matching.models import VoiceMap
    from src.synthesis.checkpoint import (
        create_checkpoint,
        mark_completed,
        save_checkpoint,
    )
    from src.synthesis.synthesizer import run_synthesis

    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)

    segments = _make_segments(chapters=1, per_chapter=3)
    config = SynthesisConfig(device="cpu")

    # Pre-populate checkpoint with segment 0 completed
    cp = create_checkpoint("test-book", 3, config)
    mark_completed(cp, 0, "wavs/ch01/seg_0000.wav", 1.0, 1.5)
    save_checkpoint(cp, book_dir)

    # Create the WAV file so validation passes
    wav_dir = book_dir / "wavs" / "ch01"
    wav_dir.mkdir(parents=True)
    (wav_dir / "seg_0000.wav").write_bytes(b"\x00" * 100)

    # Mock engine
    engine = _mock_engine()
    MockEngine.return_value = engine

    vm_path = book_dir / "voice_map.json"
    vm = VoiceMap.model_validate_json(vm_path.read_text())

    stats = run_synthesis(book_dir, vm, segments, config, verbose=False)

    # Segment 0 was cached, segments 1 and 2 were generated
    assert stats.skipped_cached == 1
    # engine.generate should have been called for segments 1 and 2 only
    assert engine.generate.call_count == 2


@patch("src.synthesis.synthesizer.TTSEngine")
def test_run_synthesis_retries_failed_segments(MockEngine, tmp_path):
    """Failed segments are retried up to max_retries."""
    from src.matching.models import VoiceMap
    from src.synthesis.synthesizer import run_synthesis

    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)

    segments = _make_segments(chapters=1, per_chapter=3)
    config = SynthesisConfig(device="cpu", max_retries=3)

    # Segment 1 fails first 2 attempts then succeeds
    engine = _mock_engine(fail_ids={1})
    MockEngine.return_value = engine

    vm_path = book_dir / "voice_map.json"
    vm = VoiceMap.model_validate_json(vm_path.read_text())

    stats = run_synthesis(book_dir, vm, segments, config, verbose=False)

    # All should complete (segment 1 succeeds on 3rd attempt)
    assert stats.failed == 0
    assert stats.completed == 3


@patch("src.synthesis.synthesizer.TTSEngine")
def test_failure_threshold_stops_run(MockEngine, tmp_path):
    """Run stops early when failure rate exceeds threshold."""
    from src.matching.models import VoiceMap
    from src.synthesis.synthesizer import run_synthesis

    book_dir = tmp_path / "book"
    book_dir.mkdir()

    # Need enough segments to trigger threshold check (>= 20)
    vm = {
        "book_slug": "test-book",
        "narrator": {
            "character_name": "narrator",
            "speaker_id": "100",
            "clip_path": "ref/narrator.wav",
            "reasoning": "test",
            "confidence": 0.9,
            "is_major": False,
            "method": "test",
            "warning": None,
        },
        "characters": [],
        "metadata": {},
    }
    (book_dir / "voice_map.json").write_text(json.dumps(vm))

    segments = _make_segments(chapters=1, per_chapter=25)
    # Make ALL segments fail permanently
    fail_all = set(range(25))
    config = SynthesisConfig(device="cpu", failure_threshold=0.1, max_retries=1)

    engine = _mock_engine(fail_permanently=fail_all)
    MockEngine.return_value = engine

    vm_obj = VoiceMap.model_validate_json((book_dir / "voice_map.json").read_text())

    stats = run_synthesis(book_dir, vm_obj, segments, config, verbose=False)

    # Should have stopped before processing all 25 segments
    assert stats.completed + stats.failed < 25


@patch("src.synthesis.synthesizer.TTSEngine")
def test_chapter_filter(MockEngine, tmp_path):
    """Only segments from the specified chapter are processed."""
    from src.matching.models import VoiceMap
    from src.synthesis.synthesizer import run_synthesis

    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)

    segments = _make_segments(chapters=3, per_chapter=2)
    config = SynthesisConfig(device="cpu")

    engine = _mock_engine()
    MockEngine.return_value = engine

    vm_path = book_dir / "voice_map.json"
    vm = VoiceMap.model_validate_json(vm_path.read_text())

    stats = run_synthesis(book_dir, vm, segments, config, chapter=2, verbose=False)

    # Only chapter 2 segments (2 segments) should have been generated
    assert engine.generate.call_count == 2


@patch("src.synthesis.synthesizer.TTSEngine")
def test_end_of_run_retry_pass(MockEngine, tmp_path):
    """Failed segments get a retry pass at end of run."""
    from src.matching.models import VoiceMap
    from src.synthesis.synthesizer import run_synthesis

    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)

    segments = _make_segments(chapters=1, per_chapter=5)
    config = SynthesisConfig(device="cpu", max_retries=1, failure_threshold=0.5)

    # Segment 2 fails on first pass (only 1 retry allowed)
    # but the end-of-run retry pass should succeed
    call_tracker = {"seg2_calls": 0}
    engine = MagicMock()
    engine.device = "cpu"
    engine.sample_rate = 24000
    engine.model = MagicMock()
    engine.model.sr = 24000
    engine.config = config

    def gen(text, ref_clip, seg_type=None, **kwargs):
        if "segment 2" in text:
            call_tracker["seg2_calls"] += 1
            if call_tracker["seg2_calls"] <= 1:
                raise RuntimeError("Transient fail")
        return FakeTensor(24000)

    engine.generate.side_effect = gen
    engine.save_wav_atomic.return_value = True
    engine.cleanup_memory.return_value = None
    engine.unload.return_value = None
    engine.load_model.return_value = None

    MockEngine.return_value = engine

    vm_path = book_dir / "voice_map.json"
    vm = VoiceMap.model_validate_json(vm_path.read_text())

    stats = run_synthesis(book_dir, vm, segments, config, verbose=False)

    # Segment 2 should have been recovered in the retry pass
    assert stats.failed == 0
    assert stats.completed == 5
