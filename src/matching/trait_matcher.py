"""LLM-based trait comparison for voice-character matching.

Uses Qwen3 8B via Ollama to compare character voice traits from
CharacterProfile against LibriTTS-P speaker annotations. Acts as
a "casting director" selecting the best voice actor for each role.

Also handles narrator voice matching with first-person/third-person
mode awareness.
"""

from __future__ import annotations

import logging
from collections import Counter

from pydantic import BaseModel, ConfigDict

from src.attribution.llm_client import call_llm_structured
from src.attribution.models import CharacterProfile
from src.matching.models import SpeakerAnnotation, VoiceAssignment

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM response schema
# ---------------------------------------------------------------------------


class MatchResponse(BaseModel):
    """LLM response for a single voice match.

    Returned by Qwen3 8B when comparing character traits to speaker
    annotations. The speaker_id must be from the provided candidate list.
    """

    model_config = ConfigDict(strict=True)

    speaker_id: str
    """LibriTTS-P speaker ID selected as best match."""

    reasoning: str
    """Brief casting-director style reasoning for the match."""

    confidence: float
    """Confidence score 0.0-1.0 for this match."""


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_CHARACTER_SYSTEM_PROMPT = """\
You are a casting director matching a fictional character to a voice actor.

Given a character profile and a list of available voice actors (LibriTTS-P speakers \
with annotated vocal traits), select the BEST match.

Matching priorities (in order):
1. Gender match is mandatory
2. Balance age, vocal quality, and personality — no single factor dominates
3. Prioritize distinctiveness — a voice that stands out for this character is \
better than a generic good match
4. Include brief reasoning explaining why this voice fits the role

Return the speaker_id of your best match, your reasoning, and a confidence score (0.0-1.0).\
"""

_NARRATOR_THIRD_PERSON_PROMPT = """\
You are a casting director selecting a narrator voice for an audiobook.

Match a narrator voice that fits the book's tone:
- Dark thrillers get a lower, tense narrator voice
- Comedies get a lighter, energetic voice
- Literary fiction gets a measured, intellectual voice
- Romance gets a warm, expressive voice

The narrator must sound distinct from character voices. \
Select from the available speakers based on the book's tone description.

Return the speaker_id of your best match, your reasoning, and a confidence score (0.0-1.0).\
"""

_NARRATOR_FIRST_PERSON_PROMPT = """\
You are a casting director selecting a narrator voice for a first-person audiobook.

In first-person narration, the narrator IS the protagonist. \
Match the narrator voice to the protagonist's character traits.

The narrator's voice should feel like the protagonist speaking directly to the listener.

Return the speaker_id of your best match, your reasoning, and a confidence score (0.0-1.0).\
"""


# ---------------------------------------------------------------------------
# Character matching
# ---------------------------------------------------------------------------


def _build_character_description(character: CharacterProfile) -> str:
    """Build a natural language description of a character's voice traits."""
    parts = [f"Character: {character.name}"]
    parts.append(f"Gender: {character.gender}")
    parts.append(f"Age: {character.age_range}")

    vp = character.voice_profile
    voice_parts = []
    if vp.pitch != "unknown":
        voice_parts.append(f"{vp.pitch} pitch")
    if vp.pace != "unknown":
        voice_parts.append(f"{vp.pace} pace")
    if vp.tone != "unknown":
        voice_parts.append(f"{vp.tone} tone")
    if vp.accent != "unknown":
        voice_parts.append(f"{vp.accent} accent")
    if voice_parts:
        parts.append(f"Voice: {', '.join(voice_parts)}")

    # Rich descriptors for LLM casting nuance
    style_parts = []
    if vp.pace_style != "unknown":
        style_parts.append(f"{vp.pace_style} speaking style")
    if vp.tone_style != "unknown":
        style_parts.append(f"{vp.tone_style} vocal quality")
    if vp.energy != "unknown":
        style_parts.append(f"{vp.energy} energy")
    if vp.typical_emotion != "unknown":
        style_parts.append(f"typically {vp.typical_emotion}")
    if style_parts:
        parts.append(f"Style: {', '.join(style_parts)}")

    if vp.description and vp.description != "unknown":
        parts.append(f"Voice summary: {vp.description}")

    if character.personality_traits:
        parts.append(f"Personality: {', '.join(character.personality_traits)}")
    if character.description:
        parts.append(f"Description: {character.description}")

    return "\n".join(parts)


