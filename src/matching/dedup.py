"""Major character uniqueness enforcement and minor co-occurrence checking.

Ensures no two major characters share the same LibriTTS-P speaker.
Also prevents minor characters who appear in the same chapter from
sharing a speaker (they'd sound identical in the same scene).

When duplicates are found, the lower-confidence assignment is swapped
to the next-best available speaker, prioritizing distinctiveness.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from itertools import combinations
from typing import Any

from src.matching.models import CastClassification, SpeakerAnnotation, VoiceAssignment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Chapter co-occurrence
# ---------------------------------------------------------------------------


def _get_chapter_cooccurrence(segments: list[dict]) -> set[tuple[str, str]]:
    """Find pairs of speakers who appear in the same chapter.

    Args:
        segments: Attributed segments with chapter and speaker fields.

    Returns:
        Set of (speaker_a, speaker_b) tuples (alphabetically ordered)
        for speakers who co-occur in at least one chapter.
    """
    chapter_speakers: dict[int, set[str]] = defaultdict(set)
    for seg in segments:
        chapter = seg.get("chapter", 0)
        speaker = seg.get("speaker", "")
        if speaker and speaker != "narrator" and speaker != "unknown":
            chapter_speakers[chapter].add(speaker)

    cooccurring: set[tuple[str, str]] = set()
    for speakers in chapter_speakers.values():
        for a, b in combinations(sorted(speakers), 2):
            cooccurring.add((a, b))

    return cooccurring


def _find_next_available(
    character_name: str,
    excluded_ids: set[str],
    candidates: list[SpeakerAnnotation] | None,
    speaker_ids: list[str] | None = None,
    speaker_embeddings: Any = None,
) -> tuple[str, float] | None:
    """Find next available speaker for reassignment.

    Tries embedding matcher if available, otherwise picks from candidate pool.

    Returns:
        (speaker_id, confidence) or None if no alternatives found.
    """
    # Try embedding matcher
    if speaker_ids is not None and speaker_embeddings is not None:
        try:
            from src.matching.embedding_matcher import _get_model
            from sentence_transformers import util

            model = _get_model()
            # Encode a generic description for the character
            char_embedding = model.encode(
                f"{character_name} voice", convert_to_tensor=True, show_progress_bar=False
            )
            scores = util.cos_sim(char_embedding, speaker_embeddings)[0]
            scored = [
                (speaker_ids[i], float(scores[i]))
                for i in range(len(speaker_ids))
                if speaker_ids[i] not in excluded_ids
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            if scored:
                return scored[0]
        except Exception:
            pass

    # Fallback: pick from candidate pool
    if candidates:
        for c in candidates:
            if c.speaker_id not in excluded_ids:
                return (c.speaker_id, 0.3)  # Low confidence for pool fallback

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enforce_uniqueness(
    assignments: list[VoiceAssignment],
    classification: CastClassification,
    segments: list[dict],
    candidates_by_character: dict[str, list[SpeakerAnnotation]] | None = None,
    speaker_ids: list[str] | None = None,
    speaker_embeddings: Any = None,
) -> list[VoiceAssignment]:
    """Enforce voice uniqueness constraints on assignments.

    Rules:
    1. No two major characters may share the same speaker.
    2. Minor characters may share a speaker, but NOT if they appear
       in the same chapter (they'd sound identical in a scene).

    When duplicates are found, the lower-confidence assignment is
    reassigned to the next-best available speaker.

    Args:
        assignments: List of VoiceAssignment objects to check.
        classification: CastClassification with major/minor lists.
        segments: Attributed segments for co-occurrence checking.
        candidates_by_character: Optional candidate pools per character.
        speaker_ids: Optional full speaker ID list for embedding fallback.
        speaker_embeddings: Optional pre-computed speaker embeddings.

    Returns:
        Updated list of VoiceAssignment objects with duplicates resolved.
    """
    if candidates_by_character is None:
        candidates_by_character = {}

    # Work on a copy
    result = [a.model_copy() for a in assignments]

    # Track all assigned speaker IDs
    assigned_ids = {a.speaker_id for a in result}

    # --- Major character dedup ---
    major_set = set(classification.major)
    major_assignments = [a for a in result if a.character_name in major_set]

    # Find duplicates among major characters
    speaker_to_majors: dict[str, list[VoiceAssignment]] = defaultdict(list)
    for a in major_assignments:
        speaker_to_majors[a.speaker_id].append(a)

    for speaker_id, group in speaker_to_majors.items():
        if len(group) <= 1:
            continue

        # Sort by confidence descending — keep highest
        group.sort(key=lambda a: a.confidence, reverse=True)
        keeper = group[0]
        logger.info(
            "Dedup: keeping %s on speaker %s (confidence: %.2f)",
            keeper.character_name,
            speaker_id,
            keeper.confidence,
        )

        for to_swap in group[1:]:
            old_id = to_swap.speaker_id
            candidates = candidates_by_character.get(to_swap.character_name, [])
            new_match = _find_next_available(
                to_swap.character_name,
                assigned_ids,
                candidates,
                speaker_ids,
                speaker_embeddings,
            )

            if new_match:
                new_id, new_confidence = new_match
                # Update in the result list
                for i, a in enumerate(result):
                    if a.character_name == to_swap.character_name:
                        result[i] = a.model_copy(
                            update={
                                "speaker_id": new_id,
                                "confidence": new_confidence,
                                "reasoning": (
                                    f"Reassigned for distinctiveness — "
                                    f"originally matched speaker {old_id}. "
                                    f"{a.reasoning}"
                                ),
                                "warning": (
                                    a.warning or "Reassigned for uniqueness"
                                ),
                            }
                        )
                        assigned_ids.add(new_id)
                        logger.info(
                            "Dedup: swapped %s from speaker %s to %s for uniqueness",
                            to_swap.character_name,
                            old_id,
                            new_id,
                        )
                        break
            else:
                # No alternative available — keep with warning
                for i, a in enumerate(result):
                    if a.character_name == to_swap.character_name:
                        result[i] = a.model_copy(
                            update={
                                "warning": (
                                    "Shares speaker with another major character — "
                                    "no alternative available"
                                ),
                            }
                        )
                        logger.warning(
                            "Dedup: no alternative for %s (shares speaker %s)",
                            to_swap.character_name,
                            old_id,
                        )
                        break

    # --- Minor character co-occurrence dedup ---
    minor_set = set(classification.minor)
    minor_assignments = [a for a in result if a.character_name in minor_set]
    cooccurrence = _get_chapter_cooccurrence(segments)

    # Check pairs of minor characters who share a speaker AND co-occur
    minor_by_speaker: dict[str, list[VoiceAssignment]] = defaultdict(list)
    for a in minor_assignments:
        minor_by_speaker[a.speaker_id].append(a)

    for speaker_id, group in minor_by_speaker.items():
        if len(group) <= 1:
            continue

        for a, b in combinations(group, 2):
            pair = tuple(sorted([a.character_name, b.character_name]))
            if pair in cooccurrence:
                # These two co-occur AND share a speaker — fix it
                lower = b if b.confidence <= a.confidence else a
                old_id = lower.speaker_id
                candidates = candidates_by_character.get(lower.character_name, [])
                new_match = _find_next_available(
                    lower.character_name,
                    assigned_ids,
                    candidates,
                    speaker_ids,
                    speaker_embeddings,
                )

                if new_match:
                    new_id, new_confidence = new_match
                    for i, r in enumerate(result):
                        if r.character_name == lower.character_name:
                            result[i] = r.model_copy(
                                update={
                                    "speaker_id": new_id,
                                    "confidence": new_confidence,
                                    "reasoning": (
                                        f"Reassigned — co-occurs with "
                                        f"{(a if lower == b else b).character_name} "
                                        f"in same chapter. {r.reasoning}"
                                    ),
                                    "warning": r.warning or "Reassigned for co-occurrence",
                                }
                            )
                            assigned_ids.add(new_id)
                            logger.info(
                                "Dedup: swapped minor %s from speaker %s to %s "
                                "(co-occurs with %s)",
                                lower.character_name,
                                old_id,
                                new_id,
                                (a if lower == b else b).character_name,
                            )
                            break

    return result
