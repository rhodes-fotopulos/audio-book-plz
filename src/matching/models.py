"""Pydantic data models for Phase 3 voice-character matching.

Defines schemas for:
- LibriTTS-P speaker annotations (SpeakerAnnotation)
- Character-to-speaker mappings (VoiceAssignment)
- Complete voice map output (VoiceMap)
- Cast classification results (CastClassification)

Value objects use ConfigDict(strict=True) consistent with Phase 2
conventions. Container models (VoiceMap) do not use strict mode.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# LibriTTS-P speaker representation
# ---------------------------------------------------------------------------


class SpeakerAnnotation(BaseModel):
    """A LibriTTS-P speaker with merged annotations from all annotators.

    Annotations are perception/impression words collected from 3 professional
    annotators. Traits are merged across annotators and gender is inferred
    from trait keywords.
    """

    model_config = ConfigDict(strict=True)

    speaker_id: str
    """Numeric speaker ID as string (e.g., '7335')."""

    traits: list[str]
    """Merged perception/impression words from all annotators."""

    trait_text: str
    """Comma-joined sorted traits for display and embedding."""

    gender: str
    """Inferred gender: 'male', 'female', or 'unknown'."""

    annotator_agreement: dict[str, int]
    """How many annotators (1-3) agree on each trait word."""


# ---------------------------------------------------------------------------
# Voice assignment (single character mapping)
# ---------------------------------------------------------------------------


class VoiceAssignment(BaseModel):
    """A single character-to-speaker voice mapping.

    Represents one row in the voice map: which LibriTTS-P speaker is
    assigned to which character, with reasoning and confidence.
    """

    model_config = ConfigDict(strict=True)

    character_name: str
    """Canonical character name from CharacterProfile."""

    speaker_id: str
    """LibriTTS-P speaker ID."""

    clip_path: str
    """Relative path to reference WAV within LibriTTS-R directory."""

    reasoning: str
    """Brief explanation of why matched (casting-director style)."""

    confidence: float
    """Confidence score 0.0-1.0."""

    is_major: bool
    """Whether this is a major character (by dialogue line count)."""

    method: str
    """Matching method used: 'llm' or 'embedding'."""

    warning: str | None = None
    """Warning flag for weak matches, or None if match is solid."""


# ---------------------------------------------------------------------------
# Complete voice map (output file schema)
# ---------------------------------------------------------------------------


class VoiceMap(BaseModel):
    """Complete voice map for a book — the voice_map.json schema.

    Contains narrator assignment plus all character assignments.
    Written to book_dir/voice_map.json after user confirmation.
    """

    book_slug: str
    """Identifies the book (derived from EPUB filename)."""

    narrator: VoiceAssignment
    """Narrator voice assignment."""

    characters: list[VoiceAssignment]
    """All character voice assignments (major and minor)."""

    metadata: dict
    """Metadata: created_at, libritts_subset, total_speakers_evaluated."""


# ---------------------------------------------------------------------------
# Cast classification
# ---------------------------------------------------------------------------


class CastClassification(BaseModel):
    """Result of classifying characters as major or minor.

    Major characters get LLM-based matching with uniqueness enforcement.
    Minor characters use embedding similarity and can share voices
    (but not if they appear in the same chapter).
    """

    model_config = ConfigDict(strict=True)

    major: list[str]
    """Character names classified as major (>= threshold dialogue lines)."""

    minor: list[str]
    """Character names classified as minor (< threshold dialogue lines)."""

    threshold: int
    """Dialogue count threshold used for classification."""

    narrator_mode: str
    """'first_person' or 'third_person' — affects narrator voice selection."""
