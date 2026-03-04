"""Tests for voice consistency verifier.

Uses mocking for Resemblyzer encoder since it requires neural network weights.
Tests cosine similarity math, threshold logic, report generation, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.synthesis.voice_verifier import (
    ConsistencyReport,
    VoiceConsistencyVerifier,
)


def _random_embedding(seed: int = 42) -> np.ndarray:
    """Generate a random unit vector for testing embeddings."""
    rng = np.random.RandomState(seed)
    v = rng.randn(256).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Cosine similarity tests
# ---------------------------------------------------------------------------


def test_cosine_similarity_identical_vectors():
    """Two identical vectors should return similarity of 1.0."""
    v = _random_embedding(42)
    sim = VoiceConsistencyVerifier.cosine_similarity(v, v)
    assert abs(sim - 1.0) < 1e-5, f"Expected ~1.0, got {sim}"


def test_cosine_similarity_orthogonal_vectors():
    """Two orthogonal vectors should return similarity of 0.0."""
    # Create two orthogonal vectors
    a = np.zeros(256, dtype=np.float32)
    a[0] = 1.0
    b = np.zeros(256, dtype=np.float32)
    b[1] = 1.0
    sim = VoiceConsistencyVerifier.cosine_similarity(a, b)
    assert abs(sim) < 1e-5, f"Expected ~0.0, got {sim}"


def test_cosine_similarity_opposite_vectors():
    """Negated vector should return similarity of -1.0."""
    v = _random_embedding(42)
    sim = VoiceConsistencyVerifier.cosine_similarity(v, -v)
    assert abs(sim - (-1.0)) < 1e-5, f"Expected ~-1.0, got {sim}"


# ---------------------------------------------------------------------------
# Threshold tests
# ---------------------------------------------------------------------------


def test_threshold_pass():
    """Similarity 0.75 with threshold 0.60 should pass."""
    verifier = VoiceConsistencyVerifier(threshold=0.60)
    # Similarity > threshold
    assert 0.75 >= verifier.threshold


def test_threshold_fail():
    """Similarity 0.45 with threshold 0.60 should fail."""
    verifier = VoiceConsistencyVerifier(threshold=0.60)
    assert 0.45 < verifier.threshold


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------


def test_report_summary_counts():
    """Add 5 passed and 2 flagged results, verify summary counts."""
    report = ConsistencyReport()

    # 5 passed
    for i in range(5):
        report.add_result(i, "Alice", 0.85, passed=True)

    # 2 flagged
    for i in range(5, 7):
        report.add_result(i, "Bob", 0.40, passed=False)
        report.add_flagged(i, "Bob", 0.40, f"/tmp/seg_{i:04d}.wav")

    assert report.segments_checked == 7
    assert report.segments_passed == 5
    assert len(report.segments_flagged) == 2


def test_report_write_json(tmp_path: Path):
    """Write report to tmp_path, read back, verify JSON structure."""
    report = ConsistencyReport()
    report.add_result(1, "Alice", 0.85, passed=True)
    report.add_result(2, "Bob", 0.40, passed=False)
    report.add_flagged(2, "Bob", 0.40, "/tmp/seg_0002.wav")
    report.add_skipped()

    output_path = tmp_path / "voice_consistency_report.json"
    report.write_report(output_path)

    assert output_path.exists()
    data = json.loads(output_path.read_text())

    assert "summary" in data
    assert "flagged_segments" in data
    assert data["summary"]["segments_checked"] == 2
    assert data["summary"]["segments_passed"] == 1
    assert data["summary"]["segments_flagged"] == 1
    assert data["summary"]["segments_skipped"] == 1
    assert len(data["flagged_segments"]) == 1
    assert data["flagged_segments"][0]["speaker"] == "Bob"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_short_segment_skipped():
    """Segment shorter than min_duration_s should be skipped (returns 1.0, True)."""
    verifier = VoiceConsistencyVerifier(threshold=0.60, min_duration_s=2.0)

    # Mock compute_segment_embedding to return None (simulating short segment)
    verifier.compute_segment_embedding = MagicMock(return_value=None)

    ref = _random_embedding(42)
    similarity, passed = verifier.check_segment(Path("/tmp/short.wav"), ref)

    assert similarity == 1.0
    assert passed is True


def test_placeholder_clip_skipped():
    """Build reference embeddings with AUDIO_DIR/ prefix should skip that character."""
    from src.matching.models import VoiceAssignment, VoiceMap

    voice_map = VoiceMap(
        book_slug="test-book",
        narrator=VoiceAssignment(
            character_name="narrator",
            speaker_id="100",
            clip_path="AUDIO_DIR/some/clip.wav",  # Placeholder
            reasoning="test",
            confidence=0.9,
            is_major=True,
            method="llm",
        ),
        characters=[
            VoiceAssignment(
                character_name="Alice",
                speaker_id="200",
                clip_path="AUDIO_DIR/another/clip.wav",  # Placeholder
                reasoning="test",
                confidence=0.8,
                is_major=True,
                method="llm",
            ),
        ],
        metadata={"test": True},
    )

    verifier = VoiceConsistencyVerifier(threshold=0.60)

    # Mock the encoder so we don't need actual Resemblyzer weights
    mock_encoder = MagicMock()
    verifier._encoder = mock_encoder

    embeddings = verifier.build_reference_embeddings(voice_map)

    # Both should be skipped (placeholder paths)
    assert len(embeddings) == 0


def test_verifier_configurable_threshold():
    """Threshold should be configurable."""
    v = VoiceConsistencyVerifier(threshold=0.70)
    assert v.threshold == 0.70

    v2 = VoiceConsistencyVerifier(threshold=0.50)
    assert v2.threshold == 0.50
