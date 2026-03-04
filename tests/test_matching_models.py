"""Tests for Phase 3 voice matching models and speaker index.

Covers:
- SpeakerAnnotation creation and gender inference
- VoiceAssignment serialization
- VoiceMap JSON round-trip
- Speaker index loading with mock CSV data
- Candidate filtering by gender and age
- Cast classification by dialogue count
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from src.matching.models import (
    CastClassification,
    SpeakerAnnotation,
    VoiceAssignment,
    VoiceMap,
)
from src.matching.speaker_index import (
    classify_cast,
    filter_candidates,
    load_speaker_index,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_libritts_data(tmp_path: Path) -> Path:
    """Create mock LibriTTS-P CSV files for testing."""
    # Annotator 1
    df1 = tmp_path / "df1_en.csv"
    df1.write_text(
        "100|very masculine,adult-like,calm,intellectual\n"
        "200|very feminine,young,clear,cute\n"
        "300|feminine,adult-like,slightly calm,sincere\n"
        "400|masculine,middle-aged,slightly thick,cool\n"
    )
    # Annotator 2
    df2 = tmp_path / "df2_en.csv"
    df2.write_text(
        "100|masculine,adult-like,calm,slightly cool\n"
        "200|feminine,young,fluent,intellectual\n"
        "300|very feminine,adult-like,calm,friendly\n"
        "400|very masculine,middle-aged,dark,cool\n"
    )
    # Annotator 3
    df3 = tmp_path / "df3_en.csv"
    df3.write_text(
        "100|very masculine,slightly old,calm,intellectual,sincere\n"
        "200|feminine,slightly young,clear,lively\n"
        "300|feminine,adult-like,slightly intellectual\n"
        "400|masculine,middle-aged,thick,slightly wild\n"
    )
    return tmp_path


@pytest.fixture
def sample_speaker_index(mock_libritts_data: Path) -> dict[str, SpeakerAnnotation]:
    """Load a speaker index from mock data."""
    return load_speaker_index(mock_libritts_data)


@pytest.fixture
def sample_segments() -> list[dict]:
    """Create sample attributed segments for cast classification tests."""
    segments = []
    seg_id = 0

    # Chapter 1: Mr. Darcy speaks 8 lines, Elizabeth 6
    for _ in range(8):
        segments.append(
            {"id": seg_id, "chapter": 1, "type": "dialogue", "speaker": "Mr. Darcy", "text": "Test."}
        )
        seg_id += 1
    for _ in range(6):
        segments.append(
            {"id": seg_id, "chapter": 1, "type": "dialogue", "speaker": "Elizabeth Bennet", "text": "Test."}
        )
        seg_id += 1

    # Chapter 2: Minor character Mary speaks 2 lines
    for _ in range(2):
        segments.append(
            {"id": seg_id, "chapter": 2, "type": "dialogue", "speaker": "Mary", "text": "Test."}
        )
        seg_id += 1

    # Narration segments (third person)
    for _ in range(10):
        segments.append(
            {"id": seg_id, "chapter": 1, "type": "narration", "speaker": "narrator", "text": "The gentleman walked across the room."}
        )
        seg_id += 1

    return segments


@pytest.fixture
def sample_characters() -> list[dict]:
    """Sample character dicts for classification tests."""
    return [
        {"name": "Mr. Darcy", "gender": "male", "age_range": "young adult"},
        {"name": "Elizabeth Bennet", "gender": "female", "age_range": "young adult"},
        {"name": "Mary", "gender": "female", "age_range": "young adult"},
    ]


# ---------------------------------------------------------------------------
# SpeakerAnnotation tests
# ---------------------------------------------------------------------------


class TestSpeakerAnnotation:
    def test_create_speaker_annotation(self) -> None:
        ann = SpeakerAnnotation(
            speaker_id="100",
            traits=["calm", "intellectual", "masculine"],
            trait_text="calm, intellectual, masculine",
            gender="male",
            annotator_agreement={"calm": 3, "intellectual": 2, "masculine": 1},
        )
        assert ann.speaker_id == "100"
        assert ann.gender == "male"
        assert len(ann.traits) == 3

    def test_gender_inference_male(self, sample_speaker_index: dict) -> None:
        assert sample_speaker_index["100"].gender == "male"
        assert sample_speaker_index["400"].gender == "male"

    def test_gender_inference_female(self, sample_speaker_index: dict) -> None:
        assert sample_speaker_index["200"].gender == "female"
        assert sample_speaker_index["300"].gender == "female"

    def test_traits_merged_from_annotators(self, sample_speaker_index: dict) -> None:
        # Speaker 100 should have traits from all 3 annotators
        speaker = sample_speaker_index["100"]
        assert "calm" in speaker.traits
        assert "intellectual" in speaker.traits
        assert "sincere" in speaker.traits
        assert "slightly cool" in speaker.traits

    def test_annotator_agreement_tracked(self, sample_speaker_index: dict) -> None:
        speaker = sample_speaker_index["100"]
        # "calm" appears in all 3 annotators
        assert speaker.annotator_agreement["calm"] == 3
        # "sincere" appears in only 1 annotator
        assert speaker.annotator_agreement["sincere"] == 1


# ---------------------------------------------------------------------------
# VoiceAssignment tests
# ---------------------------------------------------------------------------


class TestVoiceAssignment:
    def test_create_voice_assignment(self) -> None:
        va = VoiceAssignment(
            character_name="Mr. Darcy",
            speaker_id="100",
            clip_path="train-clean-360/100/12345/100_12345_000001_000001.wav",
            reasoning="Matched because masculine, intellectual, calm tone fits reserved gentleman",
            confidence=0.85,
            is_major=True,
            method="llm",
            warning=None,
        )
        assert va.character_name == "Mr. Darcy"
        assert va.confidence == 0.85
        assert va.warning is None

    def test_voice_assignment_with_warning(self) -> None:
        va = VoiceAssignment(
            character_name="Servant",
            speaker_id="999",
            clip_path="train-clean-360/999/00000/999_00000_000001_000001.wav",
            reasoning="Best available match from limited pool",
            confidence=0.35,
            is_major=False,
            method="embedding",
            warning="Weak embedding match — consider manual review",
        )
        assert va.warning is not None
        assert "Weak" in va.warning

    def test_voice_assignment_serialization(self) -> None:
        va = VoiceAssignment(
            character_name="Elizabeth",
            speaker_id="200",
            clip_path="train-clean-360/200/11111/200_11111_000001_000001.wav",
            reasoning="Feminine, clear, intellectual matches witty heroine",
            confidence=0.92,
            is_major=True,
            method="llm",
            warning=None,
        )
        data = va.model_dump()
        assert data["character_name"] == "Elizabeth"
        assert data["method"] == "llm"
        # Round-trip through JSON
        json_str = json.dumps(data)
        restored = VoiceAssignment.model_validate_json(json_str)
        assert restored.character_name == "Elizabeth"
        assert restored.confidence == 0.92


# ---------------------------------------------------------------------------
# VoiceMap tests
# ---------------------------------------------------------------------------


class TestVoiceMap:
    def test_voice_map_json_roundtrip(self) -> None:
        narrator = VoiceAssignment(
            character_name="narrator",
            speaker_id="300",
            clip_path="train-clean-360/300/22222/300_22222_000001_000001.wav",
            reasoning="Calm, sincere female voice fits period drama narration",
            confidence=0.88,
            is_major=False,
            method="llm",
            warning=None,
        )
        character = VoiceAssignment(
            character_name="Mr. Darcy",
            speaker_id="100",
            clip_path="train-clean-360/100/12345/100_12345_000001_000001.wav",
            reasoning="Intellectual, calm masculine voice",
            confidence=0.85,
            is_major=True,
            method="llm",
            warning=None,
        )
        vm = VoiceMap(
            book_slug="pride-and-prejudice",
            narrator=narrator,
            characters=[character],
            metadata={
                "created_at": "2026-03-03",
                "libritts_subset": "train-clean-360",
                "total_speakers_evaluated": 904,
            },
        )
        # Serialize
        json_str = json.dumps(vm.model_dump(), indent=2)
        # Deserialize
        restored = VoiceMap.model_validate_json(json_str)
        assert restored.book_slug == "pride-and-prejudice"
        assert restored.narrator.speaker_id == "300"
        assert len(restored.characters) == 1
        assert restored.metadata["total_speakers_evaluated"] == 904


# ---------------------------------------------------------------------------
# Speaker index loading tests
# ---------------------------------------------------------------------------


class TestLoadSpeakerIndex:
    def test_loads_all_speakers(self, sample_speaker_index: dict) -> None:
        assert len(sample_speaker_index) == 4

    def test_speaker_ids_are_strings(self, sample_speaker_index: dict) -> None:
        for sid in sample_speaker_index:
            assert isinstance(sid, str)

    def test_traits_sorted(self, sample_speaker_index: dict) -> None:
        for speaker in sample_speaker_index.values():
            assert speaker.traits == sorted(speaker.traits)

    def test_trait_text_matches_traits(self, sample_speaker_index: dict) -> None:
        for speaker in sample_speaker_index.values():
            assert speaker.trait_text == ", ".join(speaker.traits)

    def test_missing_csv_raises_error(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="df1_en.csv"):
            load_speaker_index(tmp_path)


# ---------------------------------------------------------------------------
# Candidate filtering tests
# ---------------------------------------------------------------------------


class TestFilterCandidates:
    def test_filter_by_male(self, sample_speaker_index: dict) -> None:
        candidates = filter_candidates(sample_speaker_index, gender="male")
        assert all(c.gender == "male" for c in candidates)
        speaker_ids = {c.speaker_id for c in candidates}
        assert "100" in speaker_ids
        assert "400" in speaker_ids
        assert "200" not in speaker_ids

    def test_filter_by_female(self, sample_speaker_index: dict) -> None:
        candidates = filter_candidates(sample_speaker_index, gender="female")
        assert all(c.gender == "female" for c in candidates)
        speaker_ids = {c.speaker_id for c in candidates}
        assert "200" in speaker_ids
        assert "300" in speaker_ids

    def test_unknown_gender_returns_all(self, sample_speaker_index: dict) -> None:
        candidates = filter_candidates(sample_speaker_index, gender="unknown")
        assert len(candidates) == 4

    def test_age_filter_young_adult(self, sample_speaker_index: dict) -> None:
        candidates = filter_candidates(
            sample_speaker_index, gender="female", age_range="young adult"
        )
        # Should include speakers with "young" or "adult-like" in traits
        assert len(candidates) > 0
        # Speaker 200 has "young" trait
        speaker_ids = {c.speaker_id for c in candidates}
        assert "200" in speaker_ids

    def test_age_filter_elderly(self, sample_speaker_index: dict) -> None:
        candidates = filter_candidates(
            sample_speaker_index, gender="male", age_range="elderly"
        )
        # Should match speakers with "old" or "middle-aged" traits
        assert len(candidates) > 0

    def test_age_filter_fallback_when_no_match(self, sample_speaker_index: dict) -> None:
        # "child" age with male gender — no speakers have "childish" trait
        candidates = filter_candidates(
            sample_speaker_index, gender="male", age_range="child"
        )
        # Should fall back to all male speakers
        assert len(candidates) >= 2

    def test_results_sorted_by_speaker_id(self, sample_speaker_index: dict) -> None:
        candidates = filter_candidates(sample_speaker_index, gender="unknown")
        ids = [c.speaker_id for c in candidates]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# Cast classification tests
# ---------------------------------------------------------------------------


class TestClassifyCast:
    def test_major_minor_split(
        self, sample_characters: list[dict], sample_segments: list[dict]
    ) -> None:
        result = classify_cast(sample_characters, sample_segments, default_threshold=5)
        assert "Mr. Darcy" in result.major  # 8 dialogue lines
        assert "Elizabeth Bennet" in result.major  # 6 dialogue lines
        assert "Mary" in result.minor  # 2 dialogue lines

    def test_threshold_stored(
        self, sample_characters: list[dict], sample_segments: list[dict]
    ) -> None:
        result = classify_cast(sample_characters, sample_segments, default_threshold=5)
        assert result.threshold == 5

    def test_custom_threshold(
        self, sample_characters: list[dict], sample_segments: list[dict]
    ) -> None:
        # With threshold of 7, only Mr. Darcy (8) is major
        result = classify_cast(sample_characters, sample_segments, default_threshold=7)
        assert "Mr. Darcy" in result.major
        assert "Elizabeth Bennet" in result.minor

    def test_narrator_mode_third_person(
        self, sample_characters: list[dict], sample_segments: list[dict]
    ) -> None:
        result = classify_cast(sample_characters, sample_segments)
        assert result.narrator_mode == "third_person"

    def test_narrator_mode_first_person(
        self, sample_characters: list[dict]
    ) -> None:
        # Create segments with first-person narration
        segments = []
        for i in range(10):
            segments.append(
                {"id": i, "chapter": 1, "type": "narration", "speaker": "narrator",
                 "text": "I walked across the room and my heart raced."}
            )
        for i in range(10, 15):
            segments.append(
                {"id": i, "chapter": 1, "type": "dialogue", "speaker": "Mr. Darcy",
                 "text": "Hello."}
            )
        result = classify_cast(sample_characters, segments)
        assert result.narrator_mode == "first_person"

    def test_empty_segments(self, sample_characters: list[dict]) -> None:
        result = classify_cast(sample_characters, [])
        assert len(result.major) == 0
        assert len(result.minor) == 3
        assert result.narrator_mode == "third_person"
