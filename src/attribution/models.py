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


# ---------------------------------------------------------------------------
# LLM response schemas — distinctiveness pass
# ---------------------------------------------------------------------------


class DistinctivenessResult(BaseModel):
    """LLM response schema for the distinctiveness pass.

    The LLM reviews all character voice profiles together and returns
    modified profiles with audible separation between similar characters.
    """

    characters: list[CharacterProfile]
    """All character profiles (modified and unmodified)."""

    modifications: list[str]
    """Human-readable list of what was changed and why."""


# ---------------------------------------------------------------------------
# Merge audit models (Phase 14 — merger hardening)
# ---------------------------------------------------------------------------


class MergeDecision(BaseModel):
    """Record of a single merge/reject/flag decision during character merging.

    Each stage of the merge pipeline (exact-name, fuzzy, alias, LLM)
    records its decisions for audit trail and debugging.
    """

    stage: str
    """Which merge stage produced this decision (e.g. 'exact_name', 'fuzzy', 'llm')."""

    profile_a: str
    """Canonical name of the first profile."""

    profile_b: str
    """Canonical name of the second profile."""

    action: str
    """Decision taken: 'merged', 'rejected', or 'flagged'."""

    reason: str
    """Human-readable explanation of why this action was taken."""

    confidence: float
    """Confidence score 0.0-1.0 for this decision."""

    details: dict = {}
    """Optional extra data (e.g. similarity score, co-occurrence chapters)."""


class MergeAudit(BaseModel):
    """Complete audit trail for a merge_characters run.

    Written to merge_audit.json alongside characters.json so that
    merge decisions can be reviewed and debugged.
    """

    book_title: str
    """Title of the book being processed."""

    timestamp: str
    """ISO-8601 timestamp of when the merge was performed."""

    total_raw_profiles: int
    """Number of raw character entries before merging."""

    total_merged_profiles: int
    """Number of profiles after merging."""

    stages: dict[str, list[MergeDecision]] = {}
    """Decisions grouped by stage name."""

    warnings: list[str] = []
    """Post-merge validation warnings (e.g. excessive aliases, trait overflow)."""

    final_profiles: list[str] = []
    """Canonical names of all profiles in the final registry."""


# ---------------------------------------------------------------------------
# Disambiguation models (Stage 0.5 — pre-merge name disambiguation)
# ---------------------------------------------------------------------------


class DisambiguatedIdentity(BaseModel):
    """A resolved identity for an ambiguous name in specific chapters."""

    resolved_name: str
    """Disambiguated name (e.g. "Jane Bennet")."""

    original_name: str
    """The ambiguous name (e.g. "Miss Bennet")."""

    chapter_numbers: list[int]
    """Chapters where this name refers to this identity."""

    reasoning: str
    """Explanation of why this identity was assigned."""


class NameChangeLink(BaseModel):
    """A detected name change for a character (e.g. marriage)."""

    earlier_name: str
    """Name used before the change (e.g. "Elizabeth Bennet")."""

    later_name: str
    """Name used after the change (e.g. "Mrs. Darcy")."""

    transition_chapter: int
    """Approximate chapter where the name change occurs."""

    reasoning: str
    """Explanation of the name change."""


class DisambiguationResult(BaseModel):
    """LLM response schema for per-group name disambiguation."""

    identities: list[DisambiguatedIdentity]
    """Resolved identities for the ambiguous name."""

    name_changes: list[NameChangeLink]
    """Any name changes detected for characters in this group."""


class DisambiguationDecision(BaseModel):
    """Record of a single disambiguation decision."""

    original_name: str
    """The name that was analyzed."""

    action: str
    """Decision taken: "split", "name_change", or "no_change"."""

    details: str
    """Human-readable explanation."""

    confidence: float
    """Confidence score 0.0-1.0."""


class DisambiguationAudit(BaseModel):
    """Complete audit trail for a disambiguation pass."""

    total_names_analyzed: int
    """Number of unique names examined."""

    ambiguous_groups_found: int
    """Number of groups flagged as potentially ambiguous."""

    splits_applied: int
    """Number of name splits applied."""

    name_changes_found: int
    """Number of name-change links detected."""

    decisions: list[DisambiguationDecision] = []
    """All decisions made during disambiguation."""

    warnings: list[str] = []
    """Any warnings generated during the pass."""
