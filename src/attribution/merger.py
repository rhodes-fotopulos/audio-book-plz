"""Character profile merger — alias detection and deduplication.

Merges per-chapter character lists into a single deduplicated registry.
Uses a three-stage merge strategy:
  1. Exact name match
  2. Alias/substring match (with surname-only exclusion)
  3. Alias overlap detection

Requirements covered: ATTR-02
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.attribution.models import CharacterProfile, VoiceQualities

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name matching helpers
# ---------------------------------------------------------------------------

MIN_SUBSTRING_LENGTH = 3
"""Minimum length for a name to be considered in substring matching."""


def _names_match_substring(name_a: str, name_b: str) -> bool:
    """Check if one name is a substring of the other (case-insensitive).

    Requires the shorter name to be at least MIN_SUBSTRING_LENGTH characters
    to avoid matching trivial strings like "I" or "Mr".

    Args:
        name_a: First name to compare.
        name_b: Second name to compare.

    Returns:
        True if one name contains the other.
    """
    a_lower = name_a.lower().strip()
    b_lower = name_b.lower().strip()

    if a_lower == b_lower:
        return True

    shorter, longer = (a_lower, b_lower) if len(a_lower) <= len(b_lower) else (b_lower, a_lower)

    if len(shorter) < MIN_SUBSTRING_LENGTH:
        return False

    return shorter in longer


def _names_share_surname_only(name_a: str, name_b: str) -> bool:
    """Check if names share a surname but have different given names/titles.

    Used to PREVENT merging: "Mr. Bennet" and "Mrs. Bennet" share a surname
    but are different characters. "Mr. Darcy" and "Darcy" are the same person
    (one is just the surname, no conflicting given name).

    Args:
        name_a: First name to compare.
        name_b: Second name to compare.

    Returns:
        True if names share surname but have different given names/titles.
    """
    parts_a = name_a.strip().split()
    parts_b = name_b.strip().split()

    # Need at least 2 parts each to compare surname vs given name
    if len(parts_a) < 2 or len(parts_b) < 2:
        return False

    surname_a = parts_a[-1].lower()
    surname_b = parts_b[-1].lower()

    if surname_a != surname_b:
        return False

    # Same surname — check if given names/titles differ
    prefix_a = " ".join(parts_a[:-1]).lower()
    prefix_b = " ".join(parts_b[:-1]).lower()

    return prefix_a != prefix_b


def _alias_overlap(profile_a: CharacterProfile, profile_b: CharacterProfile) -> bool:
    """Check if any alias of A matches name or alias of B (or vice versa).

    Case-insensitive comparison.

    Args:
        profile_a: First character profile.
        profile_b: Second character profile.

    Returns:
        True if there is any alias overlap between the two profiles.
    """
    a_names = {profile_a.name.lower().strip()}
    a_names.update(alias.lower().strip() for alias in profile_a.aliases)

    b_names = {profile_b.name.lower().strip()}
    b_names.update(alias.lower().strip() for alias in profile_b.aliases)

    return bool(a_names & b_names)


# ---------------------------------------------------------------------------
# Profile merging
# ---------------------------------------------------------------------------


def _merge_two_profiles(
    primary: CharacterProfile, secondary: CharacterProfile
) -> CharacterProfile:
    """Merge two profiles determined to be the same character.

    The primary profile is preferred for most fields, but the longer/more
    formal name is chosen as canonical. All aliases and traits are unioned.

    Args:
        primary: The profile to prefer for name/description.
        secondary: The profile to merge into primary.

    Returns:
        A new merged CharacterProfile.
    """
    # Choose the longer/more formal name as canonical
    if len(secondary.name) > len(primary.name):
        canonical_name = secondary.name
        other_name = primary.name
    else:
        canonical_name = primary.name
        other_name = secondary.name

    # Combine aliases (union of both + the non-canonical name)
    all_aliases: set[str] = set()
    all_aliases.update(primary.aliases)
    all_aliases.update(secondary.aliases)
    all_aliases.add(other_name)
    # Remove canonical name from aliases
    all_aliases.discard(canonical_name)
    # Remove empty strings
    all_aliases.discard("")

    # Merge voice qualities: prefer non-"unknown" values
    merged_vq = _merge_voice_qualities(
        primary.voice_qualities, secondary.voice_qualities,
        primary.description, secondary.description,
    )

    # Union of personality traits (deduplicated)
    all_traits: list[str] = list(dict.fromkeys(
        primary.personality_traits + secondary.personality_traits
    ))

    # Prefer is_named=True if either has it
    is_named = primary.is_named or secondary.is_named

    # Take the longer description
    description = (
        primary.description if len(primary.description) >= len(secondary.description)
        else secondary.description
    )

    # Prefer non-"unknown" gender
    gender = primary.gender if primary.gender != "unknown" else secondary.gender

    # Prefer non-"unknown" age_range
    age_range = primary.age_range if primary.age_range != "unknown" else secondary.age_range

    return CharacterProfile(
        name=canonical_name,
        aliases=sorted(all_aliases),
        gender=gender,
        age_range=age_range,
        voice_qualities=merged_vq,
        personality_traits=all_traits,
        description=description,
        is_named=is_named,
    )


def _merge_voice_qualities(
    vq_a: VoiceQualities,
    vq_b: VoiceQualities,
    desc_a: str,
    desc_b: str,
) -> VoiceQualities:
    """Merge two VoiceQualities, preferring non-unknown values.

    When both have non-unknown values, prefer the one associated with
    the longer description (more textual evidence).

    Args:
        vq_a: Voice qualities from profile A.
        vq_b: Voice qualities from profile B.
        desc_a: Description from profile A (for evidence heuristic).
        desc_b: Description from profile B (for evidence heuristic).

    Returns:
        Merged VoiceQualities.
    """
    prefer_a = len(desc_a) >= len(desc_b)

    def pick(val_a: str, val_b: str) -> str:
        if val_a == "unknown" and val_b != "unknown":
            return val_b
        if val_b == "unknown" and val_a != "unknown":
            return val_a
        if val_a != "unknown" and val_b != "unknown":
            return val_a if prefer_a else val_b
        return "unknown"

    return VoiceQualities(
        pitch=pick(vq_a.pitch, vq_b.pitch),
        pace=pick(vq_a.pace, vq_b.pace),
        tone=pick(vq_a.tone, vq_b.tone),
        accent=pick(vq_a.accent, vq_b.accent),
    )


# ---------------------------------------------------------------------------
# Main merge pipeline
# ---------------------------------------------------------------------------


def merge_characters(
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path | None = None,
) -> list[CharacterProfile]:
    """Merge per-chapter character lists into a deduplicated registry.

    Three-stage merge:
    1. Exact name match (case-insensitive)
    2. Alias/substring match (with surname-only exclusion)
    3. Alias overlap detection

    Args:
        chapter_characters: Dict mapping chapter_num -> character list.
        cache_dir: Optional cache directory (reserved for future LLM
                   confirmation of ambiguous merges).

    Returns:
        Sorted list of deduplicated CharacterProfile objects.
    """
    # Collect all profiles into a flat list
    all_profiles: list[CharacterProfile] = []
    for chapter_num in sorted(chapter_characters.keys()):
        all_profiles.extend(chapter_characters[chapter_num])

    if not all_profiles:
        return []

    logger.info("Merging %d raw character entries", len(all_profiles))

    # Stage 1: Exact name match
    profiles = _merge_by_exact_name(all_profiles)
    logger.info("After exact-name merge: %d profiles", len(profiles))

    # Stage 2: Alias/substring match
    profiles = _merge_by_substring_and_alias(profiles)
    logger.info("After substring/alias merge: %d profiles", len(profiles))

    # Sort: named first, then alphabetically
    profiles.sort(key=lambda p: (not p.is_named, p.name.lower()))

    logger.info("Final registry: %d characters", len(profiles))
    return profiles


def _merge_by_exact_name(profiles: list[CharacterProfile]) -> list[CharacterProfile]:
    """Stage 1: Group and merge profiles with identical names (case-insensitive)."""
    groups: dict[str, list[CharacterProfile]] = {}
    for profile in profiles:
        key = profile.name.lower().strip()
        groups.setdefault(key, []).append(profile)

    merged: list[CharacterProfile] = []
    for group in groups.values():
        result = group[0]
        for other in group[1:]:
            result = _merge_two_profiles(result, other)
        merged.append(result)

    return merged


def _merge_by_substring_and_alias(
    profiles: list[CharacterProfile],
) -> list[CharacterProfile]:
    """Stage 2: Merge profiles by substring matching and alias overlap.

    Skips merges where names share only a surname (likely different characters).
    """
    merged_indices: set[int] = set()
    result: list[CharacterProfile] = []

    for i in range(len(profiles)):
        if i in merged_indices:
            continue

        current = profiles[i]

        for j in range(i + 1, len(profiles)):
            if j in merged_indices:
                continue

            candidate = profiles[j]

            # Check for surname-only match (PREVENT merge)
            if _names_share_surname_only(current.name, candidate.name):
                continue

            # Check substring match or alias overlap
            should_merge = (
                _names_match_substring(current.name, candidate.name)
                or _alias_overlap(current, candidate)
            )

            if should_merge:
                current = _merge_two_profiles(current, candidate)
                merged_indices.add(j)
                logger.debug(
                    "Merged '%s' into '%s'", candidate.name, current.name
                )

        result.append(current)

    return result
