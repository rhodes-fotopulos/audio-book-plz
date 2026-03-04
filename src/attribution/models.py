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


class VoiceQualities(BaseModel):
    """Vocal characteristics for a character, used by Phase 3 voice matching.

    Values are inferred from text descriptions and dialogue style.
    Use "unknown" when the text provides no evidence for a trait.
    """

    model_config = ConfigDict(strict=True)

    pitch: str
    """Vocal pitch: "high", "medium", "low", or "unknown"."""

    pace: str
    """Speech pace: "fast", "moderate", "slow", or "unknown"."""

    tone: str
    """Vocal tone: e.g. "warm", "gruff", "silky", "monotone", "unknown"."""

    accent: str
    """Accent if mentioned: e.g. "British", "Southern American", "unknown"."""


class Relationship(BaseModel):
    """A relationship between two characters.

    Used to help disambiguate dialogue in group scenes and to enrich
    character profiles for downstream voice matching.
    """

    model_config = ConfigDict(strict=True)

    character: str
    """Name of the related character."""

    relation: str
    """Nature of the relationship: e.g. "mother", "rival", "employer"."""


# ---------------------------------------------------------------------------
# Character profile (registry entry + extraction result)
# ---------------------------------------------------------------------------


class CharacterProfile(BaseModel):
    """A character extracted from novel text.

    Used both as individual extraction results (per-chapter) and as entries
    in the merged character registry (characters.json). Rich profile per
    user decision: gender, age, voice qualities, personality, relationships.
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

    voice_qualities: VoiceQualities
    """Inferred vocal characteristics for voice matching."""

    personality_traits: list[str] = []
    """Key personality characteristics shown in the text."""

    relationships: list[Relationship] = []
    """Known relationships to other characters."""

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
