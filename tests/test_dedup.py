"""Tests for dedup enforcement (uniqueness and co-occurrence).

Covers:
- No changes when assignments are already unique
- Major character dedup (higher confidence kept)
- Minor character sharing allowed in different chapters
- Minor character sharing blocked in same chapter
- Warning flags on reassigned characters
- Edge case: no alternative available
"""

from __future__ import annotations

import pytest

from src.matching.models import CastClassification, SpeakerAnnotation, VoiceAssignment
from src.matching.dedup import enforce_uniqueness, _get_chapter_cooccurrence


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_assignment(
    name: str, speaker_id: str, confidence: float = 0.8, is_major: bool = True
) -> VoiceAssignment:
    return VoiceAssignment(
        character_name=name,
        speaker_id=speaker_id,
        clip_path="",
        reasoning=f"Matched {name} to speaker {speaker_id}",
        confidence=confidence,
        is_major=is_major,
        method="llm",
        warning=None,
    )


@pytest.fixture
def candidates_pool() -> dict[str, list[SpeakerAnnotation]]:
    """Candidate pools for reassignment."""
    alt_speaker = SpeakerAnnotation(
        speaker_id="999",
        traits=["neutral"],
        trait_text="neutral",
        gender="unknown",
        annotator_agreement={"neutral": 1},
    )
    alt_speaker_2 = SpeakerAnnotation(
        speaker_id="888",
        traits=["neutral"],
        trait_text="neutral",
        gender="unknown",
        annotator_agreement={"neutral": 1},
    )
    return {
        "Darcy": [alt_speaker],
        "Bingley": [alt_speaker, alt_speaker_2],
        "Mary": [alt_speaker],
        "Kitty": [alt_speaker_2],
    }


# ---------------------------------------------------------------------------
# Chapter co-occurrence tests
# ---------------------------------------------------------------------------


class TestChapterCooccurrence:
    def test_cooccurrence_detected(self) -> None:
        segments = [
            {"chapter": 1, "speaker": "Alice", "type": "dialogue"},
            {"chapter": 1, "speaker": "Bob", "type": "dialogue"},
        ]
        cooc = _get_chapter_cooccurrence(segments)
        assert ("Alice", "Bob") in cooc

    def test_different_chapters_no_cooccurrence(self) -> None:
        segments = [
            {"chapter": 1, "speaker": "Alice", "type": "dialogue"},
            {"chapter": 2, "speaker": "Bob", "type": "dialogue"},
        ]
        cooc = _get_chapter_cooccurrence(segments)
        assert ("Alice", "Bob") not in cooc

    def test_narrator_excluded(self) -> None:
        segments = [
            {"chapter": 1, "speaker": "narrator", "type": "narration"},
            {"chapter": 1, "speaker": "Alice", "type": "dialogue"},
        ]
        cooc = _get_chapter_cooccurrence(segments)
        # narrator shouldn't appear in co-occurrence pairs
        assert not any("narrator" in pair for pair in cooc)


# ---------------------------------------------------------------------------
# Major character dedup tests
# ---------------------------------------------------------------------------


class TestMajorDedup:
    def test_no_changes_when_unique(self, candidates_pool) -> None:
        assignments = [
            _make_assignment("Darcy", "100", 0.9),
            _make_assignment("Bingley", "200", 0.85),
        ]
        classification = CastClassification(
            major=["Darcy", "Bingley"], minor=[], threshold=5, narrator_mode="third_person"
        )
        result = enforce_uniqueness(
            assignments, classification, [], candidates_pool
        )
        assert result[0].speaker_id == "100"
        assert result[1].speaker_id == "200"
        assert result[0].warning is None
        assert result[1].warning is None

    def test_swaps_lower_confidence_major(self, candidates_pool) -> None:
        # Both major characters assigned to speaker 100
        assignments = [
            _make_assignment("Darcy", "100", 0.9),
            _make_assignment("Bingley", "100", 0.7),
        ]
        classification = CastClassification(
            major=["Darcy", "Bingley"], minor=[], threshold=5, narrator_mode="third_person"
        )
        result = enforce_uniqueness(
            assignments, classification, [], candidates_pool
        )
        # Darcy keeps 100 (higher confidence)
        darcy = next(a for a in result if a.character_name == "Darcy")
        assert darcy.speaker_id == "100"
        # Bingley reassigned
        bingley = next(a for a in result if a.character_name == "Bingley")
        assert bingley.speaker_id != "100"
        assert "Reassigned for distinctiveness" in bingley.reasoning

    def test_warning_set_on_reassigned(self, candidates_pool) -> None:
        assignments = [
            _make_assignment("Darcy", "100", 0.9),
            _make_assignment("Bingley", "100", 0.7),
        ]
        classification = CastClassification(
            major=["Darcy", "Bingley"], minor=[], threshold=5, narrator_mode="third_person"
        )
        result = enforce_uniqueness(
            assignments, classification, [], candidates_pool
        )
        bingley = next(a for a in result if a.character_name == "Bingley")
        assert bingley.warning is not None

    def test_no_swap_when_no_alternative(self) -> None:
        # No candidates available for reassignment
        assignments = [
            _make_assignment("Darcy", "100", 0.9),
            _make_assignment("Bingley", "100", 0.7),
        ]
        classification = CastClassification(
            major=["Darcy", "Bingley"], minor=[], threshold=5, narrator_mode="third_person"
        )
        # Empty candidates and assigned_ids blocks all alternatives
        result = enforce_uniqueness(
            assignments, classification, [], candidates_by_character={}
        )
        bingley = next(a for a in result if a.character_name == "Bingley")
        # Should have warning about sharing
        assert bingley.warning is not None
        assert "no alternative" in bingley.warning.lower()


# ---------------------------------------------------------------------------
# Minor character dedup tests
# ---------------------------------------------------------------------------


class TestMinorDedup:
    def test_sharing_allowed_different_chapters(self, candidates_pool) -> None:
        assignments = [
            _make_assignment("Mary", "100", 0.6, is_major=False),
            _make_assignment("Kitty", "100", 0.55, is_major=False),
        ]
        classification = CastClassification(
            major=[], minor=["Mary", "Kitty"], threshold=5, narrator_mode="third_person"
        )
        # Different chapters — no co-occurrence
        segments = [
            {"chapter": 1, "speaker": "Mary", "type": "dialogue"},
            {"chapter": 2, "speaker": "Kitty", "type": "dialogue"},
        ]
        result = enforce_uniqueness(
            assignments, classification, segments, candidates_pool
        )
        # Both keep speaker 100
        mary = next(a for a in result if a.character_name == "Mary")
        kitty = next(a for a in result if a.character_name == "Kitty")
        assert mary.speaker_id == "100"
        assert kitty.speaker_id == "100"

    def test_sharing_blocked_same_chapter(self, candidates_pool) -> None:
        assignments = [
            _make_assignment("Mary", "100", 0.6, is_major=False),
            _make_assignment("Kitty", "100", 0.55, is_major=False),
        ]
        classification = CastClassification(
            major=[], minor=["Mary", "Kitty"], threshold=5, narrator_mode="third_person"
        )
        # Same chapter — co-occurrence
        segments = [
            {"chapter": 1, "speaker": "Mary", "type": "dialogue"},
            {"chapter": 1, "speaker": "Kitty", "type": "dialogue"},
        ]
        result = enforce_uniqueness(
            assignments, classification, segments, candidates_pool
        )
        # Lower confidence (Kitty) should be reassigned
        kitty = next(a for a in result if a.character_name == "Kitty")
        assert kitty.speaker_id != "100"
        assert "co-occurs" in kitty.reasoning.lower()
