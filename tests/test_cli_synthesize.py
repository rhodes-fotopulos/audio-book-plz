"""CLI integration tests for the synthesize command.

Tests use typer.testing.CliRunner to verify CLI behavior without
loading the actual TTS engine (torch/chatterbox are never imported).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from main import app

runner = CliRunner()


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
        "characters": [],
        "metadata": {},
    }
    path = book_dir / "voice_map.json"
    path.write_text(json.dumps(vm), encoding="utf-8")
    return path


def _make_attributed(book_dir: Path, num_segments: int = 3) -> Path:
    """Create a minimal attributed.json for testing."""
    segments = [
        {
            "id": i,
            "chapter": 1,
            "chapter_title": "Chapter 1",
            "type": "narration" if i % 2 == 0 else "dialogue",
            "text": f"Test segment {i}.",
            "speaker": "narrator",
            "confidence": 1.0,
        }
        for i in range(num_segments)
    ]
    path = book_dir / "attributed.json"
    path.write_text(json.dumps(segments), encoding="utf-8")
    return path


def test_synthesize_missing_voice_map(tmp_path: Path) -> None:
    """Run synthesize on a book_dir without voice_map.json -> exit 1."""
    book_dir = tmp_path / "book"
    book_dir.mkdir()

    result = runner.invoke(app, ["synthesize", str(book_dir)])

    assert result.exit_code == 1
    assert "Run 'match' first" in result.output


def test_synthesize_missing_attributed(tmp_path: Path) -> None:
    """voice_map.json exists but no attributed.json -> exit 1."""
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)

    result = runner.invoke(app, ["synthesize", str(book_dir)])

    assert result.exit_code == 1
    assert "Run 'attribute' first" in result.output


def test_synthesize_dry_run(tmp_path: Path) -> None:
    """Dry run shows estimate table and does not create wavs directory."""
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)
    _make_attributed(book_dir, num_segments=10)

    result = runner.invoke(app, ["synthesize", str(book_dir), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry Run Estimate" in result.output
    # No wavs directory should be created in dry-run mode
    assert not (book_dir / "wavs").exists()


def test_synthesize_chapter_option(tmp_path: Path) -> None:
    """Verify --chapter flag filters segments in dry-run estimate."""
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    _make_voice_map(book_dir)

    # Create segments across 2 chapters
    segments = [
        {
            "id": i,
            "chapter": 1 if i < 5 else 2,
            "chapter_title": f"Chapter {1 if i < 5 else 2}",
            "type": "narration",
            "text": f"Test segment {i}.",
            "speaker": "narrator",
            "confidence": 1.0,
        }
        for i in range(10)
    ]
    (book_dir / "attributed.json").write_text(
        json.dumps(segments), encoding="utf-8"
    )

    # Dry run for chapter 1 only (5 segments)
    result = runner.invoke(
        app, ["synthesize", str(book_dir), "--dry-run", "--chapter", "1"]
    )

    assert result.exit_code == 0
    assert "Dry Run Estimate" in result.output
    # The table should show "5" segments (only chapter 1)
    assert "5" in result.output


def test_synthesize_help() -> None:
    """Verify help text shows all expected options."""
    result = runner.invoke(app, ["synthesize", "--help"])

    assert result.exit_code == 0
    assert "--chapter" in result.output
    assert "--dry-run" in result.output
    assert "--verbose" in result.output
    assert "--cpu" in result.output
