"""Character name disambiguation pass (Stage 0.5).

Runs between extraction and merging to resolve ambiguous names before
Stage 1 exact-name merge auto-merges them. Handles two cases:

1. Same name, different characters (e.g. "Miss Bennet" → Jane vs Elizabeth)
2. Name changes missed (e.g. "Elizabeth Bennet" → "Mrs. Darcy")

The merger itself stays unchanged — disambiguation ensures names are clean
before merge runs.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import call_llm_structured, estimate_tokens
from src.attribution.models import (
    CharacterProfile,
    DisambiguatedIdentity,
    DisambiguationAudit,
    DisambiguationDecision,
    DisambiguationResult,
    NameChangeLink,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKENS_PER_CHAPTER = 500
"""Approximate token budget per chapter-appearance in LLM context."""

MAX_CONTEXT_TOKENS = 28000
"""Maximum tokens for disambiguation LLM context (leaves room for response)."""

JACCARD_THRESHOLD = 0.4
"""Minimum word-overlap Jaccard similarity to consider descriptions consistent."""

TITLES = {"mr", "mrs", "miss", "ms", "dr", "sir", "lady", "lord", "captain", "colonel"}
"""Common title prefixes for known-ambiguous pattern detection."""

# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------

DISAMBIGUATION_SYSTEM_PROMPT = """\
You are a literary character identity specialist. You are given a character \
name that appears across multiple chapters of a novel, along with the \
extracted profile and dialogue context for each appearance.

Answer two questions:
1. Does this name refer to multiple DISTINCT characters? If so, identify \
each distinct character, give them a resolved name (e.g. "Jane Bennet" \
instead of "Miss Bennet"), and list which chapters each identity appears in.
2. Did any character using this name change their name during the story? \
(e.g. marriage: "Elizabeth Bennet" → "Mrs. Darcy")

IMPORTANT: Be conservative. If you are unsure whether a name refers to \
multiple characters, assume it refers to ONE character. Only split when \
there is clear evidence (conflicting gender, age, description, or \
context that makes it obvious).

Return empty lists if the name consistently refers to one character \
with no name changes."""

NAME_CHANGE_SYSTEM_PROMPT = """\
You are a literary character identity specialist. You are given the complete \
list of unique character names from a novel, grouped by surname.

Identify any characters who changed their name during the story due to:
- Marriage (e.g. "Elizabeth Bennet" → "Mrs. Darcy")
- Title inheritance (e.g. "Mr. Collins" → "Reverend Collins")
- Revelation of true identity
- Any other name change

For each name change, specify the earlier name, the later name, and the \
approximate chapter where the transition occurs.

IMPORTANT: Only report genuine name changes where the SAME PERSON is \
referred to by different names. Do NOT link different family members \
who share a surname (e.g. "Mr. Bennet" and "Mrs. Bennet" are husband \
and wife, not a name change).

