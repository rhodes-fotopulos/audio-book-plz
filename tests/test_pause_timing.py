"""Tests for Gaussian-randomized pause timing and crossfade behaviour.

Covers:
- gaussian_pause_ms clipping and variation
- Speaker change detection in _get_silence_ms
- Boundary type ordering (scene break > paragraph)
- Crossfade guard for short segments
"""

from __future__ import annotations

import numpy as np
from pydub import AudioSegment

from src.assembly.concatenator import (
    _apply_crossfade,
    _get_silence_ms,
    gaussian_pause_ms,
)
from src.assembly.models import PauseConfig


def test_gaussian_pause_within_bounds():
    """All sampled pauses must fall within [min_val, max_val]."""
    results = [gaussian_pause_ms(450.0, 75.0, 300.0, 600.0) for _ in range(200)]
    assert all(300 <= v <= 600 for v in results), (
        f"Out-of-bounds values: {[v for v in results if v < 300 or v > 600]}"
    )


def test_gaussian_pause_varies():
    """With std > 0, sampled pauses should not all be identical."""
    np.random.seed(None)  # Ensure non-deterministic
    results = [gaussian_pause_ms(450.0, 75.0, 300.0, 600.0) for _ in range(100)]
    unique = set(results)
    assert len(unique) > 1, "All 100 samples were identical — no variation"


def test_speaker_change_detected():
    """Different speakers on adjacent segments should use speaker_change params."""
    pause_config = PauseConfig()
    prev = {"type": "dialogue", "speaker": "Alice"}
    curr = {"type": "dialogue", "speaker": "Bob"}

    # Collect multiple samples to verify they're in the speaker_change range
    results = [_get_silence_ms(prev, curr, pause_config) for _ in range(50)]
    assert all(
        pause_config.speaker_change_min_ms <= v <= pause_config.speaker_change_max_ms
        for v in results
    ), (
        f"Speaker change pause out of range "
        f"[{pause_config.speaker_change_min_ms}, {pause_config.speaker_change_max_ms}]: "
        f"{[v for v in results if v < pause_config.speaker_change_min_ms or v > pause_config.speaker_change_max_ms]}"
    )


def test_scene_break_longer_than_paragraph():
    """Scene break mean pause should be longer than paragraph mean."""
    cfg = PauseConfig()
    assert cfg.scene_break_mean_ms > cfg.paragraph_mean_ms, (
        f"scene_break_mean_ms ({cfg.scene_break_mean_ms}) should be > "
        f"paragraph_mean_ms ({cfg.paragraph_mean_ms})"
    )


def test_crossfade_guard_short_segments():
    """Segment shorter than 2*fade_ms should clamp fade duration."""
    # Create a very short segment (10ms of silence at 44100 Hz)
    short_audio = AudioSegment.silent(duration=10, frame_rate=44100)
    fade_ms = 20  # Longer than half the segment

    result = _apply_crossfade(short_audio, fade_ms)
    # Should not raise — fade is clamped to len(segment) // 2
    assert len(result) == len(short_audio), (
        f"Crossfade changed segment length: {len(short_audio)} -> {len(result)}"
    )


def test_crossfade_empty_segment():
    """Empty AudioSegment should pass through unchanged."""
    empty = AudioSegment.empty()
    result = _apply_crossfade(empty, 8)
    assert len(result) == 0