def _build_candidates_text(
    candidates: list[SpeakerAnnotation], assigned_ids: set[str]
) -> str:
    """Build text listing available candidate speakers."""
    available = [c for c in candidates if c.speaker_id not in assigned_ids]
    if not available:
        return "No available candidates."

    lines = []
    for speaker in available:
        lines.append(f"Speaker {speaker.speaker_id}: {speaker.trait_text}")
    return "\n".join(lines)


def match_character_llm(
    character: CharacterProfile,
    candidates: list[SpeakerAnnotation],
    assigned_ids: set[str] | None = None,
) -> VoiceAssignment | None:
    """Match a character to a LibriTTS-P speaker using LLM trait comparison.

    Sends character profile and candidate speaker annotations to Qwen3 8B
    for casting-director style matching. Falls back to None if all attempts
    fail (caller should use embedding matcher).

    Args:
        character: Character profile with voice qualities and traits.
        candidates: Pre-filtered candidate speakers.
        assigned_ids: Speaker IDs already assigned to other characters.

    Returns:
        VoiceAssignment if successful, None if all attempts fail.
    """
    if assigned_ids is None:
        assigned_ids = set()

    available = [c for c in candidates if c.speaker_id not in assigned_ids]
    if not available:
        logger.warning("No available candidates for %s", character.name)
        return None

    valid_ids = {c.speaker_id for c in available}

    char_desc = _build_character_description(character)
    candidates_text = _build_candidates_text(candidates, assigned_ids)
    user_content = f"{char_desc}\n\nAvailable speakers:\n{candidates_text}"

    # Try up to 3 times (call_llm_structured has its own retries,
    # but we also check for valid speaker_id)
    for attempt in range(3):
        result = call_llm_structured(
            system_prompt=_CHARACTER_SYSTEM_PROMPT,
            user_content=user_content,
            schema_class=MatchResponse,
        )
        if result is None:
            continue
        if result.speaker_id in valid_ids:
            return VoiceAssignment(
                character_name=character.name,
                speaker_id=result.speaker_id,
                clip_path="",  # Set later by clip_selector
                reasoning=result.reasoning,
                confidence=result.confidence,
                is_major=True,  # Caller updates this
                method="llm",
                warning=None,
            )
        logger.warning(
            "Attempt %d: LLM returned invalid speaker_id %s for %s",
            attempt + 1,
            result.speaker_id,
            character.name,
        )

    logger.error("All attempts failed for character %s", character.name)
    return None


# ---------------------------------------------------------------------------
# Narrator matching
# ---------------------------------------------------------------------------