Return an empty list if no name changes are detected."""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _build_chapter_segments_map(
    segments: list[dict],
) -> dict[int, list[dict]]:
    """Group segments by chapter number.

    Args:
        segments: List of segment dicts with 'chapter' key.

    Returns:
        Dict mapping chapter number to list of segments.
    """
    chapter_map: dict[int, list[dict]] = defaultdict(list)
    for seg in segments:
        chapter_map[seg.get("chapter", 0)].append(seg)
    return dict(chapter_map)


def _extract_dialogue_snippets(
    name: str,
    chapter_segments: list[dict],
    max_snippets: int = 3,
) -> list[str]:
    """Find dialogue snippets near narration mentioning the character name.

    Searches for narration segments containing the name, then collects
    dialogue segments within a 3-segment window around each match.

    Args:
        name: Character name to search for.
        chapter_segments: Segments for one chapter.
        max_snippets: Maximum dialogue snippets to return.

    Returns:
        List of dialogue text strings.
    """
    name_lower = name.lower()
    snippets: list[str] = []

    for i, seg in enumerate(chapter_segments):
        if len(snippets) >= max_snippets:
            break

        # Look for narration mentioning the name
        if seg.get("type") != "narration":
            continue
        if name_lower not in seg.get("text", "").lower():
            continue

        # Search within a 3-segment window for dialogue
        window_start = max(0, i - 3)
        window_end = min(len(chapter_segments), i + 4)
        for j in range(window_start, window_end):
            if len(snippets) >= max_snippets:
                break
            if chapter_segments[j].get("type") == "dialogue":
                snippets.append(chapter_segments[j]["text"])

    return snippets


def _description_jaccard(desc_a: str, desc_b: str) -> float:
    """Compute word-overlap Jaccard similarity between two descriptions.

    Args:
        desc_a: First description string.
        desc_b: Second description string.

    Returns:
        Jaccard similarity coefficient (0.0-1.0).
    """
    words_a = set(re.findall(r"\w+", desc_a.lower()))
    words_b = set(re.findall(r"\w+", desc_b.lower()))

    if not words_a or not words_b:
        return 0.0

    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Step 1: Find ambiguous groups
# ---------------------------------------------------------------------------


def _find_ambiguous_groups(
    chapter_characters: dict[int, list[CharacterProfile]],
) -> dict[str, list[tuple[int, CharacterProfile]]]:
    """Find groups of profiles with the same name that may be ambiguous.

    A group is flagged as ambiguous when ANY of:
    - Gender conflict (one "female", another "male")
    - Age conflict (different non-"unknown" age ranges)
    - Description divergence (Jaccard similarity < threshold)
    - Known-ambiguous pattern: title+surname with other same-surname profiles

    Args:
        chapter_characters: Dict mapping chapter_num -> character list.

    Returns:
        Dict mapping lowercase name -> list of (chapter_num, profile) tuples,
        only for groups flagged as ambiguous.
    """
    # Group all profiles by name
    name_groups: dict[str, list[tuple[int, CharacterProfile]]] = defaultdict(list)
    for chapter_num, profiles in chapter_characters.items():
        for profile in profiles:
            name_groups[profile.name.lower()].append((chapter_num, profile))

    # Collect all surnames for known-ambiguous pattern detection
    all_names_lower = set(name_groups.keys())

    ambiguous: dict[str, list[tuple[int, CharacterProfile]]] = {}

    for name_key, entries in name_groups.items():
        # Skip single-profile groups — no ambiguity possible
        if len(entries) <= 1:
            continue

        profiles = [p for _, p in entries]

        # Check gender conflict
        genders = {p.gender for p in profiles if p.gender != "unknown"}
        if len(genders) > 1:
            ambiguous[name_key] = entries
            continue

        # Check age conflict
        ages = {p.age_range for p in profiles if p.age_range != "unknown"}
        if len(ages) > 1:
            ambiguous[name_key] = entries
            continue

        # Check description divergence
        descriptions = [p.description for p in profiles if p.description]
        if len(descriptions) >= 2:
            min_jaccard = min(
                _description_jaccard(descriptions[i], descriptions[j])
                for i in range(len(descriptions))
                for j in range(i + 1, len(descriptions))
            )
            if min_jaccard < JACCARD_THRESHOLD:
                ambiguous[name_key] = entries
                continue

        # Check known-ambiguous pattern: title+surname with other same-surname profiles
        parts = name_key.split()
        if len(parts) == 2:
            prefix = parts[0].rstrip(".")
            surname = parts[1]
            if prefix in TITLES:
                # Check if other profiles with the same surname exist
                for other_name in all_names_lower:
                    if other_name == name_key:
                        continue
                    other_parts = other_name.split()
                    if len(other_parts) >= 2 and other_parts[-1] == surname:
                        other_prefix = other_parts[0].rstrip(".")
                        if other_prefix != prefix:
                            ambiguous[name_key] = entries
                            break

    return ambiguous


# ---------------------------------------------------------------------------
# Step 2: Build LLM context per group
# ---------------------------------------------------------------------------


def _build_disambiguation_context(
    name_key: str,
    entries: list[tuple[int, CharacterProfile]],
    chapter_segments_map: dict[int, list[dict]],
) -> str:
    """Build LLM context for disambiguating one name group.

    Includes profile attributes and dialogue snippets per chapter,
    staying within the token budget.

    Args:
        name_key: The ambiguous name (lowercase).
        entries: List of (chapter_num, profile) for this name.
        chapter_segments_map: Segments grouped by chapter.

    Returns:
        Formatted context string for the LLM.
    """
    lines: list[str] = []
    lines.append(f'Ambiguous name: "{entries[0][1].name}"')
    lines.append(f"Appears in {len(entries)} chapter(s):\n")

    token_budget = MAX_CONTEXT_TOKENS
    tokens_used = estimate_tokens("\n".join(lines))

    for chapter_num, profile in entries:
        chapter_block: list[str] = []
        chapter_block.append(f"--- Chapter {chapter_num} ---")
        chapter_block.append(f"  Gender: {profile.gender}")
        chapter_block.append(f"  Age: {profile.age_range}")
        chapter_block.append(f"  Description: {profile.description}")
        if profile.personality_traits:
            chapter_block.append(
                f"  Traits: {', '.join(profile.personality_traits[:5])}"
            )
        if profile.aliases:
            chapter_block.append(f"  Aliases: {', '.join(profile.aliases)}")

        # Add dialogue snippets
        chapter_segs = chapter_segments_map.get(chapter_num, [])
        snippets = _extract_dialogue_snippets(
            profile.name, chapter_segs, max_snippets=3
        )
        if snippets:
            chapter_block.append("  Dialogue snippets:")
            for s in snippets:
                chapter_block.append(f'    - "{s[:200]}"')

        block_text = "\n".join(chapter_block)
        block_tokens = estimate_tokens(block_text)

        if tokens_used + block_tokens > token_budget:
            lines.append(
                f"\n[Truncated: {len(entries) - len(lines) + 2} more chapter(s) omitted]"
            )
            break

        tokens_used += block_tokens
        lines.append(block_text)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3 & 4: LLM disambiguation + apply results
# ---------------------------------------------------------------------------


def _apply_disambiguations(
    chapter_characters: dict[int, list[CharacterProfile]],
    result: DisambiguationResult,
    audit: DisambiguationAudit,
) -> None:
    """Apply split decisions from a disambiguation result.

    For each identity in the result, renames the profile in the
    specified chapters and adds the original name as an alias.

    Modifies chapter_characters in place.
    """
    for identity in result.identities:
        # Only apply if the resolved name differs from the original
        if identity.resolved_name.lower() == identity.original_name.lower():
            continue

        audit.splits_applied += 1
        audit.decisions.append(DisambiguationDecision(
            original_name=identity.original_name,
            action="split",
            details=(
                f"Resolved to '{identity.resolved_name}' in chapters "
                f"{identity.chapter_numbers}: {identity.reasoning}"
            ),
            confidence=0.8,
        ))

        for chapter_num in identity.chapter_numbers:
            profiles = chapter_characters.get(chapter_num, [])
            for profile in profiles:
                if profile.name.lower() == identity.original_name.lower():
                    old_name = profile.name
                    profile.name = identity.resolved_name
                    if old_name not in profile.aliases:
                        profile.aliases.append(old_name)
                    break


def _apply_name_changes(
    chapter_characters: dict[int, list[CharacterProfile]],
    name_changes: list[NameChangeLink],
    audit: DisambiguationAudit,
) -> None:
    """Apply name-change links by adding aliases.

    For each name change, finds profiles with the later name and adds
    the earlier name as an alias (so the merger can connect them).

    Modifies chapter_characters in place.
    """
    for link in name_changes:
        audit.name_changes_found += 1
        audit.decisions.append(DisambiguationDecision(
            original_name=link.earlier_name,
            action="name_change",
            details=(
                f"'{link.earlier_name}' → '{link.later_name}' "
                f"around chapter {link.transition_chapter}: {link.reasoning}"
            ),
            confidence=0.7,
        ))

        # Add earlier_name as alias on later_name profiles
        for profiles in chapter_characters.values():
            for profile in profiles:
                if profile.name.lower() == link.later_name.lower():
                    if link.earlier_name not in profile.aliases:
                        profile.aliases.append(link.earlier_name)
                # Also add later_name as alias on earlier_name profiles
                elif profile.name.lower() == link.earlier_name.lower():
                    if link.later_name not in profile.aliases:
                        profile.aliases.append(link.later_name)


# ---------------------------------------------------------------------------
# Step 5: Book-wide name-change detection
# ---------------------------------------------------------------------------


class NameChangeDetectionResult(DisambiguationResult):
    """Reuses DisambiguationResult schema for name-change detection."""
    pass


def _detect_name_changes(
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path,
    audit: DisambiguationAudit,
) -> None:
    """Detect book-wide name changes by presenting all names grouped by surname.

    One LLM call that reviews the full name list and spots connections
    like "Elizabeth Bennet" → "Mrs. Darcy".

    Modifies chapter_characters in place.
    """
    # Collect unique names grouped by surname
    all_names: set[str] = set()
    for profiles in chapter_characters.values():
        for profile in profiles:
            all_names.add(profile.name)

    if len(all_names) < 2:
        return

    # Group by surname (last word)
    surname_groups: dict[str, list[str]] = defaultdict(list)
    ungrouped: list[str] = []
    for name in sorted(all_names):
        parts = name.split()
        if len(parts) >= 2:
            surname = parts[-1].lower()
            surname_groups[surname].append(name)
        else:
            ungrouped.append(name)

    # Build context
    lines: list[str] = []
    lines.append("Character names from this novel:\n")
    for surname, names in sorted(surname_groups.items()):
        if len(names) > 1:
            lines.append(f"  {surname.title()} family: {', '.join(sorted(names))}")
        else:
            lines.append(f"  {names[0]}")
    if ungrouped:
        lines.append(f"  Other: {', '.join(sorted(ungrouped))}")

    user_content = "\n".join(lines)

    # Cache check
    cache_key = get_cache_key(user_content, "name_change_detection_v1")
    cached = check_cache(cache_dir, cache_key)

    if cached is not None:
        logger.info("Name-change detection: cache hit")
        result = DisambiguationResult.model_validate(cached)
    else:
        logger.info("Name-change detection: calling LLM")
        result = call_llm_structured(
            NAME_CHANGE_SYSTEM_PROMPT,
            user_content,
            DisambiguationResult,
        )
        if result is None:
            logger.warning("Name-change detection: LLM call failed")
            audit.warnings.append("Name-change detection LLM call failed")
            return
        write_cache(cache_dir, cache_key, result.model_dump())

    # Apply name-change links
    _apply_name_changes(chapter_characters, result.name_changes, audit)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def disambiguate_characters(
    chapter_characters: dict[int, list[CharacterProfile]],
    segments: list[dict],
    cache_dir: Path,
) -> tuple[dict[int, list[CharacterProfile]], DisambiguationAudit]:
    """Run the disambiguation pass on extracted character profiles.

    Finds ambiguous name groups, asks the LLM to resolve them, then
    applies splits and name-change links before the merger runs.

    Args:
        chapter_characters: Dict mapping chapter_num -> character list.
        segments: Full segment list (for dialogue snippet extraction).
        cache_dir: Cache directory for LLM result caching.

    Returns:
        Tuple of (modified chapter_characters, DisambiguationAudit).
    """
    audit = DisambiguationAudit(
        total_names_analyzed=0,
        ambiguous_groups_found=0,
        splits_applied=0,
        name_changes_found=0,
    )

    # Count unique names
    all_names: set[str] = set()
    for profiles in chapter_characters.values():
        for profile in profiles:
            all_names.add(profile.name.lower())
    audit.total_names_analyzed = len(all_names)

    if not all_names:
        return chapter_characters, audit

    # Step 1: Find ambiguous groups
    ambiguous_groups = _find_ambiguous_groups(chapter_characters)
    audit.ambiguous_groups_found = len(ambiguous_groups)

    if not ambiguous_groups:
        logger.info("Disambiguation: no ambiguous groups found")
    else:
        logger.info(
            "Disambiguation: %d ambiguous group(s) found", len(ambiguous_groups)
        )

    # Build chapter segments map for dialogue snippets
    chapter_segments_map = _build_chapter_segments_map(segments)

    # Steps 2-4: Process each ambiguous group
    for name_key, entries in ambiguous_groups.items():
        # Build LLM context
        user_content = _build_disambiguation_context(
            name_key, entries, chapter_segments_map
        )

        # Cache check
        cache_key = get_cache_key(user_content, "disambiguation_v1")
        cached = check_cache(cache_dir, cache_key)

        if cached is not None:
            logger.info("Disambiguation cache hit for '%s'", name_key)
            result = DisambiguationResult.model_validate(cached)
        else:
            logger.info("Disambiguation: calling LLM for '%s'", name_key)
            result = call_llm_structured(
                DISAMBIGUATION_SYSTEM_PROMPT,
                user_content,
                DisambiguationResult,
            )
            if result is None:
                logger.warning(
                    "Disambiguation LLM call failed for '%s'", name_key
                )
                audit.warnings.append(
                    f"LLM call failed for ambiguous name '{name_key}'"
                )
                audit.decisions.append(DisambiguationDecision(
                    original_name=name_key,
                    action="no_change",
                    details="LLM call failed, keeping original names",
                    confidence=0.0,
                ))
                continue
            write_cache(cache_dir, cache_key, result.model_dump())

        # Apply splits
        if result.identities:
            _apply_disambiguations(chapter_characters, result, audit)
        else:
            audit.decisions.append(DisambiguationDecision(
                original_name=name_key,
                action="no_change",
                details="LLM determined name refers to one character",
                confidence=0.9,
            ))

        # Apply per-group name changes
        if result.name_changes:
            _apply_name_changes(chapter_characters, result.name_changes, audit)

    # Step 5: Book-wide name-change detection
    _detect_name_changes(chapter_characters, cache_dir, audit)

    logger.info(
        "Disambiguation complete: %d splits, %d name changes",
        audit.splits_applied,
        audit.name_changes_found,
    )
    return chapter_characters, audit
