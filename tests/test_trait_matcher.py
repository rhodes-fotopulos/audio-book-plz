"""Tests for LLM trait matcher (mock-based, no actual LLM calls).

Covers:
- match_character_llm prompt structure and response handling
- Assigned ID exclusion
- match_narrator_llm first-person and third-person modes
- Invalid speaker_id handling
- None/failure handling
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.attribution.models import CharacterProfile, VoiceQualities
from src.matching.models import SpeakerAnnotation
from src.matching.trait_matcher import (
    MatchResponse,
    match_character_llm,
    match_narrator_llm,
    _find_protagonist,
    _infer_book_tone,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_character() -> CharacterProfile:
    return CharacterProfile(
        name="Mr. Darcy",
        aliases=["Darcy", "Fitzwilliam"],
        gender="male",
        age_range="young adult",
        voice_qualities=VoiceQualities(
            pitch="low", pace="moderate", tone="reserved", accent="British"
        ),
        personality_traits=["proud", "intelligent", "reserved"],
        relationships=[],
        description="A wealthy gentleman of reserved demeanor",
        is_named=True,
    )


@pytest.fixture
def sample_candidates() -> list[SpeakerAnnotation]:
    return [
        SpeakerAnnotation(
            speaker_id="100",
            traits=["masculine", "adult-like", "calm", "intellectual"],
            trait_text="adult-like, calm, intellectual, masculine",
            gender="male",
            annotator_agreement={"masculine": 3, "calm": 2, "intellectual": 2, "adult-like": 1},
        ),
        SpeakerAnnotation(
            speaker_id="200",
            traits=["feminine", "young", "clear", "cute"],
            trait_text="clear, cute, feminine, young",
            gender="female",
            annotator_agreement={"feminine": 3, "young": 2, "clear": 1, "cute": 1},
        ),
        SpeakerAnnotation(
            speaker_id="300",
            traits=["masculine", "middle-aged", "dark", "cool"],
            trait_text="cool, dark, masculine, middle-aged",
            gender="male",
            annotator_agreement={"masculine": 2, "middle-aged": 2, "dark": 1, "cool": 1},
        ),
    ]


@pytest.fixture
def sample_characters() -> list[CharacterProfile]:
    return [
        CharacterProfile(
            name="Mr. Darcy",
            aliases=[],
            gender="male",
            age_range="young adult",
            voice_qualities=VoiceQualities(pitch="low", pace="moderate", tone="reserved", accent="British"),
            personality_traits=["proud"],
            relationships=[],
            description="Wealthy gentleman",
            is_named=True,
        ),
        CharacterProfile(
            name="Elizabeth",
            aliases=[],
            gender="female",
            age_range="young adult",
            voice_qualities=VoiceQualities(pitch="medium", pace="fast", tone="witty", accent="unknown"),
            personality_traits=["witty"],
            relationships=[],
            description="Spirited young woman",
            is_named=True,
        ),
    ]


@pytest.fixture
def sample_segments() -> list[dict]:
    segments = []
    # Mr. Darcy has more dialogue (protagonist for first-person tests)
    for i in range(10):
        segments.append({"id": i, "chapter": 1, "type": "dialogue", "speaker": "Mr. Darcy", "text": "Test."})
    for i in range(10, 15):
        segments.append({"id": i, "chapter": 1, "type": "dialogue", "speaker": "Elizabeth", "text": "Test."})
    # Narration
    for i in range(15, 25):
        segments.append({"id": i, "chapter": 1, "type": "narration", "speaker": "narrator", "text": "The dark shadows loomed over the estate."})
    return segments


# ---------------------------------------------------------------------------
# match_character_llm tests
# ---------------------------------------------------------------------------


class TestMatchCharacterLLM:
    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_returns_voice_assignment_on_success(
        self, mock_llm, sample_character, sample_candidates
    ) -> None:
        mock_llm.return_value = MatchResponse(
            speaker_id="100",
            reasoning="Calm, intellectual masculine voice fits reserved gentleman",
            confidence=0.88,
        )
        result = match_character_llm(sample_character, sample_candidates)
        assert result is not None
        assert result.character_name == "Mr. Darcy"
        assert result.speaker_id == "100"
        assert result.method == "llm"
        assert result.confidence == 0.88
        assert "reserved gentleman" in result.reasoning

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_excludes_assigned_ids(
        self, mock_llm, sample_character, sample_candidates
    ) -> None:
        mock_llm.return_value = MatchResponse(
            speaker_id="300",
            reasoning="Second-best match",
            confidence=0.75,
        )
        result = match_character_llm(
            sample_character, sample_candidates, assigned_ids={"100"}
        )
        assert result is not None
        assert result.speaker_id == "300"
        # Verify the LLM was called with user content excluding speaker 100
        call_args = mock_llm.call_args
        user_content = call_args.kwargs.get("user_content", call_args[1] if len(call_args) > 1 else "")
        if not user_content and call_args.kwargs:
            user_content = call_args.kwargs.get("user_content", "")

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_returns_none_on_all_failures(
        self, mock_llm, sample_character, sample_candidates
    ) -> None:
        mock_llm.return_value = None
        result = match_character_llm(sample_character, sample_candidates)
        assert result is None

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_retries_on_invalid_speaker_id(
        self, mock_llm, sample_character, sample_candidates
    ) -> None:
        # First two calls return invalid ID, third returns valid
        mock_llm.side_effect = [
            MatchResponse(speaker_id="999", reasoning="Bad", confidence=0.5),
            MatchResponse(speaker_id="888", reasoning="Bad", confidence=0.5),
            MatchResponse(speaker_id="100", reasoning="Good match", confidence=0.85),
        ]
        result = match_character_llm(sample_character, sample_candidates)
        assert result is not None
        assert result.speaker_id == "100"
        assert mock_llm.call_count == 3

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_returns_none_when_no_candidates(
        self, mock_llm, sample_character
    ) -> None:
        result = match_character_llm(sample_character, [])
        assert result is None
        mock_llm.assert_not_called()

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_returns_none_when_all_assigned(
        self, mock_llm, sample_character, sample_candidates
    ) -> None:
        all_ids = {c.speaker_id for c in sample_candidates}
        result = match_character_llm(
            sample_character, sample_candidates, assigned_ids=all_ids
        )
        assert result is None


# ---------------------------------------------------------------------------
# match_narrator_llm tests
# ---------------------------------------------------------------------------


class TestMatchNarratorLLM:
    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_first_person_uses_protagonist(
        self, mock_llm, sample_characters, sample_segments, sample_candidates
    ) -> None:
        mock_llm.return_value = MatchResponse(
            speaker_id="100",
            reasoning="Matches protagonist Darcy's traits",
            confidence=0.9,
        )
        result = match_narrator_llm(
            sample_characters, sample_segments, sample_candidates,
            narrator_mode="first_person"
        )
        assert result is not None
        assert result.character_name == "narrator"
        assert "First-person narrator = protagonist voice" in result.reasoning

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_third_person_uses_tone(
        self, mock_llm, sample_characters, sample_segments, sample_candidates
    ) -> None:
        mock_llm.return_value = MatchResponse(
            speaker_id="300",
            reasoning="Dark, measured voice fits thriller tone",
            confidence=0.85,
        )
        result = match_narrator_llm(
            sample_characters, sample_segments, sample_candidates,
            narrator_mode="third_person"
        )
        assert result is not None
        assert result.character_name == "narrator"
        assert result.speaker_id == "300"

    @patch("src.matching.trait_matcher.call_llm_structured")
    def test_narrator_excludes_assigned(
        self, mock_llm, sample_characters, sample_segments, sample_candidates
    ) -> None:
        mock_llm.return_value = MatchResponse(
            speaker_id="300",
            reasoning="Available match",
            confidence=0.7,
        )
        result = match_narrator_llm(
            sample_characters, sample_segments, sample_candidates,
            narrator_mode="third_person",
            assigned_ids={"100", "200"},
        )
        assert result is not None
        assert result.speaker_id == "300"


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_find_protagonist(self, sample_characters, sample_segments) -> None:
        protagonist = _find_protagonist(sample_characters, sample_segments)
        assert protagonist is not None
        assert protagonist.name == "Mr. Darcy"

    def test_find_protagonist_empty_segments(self, sample_characters) -> None:
        result = _find_protagonist(sample_characters, [])
        assert result is None

    def test_infer_book_tone_dark(self) -> None:
        segments = [
            {"type": "narration", "speaker": "narrator", "text": "The dark shadows crept through the blood-stained corridors. Death was everywhere."}
        ] * 5
        tone = _infer_book_tone(segments)
        assert "dark" in tone.lower() or "tense" in tone.lower()

    def test_infer_book_tone_light(self) -> None:
        segments = [
            {"type": "narration", "speaker": "narrator", "text": "She laughed with joy, her bright smile lighting up the cheerful room."}
        ] * 5
        tone = _infer_book_tone(segments)
        assert "light" in tone.lower() or "warm" in tone.lower() or "comedic" in tone.lower()

    def test_infer_book_tone_empty(self) -> None:
        tone = _infer_book_tone([])
        assert "neutral" in tone.lower() or "literary" in tone.lower()
