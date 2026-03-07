"""Sentence-transformers embedding similarity fallback for voice matching.

When LLM context is tight or the cast exceeds what fits in a single
LLM call, this module provides a fast, local embedding-based alternative.

Uses all-MiniLM-L6-v2 (80MB) on CPU to encode character trait descriptions
and speaker annotations into 384-dim vectors, then ranks by cosine similarity.
"""

from __future__ import annotations

import logging
from typing import Any

from src.attribution.models import CharacterProfile
from src.matching.models import SpeakerAnnotation, VoiceAssignment

logger = logging.getLogger(__name__)

# Module-level model cache (loaded once per session)
_model = None


def _get_model():
    """Lazy-load sentence-transformers model on CPU."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        logger.info("Loaded all-MiniLM-L6-v2 sentence-transformer model on CPU")
    return _model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_speaker_embeddings(
    speakers: list[SpeakerAnnotation],
) -> tuple[list[str], Any]:
    """Build embeddings for all speaker trait descriptions.

    Encodes each speaker's trait_text into a 384-dimensional vector
    using all-MiniLM-L6-v2. Results are cached as a tensor for
    efficient cosine similarity computation.

    Args:
        speakers: List of SpeakerAnnotation objects with trait_text.

    Returns:
        Tuple of (speaker_id_list, embeddings_tensor).
        speaker_id_list[i] corresponds to embeddings_tensor[i].
    """
    model = _get_model()

    speaker_ids = [s.speaker_id for s in speakers]
    trait_texts = [s.trait_text for s in speakers]

    embeddings = model.encode(trait_texts, convert_to_tensor=True, show_progress_bar=False)

    logger.info("Built embeddings for %d speakers", len(speakers))
    return speaker_ids, embeddings


def _build_character_text(character: CharacterProfile) -> str:
    """Build a natural language description for embedding from character traits."""
    parts = []

    # Gender and age
    if character.gender != "unknown":
        parts.append(character.gender)
    if character.age_range != "unknown":
        parts.append(character.age_range)

    # Voice profile — coarse traits only (LibriTTS-P aligned)
    vp = character.voice_profile
    for attr in [vp.pitch, vp.pace, vp.tone, vp.accent]:
        if attr != "unknown":
            parts.append(attr)

    # Personality
    parts.extend(character.personality_traits)

    return ", ".join(parts) if parts else "neutral voice"


def match_character_embedding(
    character: CharacterProfile,
    speaker_ids: list[str],
    speaker_embeddings: Any,
    assigned_ids: set[str] | None = None,
    top_k: int = 5,
) -> VoiceAssignment:
    """Match a character to a speaker using embedding cosine similarity.

    Encodes the character's trait description and computes cosine
    similarity against all pre-computed speaker embeddings. Returns
    the best available (non-assigned) match.

    Args:
        character: Character profile with voice qualities.
        speaker_ids: List of speaker IDs corresponding to embeddings.
        speaker_embeddings: Pre-computed speaker embeddings tensor.
        assigned_ids: Speaker IDs to exclude from results.
        top_k: Number of top candidates to consider (for logging).

    Returns:
        VoiceAssignment for the best matching speaker.
    """
    from sentence_transformers import util

    if assigned_ids is None:
        assigned_ids = set()

    model = _get_model()
    char_text = _build_character_text(character)
    char_embedding = model.encode(char_text, convert_to_tensor=True, show_progress_bar=False)

    # Compute cosine similarity against all speakers
    scores = util.cos_sim(char_embedding, speaker_embeddings)[0]

    # Build (speaker_id, score) pairs and sort by score descending
    scored = [
        (speaker_ids[i], float(scores[i]))
        for i in range(len(speaker_ids))
        if speaker_ids[i] not in assigned_ids
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    if not scored:
        # Extreme fallback: all speakers assigned, pick any
        logger.warning("All speakers assigned, selecting first available for %s", character.name)
        scored = [(speaker_ids[0], float(scores[0]))]

    best_id, best_score = scored[0]

    # Warning for low confidence
    warning = None
    if best_score < 0.5:
        warning = "Weak embedding match — consider manual review"

    reasoning = (
        f"Embedding match (similarity: {best_score:.3f}) — "
        f"{char_text} best matches speaker {best_id} traits"
    )

    return VoiceAssignment(
        character_name=character.name,
        speaker_id=best_id,
        clip_path="",  # Set later by clip_selector
        reasoning=reasoning,
        confidence=round(best_score, 3),
        is_major=False,  # Caller updates this
        method="embedding",
        warning=warning,
    )
