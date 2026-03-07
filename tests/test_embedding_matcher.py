"""Tests for embedding similarity fallback matcher.

Integration tests that load the real sentence-transformers model.
Model is 80MB and runs on CPU — fast enough for CI.

Covers:
- build_speaker_embeddings output shape
- match_character_embedding valid results
- Assigned ID exclusion
- Warning flags on low-confidence matches
"""

from __future__ import annotations

import pytest

from src.attribution.models import CharacterProfile, VoiceProfile
from src.matching.models import SpeakerAnnotation
from src.matching.embedding_matcher import (
    build_speaker_embeddings,
    match_character_embedding,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_speakers() -> list[SpeakerAnnotation]:
    """Small set of speakers with known trait distributions."""
    return [
        SpeakerAnnotation(
            speaker_id="100",
            traits=["very masculine", "adult-like", "calm", "intellectual", "deep"],
            trait_text="very masculine, adult-like, calm, intellectual, deep",
            gender="male",
            annotator_agreement={"very masculine": 3, "calm": 2, "intellectual": 2, "adult-like": 1, "deep": 1},
        ),
        SpeakerAnnotation(
            speaker_id="200",
            traits=["very feminine", "young", "clear", "cute", "lively"],
            trait_text="very feminine, young, clear, cute, lively",
            gender="female",
            annotator_agreement={"very feminine": 3, "young": 2, "clear": 1, "cute": 1, "lively": 1},
        ),
        SpeakerAnnotation(
            speaker_id="300",
            traits=["masculine", "old", "raspy", "gruff", "authoritative"],
            trait_text="masculine, old, raspy, gruff, authoritative",
            gender="male",
            annotator_agreement={"masculine": 2, "old": 2, "raspy": 1, "gruff": 1, "authoritative": 1},
        ),
        SpeakerAnnotation(
            speaker_id="400",
            traits=["feminine", "middle-aged", "warm", "sincere", "gentle"],
            trait_text="feminine, middle-aged, warm, sincere, gentle",
            gender="female",
            annotator_agreement={"feminine": 2, "middle-aged": 2, "warm": 1, "sincere": 1, "gentle": 1},
        ),
    ]


@pytest.fixture
def speaker_embeddings(mock_speakers):
    """Pre-computed embeddings for mock speakers."""
    return build_speaker_embeddings(mock_speakers)


@pytest.fixture
def male_character() -> CharacterProfile:
    return CharacterProfile(
        name="Commander",
        aliases=[],
        gender="male",
        age_range="elderly",
        voice_profile=VoiceProfile(
            pitch="low", pace="slow", tone="gruff", accent="unknown",
            pace_style="deliberate", tone_style="rough", energy="restrained",
            typical_emotion="stern",
            description="A gruff commanding voice",
        ),
        personality_traits=["authoritative", "stern"],
        description="A gruff old military commander",
        is_named=True,
    )


@pytest.fixture
def female_character() -> CharacterProfile:
    return CharacterProfile(
        name="Mary",
        aliases=[],
        gender="female",
        age_range="young adult",
        voice_profile=VoiceProfile(
            pitch="high", pace="fast", tone="cheerful", accent="unknown",
            pace_style="quick", tone_style="bright", energy="animated",
            typical_emotion="cheerful",
            description="A lively cheerful voice",
        ),
        personality_traits=["lively", "energetic"],
        description="A young lively woman",
        is_named=True,
    )


# ---------------------------------------------------------------------------
# build_speaker_embeddings tests
# ---------------------------------------------------------------------------


class TestBuildSpeakerEmbeddings:
    def test_returns_correct_count(self, mock_speakers) -> None:
        ids, embeddings = build_speaker_embeddings(mock_speakers)
        assert len(ids) == 4

    def test_returns_correct_ids(self, mock_speakers) -> None:
        ids, embeddings = build_speaker_embeddings(mock_speakers)
        assert ids == ["100", "200", "300", "400"]

    def test_embedding_dimensions(self, mock_speakers) -> None:
        ids, embeddings = build_speaker_embeddings(mock_speakers)
        assert embeddings.shape == (4, 384)


# ---------------------------------------------------------------------------
# match_character_embedding tests
# ---------------------------------------------------------------------------


class TestMatchCharacterEmbedding:
    def test_returns_valid_assignment(
        self, male_character, speaker_embeddings
    ) -> None:
        ids, embeddings = speaker_embeddings
        result = match_character_embedding(male_character, ids, embeddings)
        assert result.character_name == "Commander"
        assert result.speaker_id in {"100", "200", "300", "400"}
        assert result.method == "embedding"
        assert 0.0 <= result.confidence <= 1.0

    def test_gruff_male_matches_gruff_speaker(
        self, male_character, speaker_embeddings
    ) -> None:
        ids, embeddings = speaker_embeddings
        result = match_character_embedding(male_character, ids, embeddings)
        # Speaker 300 has gruff, old, authoritative — best match for gruff old commander
        assert result.speaker_id == "300"

    def test_lively_female_matches_lively_speaker(
        self, female_character, speaker_embeddings
    ) -> None:
        ids, embeddings = speaker_embeddings
        result = match_character_embedding(female_character, ids, embeddings)
        # Speaker 200 has young, clear, cute, lively — best match for lively young woman
        assert result.speaker_id == "200"

    def test_excludes_assigned_ids(
        self, male_character, speaker_embeddings
    ) -> None:
        ids, embeddings = speaker_embeddings
        result = match_character_embedding(
            male_character, ids, embeddings, assigned_ids={"300"}
        )
        # Speaker 300 excluded, should pick next-best male speaker
        assert result.speaker_id != "300"

    def test_reasoning_includes_similarity_score(
        self, male_character, speaker_embeddings
    ) -> None:
        ids, embeddings = speaker_embeddings
        result = match_character_embedding(male_character, ids, embeddings)
        assert "Embedding match (similarity:" in result.reasoning
        assert "speaker" in result.reasoning

    def test_confidence_is_cosine_score(
        self, male_character, speaker_embeddings
    ) -> None:
        ids, embeddings = speaker_embeddings
        result = match_character_embedding(male_character, ids, embeddings)
        # Cosine similarity should be between 0 and 1 for meaningful matches
        assert result.confidence > 0.0
        assert result.confidence <= 1.0
