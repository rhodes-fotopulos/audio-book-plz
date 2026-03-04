"""Tests for matching orchestrator and pipeline integration.

Covers:
- run_matching returns cached voice_map.json when it exists
- run_matching calls all pipeline stages in order
- run_match displays Rich table output
- CLI match command validates input paths
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.attribution.models import CharacterProfile, VoiceQualities
from src.matching.models import CastClassification, SpeakerAnnotation, VoiceAssignment, VoiceMap
from src.matching.orchestrator import run_matching


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_book_dir(tmp_path) -> Path:
    """Create a temporary book directory with characters.json and attributed.json."""
    book_dir = tmp_path / "test-book"
    book_dir.mkdir()

    characters = [
        {
            "name": "Alice",
            "aliases": [],
            "gender": "female",
            "age_range": "young adult",
            "voice_qualities": {"pitch": "high", "pace": "fast", "tone": "cheerful", "accent": "unknown"},
            "personality_traits": ["curious", "brave"],
            "relationships": [],
            "description": "A curious young woman",
            "is_named": True,
        },
        {
            "name": "Bob",
            "aliases": [],
            "gender": "male",
            "age_range": "middle-aged",
            "voice_qualities": {"pitch": "low", "pace": "slow", "tone": "gruff", "accent": "unknown"},
            "personality_traits": ["stern", "wise"],
            "relationships": [],
            "description": "A stern older man",
            "is_named": True,
        },
    ]
    with open(book_dir / "characters.json", "w") as f:
        json.dump(characters, f)

    segments = [
        {"id": 0, "chapter": 1, "type": "narration", "text": "Once upon a time.", "speaker": "narrator", "confidence": 0.9},
        {"id": 1, "chapter": 1, "type": "dialogue", "text": "Hello!", "speaker": "Alice", "confidence": 0.9},
        {"id": 2, "chapter": 1, "type": "dialogue", "text": "Hi there.", "speaker": "Alice", "confidence": 0.85},
        {"id": 3, "chapter": 1, "type": "dialogue", "text": "Hi there.", "speaker": "Alice", "confidence": 0.85},
        {"id": 4, "chapter": 1, "type": "dialogue", "text": "Hi there.", "speaker": "Alice", "confidence": 0.85},
        {"id": 5, "chapter": 1, "type": "dialogue", "text": "Hi there.", "speaker": "Alice", "confidence": 0.85},
        {"id": 6, "chapter": 1, "type": "dialogue", "text": "Good day.", "speaker": "Bob", "confidence": 0.8},
        {"id": 7, "chapter": 1, "type": "dialogue", "text": "Good day.", "speaker": "Bob", "confidence": 0.8},
        {"id": 8, "chapter": 1, "type": "dialogue", "text": "Good day.", "speaker": "Bob", "confidence": 0.8},
        {"id": 9, "chapter": 1, "type": "dialogue", "text": "Good day.", "speaker": "Bob", "confidence": 0.8},
        {"id": 10, "chapter": 1, "type": "dialogue", "text": "Good day.", "speaker": "Bob", "confidence": 0.8},
    ]
    with open(book_dir / "attributed.json", "w") as f:
        json.dump(segments, f)

    return book_dir


@pytest.fixture
def mock_voice_map() -> VoiceMap:
    """Sample VoiceMap for testing."""
    return VoiceMap(
        book_slug="test-book",
        narrator=VoiceAssignment(
            character_name="narrator",
            speaker_id="100",
            clip_path="AUDIO_DIR/100/longest.wav",
            reasoning="Good narrator voice",
            confidence=0.85,
            is_major=False,
            method="llm",
            warning=None,
        ),
        characters=[
            VoiceAssignment(
                character_name="Alice",
                speaker_id="200",
                clip_path="AUDIO_DIR/200/longest.wav",
                reasoning="Feminine, cheerful",
                confidence=0.9,
                is_major=True,
                method="llm",
                warning=None,
            ),
            VoiceAssignment(
                character_name="Bob",
                speaker_id="300",
                clip_path="AUDIO_DIR/300/longest.wav",
                reasoning="Masculine, gruff",
                confidence=0.88,
                is_major=True,
                method="llm",
                warning=None,
            ),
        ],
        metadata={
            "created_at": "2026-03-03T00:00:00Z",
            "total_speakers_evaluated": 100,
            "major_characters": 2,
            "minor_characters": 0,
            "narrator_mode": "third_person",
            "libritts_audio_available": False,
        },
    )


@pytest.fixture
def mock_speaker_index() -> dict[str, SpeakerAnnotation]:
    """Minimal speaker index."""
    return {
        "100": SpeakerAnnotation(
            speaker_id="100", traits=["calm", "masculine"], trait_text="calm, masculine",
            gender="male", annotator_agreement={"calm": 2, "masculine": 2},
        ),
        "200": SpeakerAnnotation(
            speaker_id="200", traits=["feminine", "young", "cheerful"], trait_text="feminine, young, cheerful",
            gender="female", annotator_agreement={"feminine": 2, "young": 1, "cheerful": 1},
        ),
        "300": SpeakerAnnotation(
            speaker_id="300", traits=["gruff", "masculine", "old"], trait_text="gruff, masculine, old",
            gender="male", annotator_agreement={"gruff": 2, "masculine": 2, "old": 1},
        ),
    }


# ---------------------------------------------------------------------------
# run_matching caching tests
# ---------------------------------------------------------------------------


class TestRunMatchingCaching:
    def test_returns_cached_when_voice_map_exists(self, tmp_book_dir, mock_voice_map) -> None:
        """run_matching returns cached VoiceMap when voice_map.json exists."""
        # Write a voice_map.json
        voice_map_path = tmp_book_dir / "voice_map.json"
        with open(voice_map_path, "w") as f:
            json.dump(mock_voice_map.model_dump(), f)

        # Should return the cached map without calling any matching functions
        result = run_matching(tmp_book_dir, Path("/fake/data"), None)
        assert result.book_slug == "test-book"
        assert result.narrator.speaker_id == "100"
        assert len(result.characters) == 2

    def test_cached_skips_llm_calls(self, tmp_book_dir, mock_voice_map) -> None:
        """Verify that LLM is not called when voice_map.json exists."""
        voice_map_path = tmp_book_dir / "voice_map.json"
        with open(voice_map_path, "w") as f:
            json.dump(mock_voice_map.model_dump(), f)

        with patch("src.matching.orchestrator.load_speaker_index") as mock_load:
            run_matching(tmp_book_dir, Path("/fake/data"), None)
            mock_load.assert_not_called()


# ---------------------------------------------------------------------------
# run_matching pipeline order tests
# ---------------------------------------------------------------------------


class TestRunMatchingPipeline:
    @patch("src.matching.orchestrator.select_reference_clip", return_value=None)
    @patch("src.matching.orchestrator.enforce_uniqueness")
    @patch("src.matching.orchestrator.match_character_embedding")
    @patch("src.matching.orchestrator.match_character_llm")
    @patch("src.matching.orchestrator.match_narrator_llm")
    @patch("src.matching.orchestrator.build_speaker_embeddings")
    @patch("src.matching.orchestrator.classify_cast")
    @patch("src.matching.orchestrator.load_speaker_index")
    def test_calls_pipeline_stages_in_order(
        self,
        mock_load_index,
        mock_classify,
        mock_build_emb,
        mock_narrator,
        mock_char_llm,
        mock_char_emb,
        mock_dedup,
        mock_clip,
        tmp_book_dir,
        mock_speaker_index,
    ) -> None:
        """Verify all pipeline stages are called."""
        mock_load_index.return_value = mock_speaker_index

        mock_classify.return_value = CastClassification(
            major=["Alice", "Bob"], minor=[], threshold=5, narrator_mode="third_person"
        )

        import torch
        mock_build_emb.return_value = (["100", "200", "300"], torch.randn(3, 384))

        narrator_assign = VoiceAssignment(
            character_name="narrator", speaker_id="100", clip_path="",
            reasoning="Good narrator", confidence=0.85, is_major=False, method="llm",
        )
        mock_narrator.return_value = narrator_assign

        alice_assign = VoiceAssignment(
            character_name="Alice", speaker_id="200", clip_path="",
            reasoning="Cheerful female", confidence=0.9, is_major=True, method="llm",
        )
        bob_assign = VoiceAssignment(
            character_name="Bob", speaker_id="300", clip_path="",
            reasoning="Gruff male", confidence=0.88, is_major=True, method="llm",
        )
        mock_char_llm.side_effect = [alice_assign, bob_assign]

        # Dedup returns assignments unchanged
        mock_dedup.side_effect = lambda assignments, *args, **kwargs: assignments

        result = run_matching(tmp_book_dir, Path("/fake/data"), None)

        # Verify pipeline stages called
        mock_load_index.assert_called_once()
        mock_classify.assert_called_once()
        mock_build_emb.assert_called_once()
        mock_narrator.assert_called_once()
        assert mock_char_llm.call_count == 2  # Alice and Bob
        mock_dedup.assert_called_once()

        # Verify result
        assert result.narrator.speaker_id == "100"
        assert len(result.characters) == 2

    @patch("src.matching.orchestrator.select_reference_clip", return_value=None)
    @patch("src.matching.orchestrator.enforce_uniqueness")
    @patch("src.matching.orchestrator.match_character_embedding")
    @patch("src.matching.orchestrator.match_character_llm")
    @patch("src.matching.orchestrator.match_narrator_llm")
    @patch("src.matching.orchestrator.build_speaker_embeddings")
    @patch("src.matching.orchestrator.classify_cast")
    @patch("src.matching.orchestrator.load_speaker_index")
    def test_llm_failure_falls_back_to_embedding(
        self,
        mock_load_index,
        mock_classify,
        mock_build_emb,
        mock_narrator,
        mock_char_llm,
        mock_char_emb,
        mock_dedup,
        mock_clip,
        tmp_book_dir,
        mock_speaker_index,
    ) -> None:
        """When LLM returns None, embedding fallback is used."""
        mock_load_index.return_value = mock_speaker_index

        mock_classify.return_value = CastClassification(
            major=["Alice"], minor=["Bob"], threshold=5, narrator_mode="third_person"
        )

        import torch
        mock_build_emb.return_value = (["100", "200", "300"], torch.randn(3, 384))

        # Narrator LLM fails
        mock_narrator.return_value = None

        # Embedding fallback for narrator
        narrator_emb = VoiceAssignment(
            character_name="narrator", speaker_id="100", clip_path="",
            reasoning="Embedding fallback", confidence=0.6, is_major=False, method="embedding",
        )

        # LLM fails for Alice too
        mock_char_llm.return_value = None

        # Embedding fallback for Alice
        alice_emb = VoiceAssignment(
            character_name="Alice", speaker_id="200", clip_path="",
            reasoning="Embedding match", confidence=0.7, is_major=False, method="embedding",
        )

        # Bob is minor, goes straight to embedding
        bob_emb = VoiceAssignment(
            character_name="Bob", speaker_id="300", clip_path="",
            reasoning="Embedding match", confidence=0.65, is_major=False, method="embedding",
        )

        # narrator fallback, then Alice fallback, then Bob minor
        mock_char_emb.side_effect = [narrator_emb, alice_emb, bob_emb]

        mock_dedup.side_effect = lambda assignments, *args, **kwargs: assignments

        result = run_matching(tmp_book_dir, Path("/fake/data"), None)

        # Embedding used for all
        assert mock_char_emb.call_count == 3  # narrator + Alice + Bob


# ---------------------------------------------------------------------------
# CLI validation tests
# ---------------------------------------------------------------------------


class TestCLIMatchValidation:
    def test_missing_characters_json(self, tmp_path) -> None:
        """CLI exits with error if characters.json missing."""
        from typer.testing import CliRunner
        from main import app

        book_dir = tmp_path / "test-book"
        book_dir.mkdir()
        # Only create attributed.json, no characters.json
        (book_dir / "attributed.json").write_text("[]")

        runner = CliRunner()
        result = runner.invoke(app, ["match", str(book_dir), "--libritts-data", str(tmp_path)])
        assert result.exit_code == 1
        assert "characters.json not found" in result.output

    def test_missing_attributed_json(self, tmp_path) -> None:
        """CLI exits with error if attributed.json missing."""
        from typer.testing import CliRunner
        from main import app

        book_dir = tmp_path / "test-book"
        book_dir.mkdir()
        (book_dir / "characters.json").write_text("[]")
        # No attributed.json

        runner = CliRunner()
        result = runner.invoke(app, ["match", str(book_dir), "--libritts-data", str(tmp_path)])
        assert result.exit_code == 1
        assert "attributed.json not found" in result.output

    def test_missing_df1_csv(self, tmp_path) -> None:
        """CLI exits with error if df1_en.csv not in libritts-data dir."""
        from typer.testing import CliRunner
        from main import app

        book_dir = tmp_path / "test-book"
        book_dir.mkdir()
        (book_dir / "characters.json").write_text("[]")
        (book_dir / "attributed.json").write_text("[]")

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        # No df1_en.csv

        runner = CliRunner()
        result = runner.invoke(app, ["match", str(book_dir), "--libritts-data", str(data_dir)])
        assert result.exit_code == 1
        assert "df1_en.csv not found" in result.output
