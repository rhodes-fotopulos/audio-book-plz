"""Pydantic data models for Phase 2 attribution.

Defines schemas for:
- LLM structured output (character extraction and speaker attribution)
- Character registry entries
- Final attributed segment output

All LLM-facing models produce JSON schemas via model_json_schema()
for use with Ollama's format parameter.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Nested value objects
# ---------------------------------------------------------------------------


class VoiceProfile(BaseModel):
    """Unified voice description for a character.

    Combines coarse traits (aligned with LibriTTS-P annotation vocabulary
    for embedding matching) with rich descriptors (for LLM casting and
    emotion baseline). All fields default to "unknown" when text provides
    no evidence.
    """

    model_config = ConfigDict(strict=True)

    # Coarse traits (LibriTTS-P aligned)
    pitch: str
    """Vocal pitch: "high", "medium", "low", or "unknown"."""

    pace: str
    """Speech pace: "fast", "moderate", "slow", or "unknown"."""

    tone: str
    """Vocal tone: e.g. "warm", "gruff", "silky", "monotone", "unknown"."""

    accent: str
    """Accent if mentioned: e.g. "British", "Southern American", "unknown"."""

    # Rich descriptors (LLM casting + emotion baseline)
    pace_style: str
    """Nuanced speaking pace: e.g. "measured", "rapid", "languid", "clipped", "unknown"."""

    tone_style: str
    """Nuanced vocal quality: e.g. "gravelly", "melodic", "breathy", "flat", "unknown"."""

    energy: str
    """Energy level: e.g. "restrained", "animated", "intense", "subdued", "unknown"."""

    typical_emotion: str
    """Default emotional register: e.g. "sardonic", "cheerful", "weary", "unknown"."""

    description: str
    """One-sentence voice summary: e.g. "A slow, gravelly voice with weary patience"."""


# ---------------------------------------------------------------------------
# Character profile (registry entry + extraction result)
# ---------------------------------------------------------------------------


class CharacterProfile(BaseModel):
    """A character extracted from novel text.

    Used both as individual extraction results (per-chapter) and as entries
    in the merged character registry (characters.json). Rich profile per
    user decision: gender, age, voice profile, personality.
    """

    model_config = ConfigDict(strict=True)

    name: str
    """Canonical character name (most formal/complete form)."""

    aliases: list[str] = []
    """All known aliases, nicknames, and alternate references."""

    gender: str
    """Gender: "male", "female", "non-binary", or "unknown"."""

    age_range: str
    """Age range: "child", "young adult", "middle-aged", "elderly", or "unknown"."""

    voice_profile: VoiceProfile
    """Unified voice description for voice matching and emotion baseline."""

    personality_traits: list[str] = []
    """Key personality characteristics shown in the text."""

    description: str
    """One-sentence character summary."""

    is_named: bool
    """True for named characters ("Mr. Darcy"), False for unnamed ("the bartender")."""


# ---------------------------------------------------------------------------
# LLM response schemas — character extraction
# ---------------------------------------------------------------------------


class ChapterExtractionResult(BaseModel):
    """LLM response schema for character extraction from a chapter.

    Passed to Ollama's format parameter via model_json_schema().
    The LLM returns a list of all characters found in the chapter text.
    """

    characters: list[CharacterProfile]


# ---------------------------------------------------------------------------
# LLM response schemas — speaker attribution
# ---------------------------------------------------------------------------


class SegmentAttribution(BaseModel):
    """Attribution result for a single text segment.

    Part of ChapterAttributionResult returned by the LLM.
    Maps a segment ID to its identified speaker with confidence.
    """

    model_config = ConfigDict(strict=True)

    segment_id: int
    """ID of the segment being attributed (matches Segment.id from Phase 1)."""

    speaker: str
    """Speaker name from character registry, "narrator", or "unknown"."""

    confidence: float
    """Confidence score 0.0-1.0 for this attribution."""

    reasoning: str
    """Brief explanation of why this speaker was chosen (for debugging)."""

    speech_act: str = "spoken"
    """Speech-act subtype: 'spoken', 'thought', 'shouted', 'whispered'."""


class ChapterAttributionResult(BaseModel):
    """LLM response schema for speaker attribution of a chapter's segments.

    Passed to Ollama's format parameter via model_json_schema().
    The LLM returns attributions for all dialogue segments in the chapter.
    """

    attributions: list[SegmentAttribution]


# ---------------------------------------------------------------------------
# Output model — attributed segment
# ---------------------------------------------------------------------------


class AttributedSegment(BaseModel):
    """A text segment with speaker attribution.

    Extends the Phase 1 Segment fields with speaker and confidence.
    Written to attributed.json as the final Phase 2 output.
    """

    id: int
    """Sequential global ID across the entire book."""

    chapter: int
    """1-based chapter number."""

    chapter_title: str
    """Extracted chapter heading, or empty string if untitled."""

    type: str
    """SegmentType value: "narration", "dialogue", "chapter_heading", "scene_break"."""

    text: str
    """Clean, speech-ready text."""

    char_count: int
    """Length of text in characters."""

    speaker: str
    """Attributed speaker: character name, "narrator", or "unknown"."""

    confidence: float
    """Confidence score 0.0-1.0 for this attribution."""

    speech_act: str = "spoken"
    """Speech-act subtype: 'spoken', 'thought', 'shouted', 'whispered'."""


# ---------------------------------------------------------------------------
# LLM response schemas — speech-act classification
# ---------------------------------------------------------------------------


class DuplicateGroup(BaseModel):
    """A group of character indices identified as the same person by LLM consolidation."""

    indices: list[int]
    """Indices of profiles that are the same character."""

    canonical_index: int
    """Index of the profile to use as the canonical/primary entry."""

    reasoning: str
    """Explanation of why these profiles are the same character."""


class ConsolidationResult(BaseModel):
    """LLM response schema for character consolidation/deduplication."""

    groups: list[DuplicateGroup]
    """Groups of duplicate characters. Empty list if no duplicates found."""


class SpeechActTag(BaseModel):
    """Classification result for a single segment's speech-act.

    Part of SpeechActResult returned by the LLM during hybrid
    speech-act classification.
    """

    model_config = ConfigDict(strict=True)

    segment_id: int
    """ID of the segment being classified."""

    speech_act: str
    """Speech-act subtype: 'spoken', 'thought', 'shouted', 'whispered'."""

    confidence: float
    """Confidence score 0.0-1.0 for this classification."""

    reasoning: str
    """Brief explanation of why this speech-act was chosen."""


class SpeechActResult(BaseModel):
    """LLM response schema for speech-act classification of segments.

    Passed to Ollama's format parameter via model_json_schema().
    The LLM returns speech-act tags for dialogue segments.
    """

    tags: list[SpeechActTag]