def match_narrator_llm(
    characters: list[CharacterProfile],
    segments: list[dict],
    candidates: list[SpeakerAnnotation],
    narrator_mode: str,
    assigned_ids: set[str] | None = None,
) -> VoiceAssignment | None:
    """Match a narrator voice using LLM trait comparison.

    For first_person mode, uses the protagonist's traits.
    For third_person mode, infers book tone from narration segments.

    Args:
        characters: All character profiles.
        segments: Attributed segments for tone analysis.
        candidates: Pre-filtered candidate speakers.
        narrator_mode: 'first_person' or 'third_person'.
        assigned_ids: Speaker IDs already assigned.

    Returns:
        VoiceAssignment for the narrator, or None if matching fails.
    """
    if assigned_ids is None:
        assigned_ids = set()

    available = [c for c in candidates if c.speaker_id not in assigned_ids]
    if not available:
        logger.warning("No available candidates for narrator")
        return None

    valid_ids = {c.speaker_id for c in available}
    candidates_text = _build_candidates_text(candidates, assigned_ids)

    if narrator_mode == "first_person":
        system_prompt = _NARRATOR_FIRST_PERSON_PROMPT
        protagonist = _find_protagonist(characters, segments)
        if protagonist:
            char_desc = _build_character_description(protagonist)
            user_content = (
                f"Protagonist (narrator):\n{char_desc}\n\n"
                f"Available speakers:\n{candidates_text}"
            )
        else:
            user_content = (
                f"First-person narrator (protagonist not identified)\n\n"
                f"Available speakers:\n{candidates_text}"
            )
    else:
        system_prompt = _NARRATOR_THIRD_PERSON_PROMPT
        tone_desc = _infer_book_tone(segments)
        user_content = (
            f"Book tone: {tone_desc}\n\n"
            f"Available speakers:\n{candidates_text}"
        )

    for attempt in range(3):
        result = call_llm_structured(
            system_prompt=system_prompt,
            user_content=user_content,
            schema_class=MatchResponse,
        )
        if result is None:
            continue
        if result.speaker_id in valid_ids:
            reasoning = result.reasoning
            if narrator_mode == "first_person":
                reasoning = f"First-person narrator = protagonist voice. {reasoning}"
            return VoiceAssignment(
                character_name="narrator",
                speaker_id=result.speaker_id,
                clip_path="",
                reasoning=reasoning,
                confidence=result.confidence,
                is_major=False,
                method="llm",
                warning=None,
            )
        logger.warning(
            "Attempt %d: LLM returned invalid speaker_id %s for narrator",
            attempt + 1,
            result.speaker_id,
        )

    logger.error("All attempts failed for narrator matching")
    return None


def _find_protagonist(
    characters: list[CharacterProfile], segments: list[dict]
) -> CharacterProfile | None:
    """Find the protagonist by dialogue line count."""
    dialogue_counts: Counter[str] = Counter()
    for seg in segments:
        if seg.get("type") == "dialogue":
            speaker = seg.get("speaker", "")
            if speaker and speaker != "narrator" and speaker != "unknown":
                dialogue_counts[speaker] += 1

    if not dialogue_counts:
        return None

    top_speaker = dialogue_counts.most_common(1)[0][0]
    for char in characters:
        if char.name == top_speaker:
            return char
    return None


def _infer_book_tone(segments: list[dict]) -> str:
    """Infer book tone from narration segments for narrator voice selection."""
    narration = [
        s.get("text", "")
        for s in segments
        if s.get("type") == "narration" and s.get("speaker") == "narrator"
    ]

    # Sample first 10 narration segments
    sample_text = " ".join(narration[:10])
    if not sample_text:
        return "neutral literary fiction"

    # Simple heuristic tone analysis
    lower = sample_text.lower()
    dark_words = ["dark", "shadow", "death", "blood", "fear", "horror", "grim"]
    light_words = ["laugh", "smile", "joy", "happy", "bright", "cheerful", "funny"]
    romantic_words = ["love", "heart", "passion", "desire", "embrace", "tender"]

    dark_score = sum(1 for w in dark_words if w in lower)
    light_score = sum(1 for w in light_words if w in lower)
    romantic_score = sum(1 for w in romantic_words if w in lower)

    if dark_score > light_score and dark_score > romantic_score:
        return "dark, tense fiction — needs a lower, measured narrator voice"
    elif light_score > dark_score and light_score > romantic_score:
        return "light, comedic fiction — needs a warm, expressive narrator voice"
    elif romantic_score > dark_score and romantic_score > light_score:
        return "romantic fiction — needs a warm, gentle narrator voice"
    else:
        return "literary fiction — needs a clear, measured, intellectual narrator voice"
