"""Character profile merger — alias detection and deduplication.

Merges per-chapter character lists into a single deduplicated registry.
Uses a multi-stage merge strategy:
  1. Exact name match
  2. Fuzzy name match (SequenceMatcher + title/name matching)
  3. Alias/substring match (with surname-only exclusion)
  4. LLM consolidation with co-occurrence guard

Requirements covered: ATTR-02
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from pathlib import Path

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import call_llm_structured
from src.attribution.models import CharacterProfile, ConsolidationResult, VoiceProfile

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
# Fuzzy matching helpers
# ---------------------------------------------------------------------------

TITLES = {"mr", "mrs", "miss", "ms", "dr", "sir", "lady", "lord", "captain", "colonel"}
"""Common title prefixes for title/name matching."""


def _names_match_fuzzy(name_a: str, name_b: str, threshold: float = 0.85) -> bool:
    """Check if two names are fuzzy matches using SequenceMatcher.

    Uses a higher threshold for short names to avoid false positives.

    Args:
        name_a: First name.
        name_b: Second name.
        threshold: Minimum similarity ratio (default 0.85).

    Returns:
        True if names are sufficiently similar.
    """
    a = name_a.lower().strip()
    b = name_b.lower().strip()

    if len(a) < MIN_SUBSTRING_LENGTH or len(b) < MIN_SUBSTRING_LENGTH:
        return False

    # Use higher threshold for short names
    effective_threshold = 0.90 if min(len(a), len(b)) < 6 else threshold

    return SequenceMatcher(None, a, b).ratio() >= effective_threshold


def _title_name_match(name_a: str, name_b: str) -> bool:
    """Check if names differ only by title vs first name (same person).

    Merges "Miss Darcy" with "Georgiana Darcy" but prevents
    "Mr. Bennet" / "Mrs. Bennet" merge.

    Args:
        name_a: First name.
        name_b: Second name.

    Returns:
        True if names match via title/first-name equivalence.
    """
    parts_a = name_a.strip().split()
    parts_b = name_b.strip().split()

    if len(parts_a) < 2 or len(parts_b) < 2:
        return False

    surname_a = parts_a[-1].lower().rstrip(".")
    surname_b = parts_b[-1].lower().rstrip(".")

    if surname_a != surname_b:
        return False

    prefix_a = parts_a[0].lower().rstrip(".")
    prefix_b = parts_b[0].lower().rstrip(".")

    a_is_title = prefix_a in TITLES
    b_is_title = prefix_b in TITLES

    # If both are titles and they differ, block (Mr. Bennet vs Mrs. Bennet)
    if a_is_title and b_is_title and prefix_a != prefix_b:
        return False

    # If one is a title and the other is a first name, allow merge
    if a_is_title != b_is_title:
        return True

    return False


def _merge_by_fuzzy(profiles: list[CharacterProfile]) -> list[CharacterProfile]:
    """Merge profiles by fuzzy name matching and title/name equivalence.

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

            # Check fuzzy match on canonical names
            should_merge = _names_match_fuzzy(current.name, candidate.name)

            # Check fuzzy match on aliases
            if not should_merge:
                all_a = [current.name] + list(current.aliases)
                all_b = [candidate.name] + list(candidate.aliases)
                for na in all_a:
                    for nb in all_b:
                        if _names_match_fuzzy(na, nb) or _title_name_match(na, nb):
                            should_merge = True
                            break
                    if should_merge:
                        break

            # Check title/name match on canonical names
            if not should_merge:
                should_merge = _title_name_match(current.name, candidate.name)

            if should_merge:
                current = _merge_two_profiles(current, candidate)
                merged_indices.add(j)
                logger.debug(
                    "Fuzzy-merged '%s' into '%s'", candidate.name, current.name
                )

        result.append(current)

    return result


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

    # Merge voice profiles: prefer non-"unknown" values
    merged_vp = _merge_voice_profiles(primary.voice_profile, secondary.voice_profile)

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
        voice_profile=merged_vp,
        personality_traits=all_traits,
        description=description,
        is_named=is_named,
    )


def _merge_voice_profiles(
    vp_a: VoiceProfile,
    vp_b: VoiceProfile,
) -> VoiceProfile:
    """Merge two VoiceProfiles, preferring non-unknown values.

    When both have non-unknown values, prefer the profile with the
    longer description (more textual evidence).

    Args:
        vp_a: Voice profile from profile A.
        vp_b: Voice profile from profile B.

    Returns:
        Merged VoiceProfile.
    """
    prefer_a = len(vp_a.description) >= len(vp_b.description)

    def pick(val_a: str, val_b: str) -> str:
        if val_a == "unknown" and val_b != "unknown":
            return val_b
        if val_b == "unknown" and val_a != "unknown":
            return val_a
        if val_a != "unknown" and val_b != "unknown":
            return val_a if prefer_a else val_b
        return "unknown"

    # Description: take the longer one directly
    desc = vp_a.description if len(vp_a.description) >= len(vp_b.description) else vp_b.description

    return VoiceProfile(
        pitch=pick(vp_a.pitch, vp_b.pitch),
        pace=pick(vp_a.pace, vp_b.pace),
        tone=pick(vp_a.tone, vp_b.tone),
        accent=pick(vp_a.accent, vp_b.accent),
        pace_style=pick(vp_a.pace_style, vp_b.pace_style),
        tone_style=pick(vp_a.tone_style, vp_b.tone_style),
        energy=pick(vp_a.energy, vp_b.energy),
        typical_emotion=pick(vp_a.typical_emotion, vp_b.typical_emotion),
        description=desc,
    )


# ---------------------------------------------------------------------------
# LLM consolidation
# ---------------------------------------------------------------------------

CONSOLIDATION_SYSTEM_PROMPT = """\
You are a character deduplication specialist. Given a numbered list of \
character profiles extracted from a novel, identify ONLY characters you \
are CERTAIN are the same person.

Rules:
- If unsure, do NOT group — it is better to keep duplicates than to \
wrongly merge distinct characters.
- Characters who share a surname are often DIFFERENT people \
(e.g. the Bennet sisters are 5 distinct characters: Jane, Elizabeth, \
Mary, Kitty/Catherine, and Lydia).
- "Mr. Bennet" and "Mrs. Bennet" are DIFFERENT characters (husband and wife).
- Spelling variants of the same name ARE duplicates \
(e.g. "Mrs. Phillips" and "Mrs. Philips").
- A descriptor like "the middle Bennet daughter" that refers to a named \
character IS a duplicate of that named character.
- Return an empty groups list if no clear duplicates exist.
- For each group, set canonical_index to the profile with the most \
complete information."""


def _build_cooccurrence(
    chapter_characters: dict[int, list[CharacterProfile]],
) -> tuple[dict[str, set[int]], dict[str, bool]]:
    """Build co-occurrence map: character name -> set of chapter numbers.

    Also tracks is_named status per character name.

    Returns:
        Tuple of (name_to_chapters, name_is_named).
    """
    name_to_chapters: dict[str, set[int]] = {}
    name_is_named: dict[str, bool] = {}

    for chapter_num, profiles in chapter_characters.items():
        for profile in profiles:
            key = profile.name.lower().strip()
            name_to_chapters.setdefault(key, set()).add(chapter_num)
            name_is_named[key] = profile.is_named

            for alias in profile.aliases:
                alias_key = alias.lower().strip()
                if alias_key:
                    name_to_chapters.setdefault(alias_key, set()).add(chapter_num)
                    # Alias inherits the profile's is_named status
                    name_is_named.setdefault(alias_key, profile.is_named)

    return name_to_chapters, name_is_named


def _named_pair_cooccurs(
    profile_a: CharacterProfile,
    profile_b: CharacterProfile,
    name_to_chapters: dict[str, set[int]],
) -> bool:
    """Check if two named profiles co-occur in any chapter.

    Only blocks when BOTH profiles have is_named=True. If either is
    unnamed (a descriptor), co-occurrence does NOT block — this is
    exactly the case where the extraction LLM failed to recognize an alias.

    Returns:
        True if both are named and they co-occur in at least one chapter.
    """
    if not profile_a.is_named or not profile_b.is_named:
        return False

    # Collect chapter sets for all names/aliases of each profile
    chapters_a: set[int] = set()
    for name in [profile_a.name] + list(profile_a.aliases):
        key = name.lower().strip()
        if key in name_to_chapters:
            chapters_a.update(name_to_chapters[key])

    chapters_b: set[int] = set()
    for name in [profile_b.name] + list(profile_b.aliases):
        key = name.lower().strip()
        if key in name_to_chapters:
            chapters_b.update(name_to_chapters[key])

    if not chapters_a or not chapters_b:
        return False

    return bool(chapters_a & chapters_b)


def _consolidate_with_llm(
    profiles: list[CharacterProfile],
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path,
) -> list[CharacterProfile]:
    """Use LLM to identify remaining duplicates with co-occurrence guard.

    Skips if <= 5 profiles (too few to warrant LLM call).
    Validates proposed merges against co-occurrence data.
    """
    if len(profiles) <= 5:
        return profiles

    # Build co-occurrence map
    name_to_chapters, _ = _build_cooccurrence(chapter_characters)

    # Build numbered summary for LLM
    lines: list[str] = []
    for i, p in enumerate(profiles):
        aliases_str = ", ".join(p.aliases) if p.aliases else "none"
        lines.append(
            f"{i}. {p.name} | aliases: {aliases_str} | "
            f"gender: {p.gender} | age: {p.age_range} | "
            f"named: {p.is_named} | {p.description}"
        )
    summary = "\n".join(lines)

    # Cache check
    cache_key = get_cache_key(summary, "consolidation")
    cached = check_cache(cache_dir, cache_key)
    if cached is not None:
        logger.info("Consolidation: cache hit")
        result = ConsolidationResult.model_validate(cached)
    else:
        logger.info(
            "Consolidation: calling LLM with %d profiles", len(profiles)
        )
        result = call_llm_structured(
            CONSOLIDATION_SYSTEM_PROMPT,
            summary,
            ConsolidationResult,
        )
        if result is None:
            logger.warning("Consolidation: LLM call failed, skipping")
            return profiles
        write_cache(cache_dir, cache_key, result.model_dump())

    if not result.groups:
        logger.info("Consolidation: no duplicates found by LLM")
        return profiles

    # Validate and apply merges
    used_indices: set[int] = set()
    valid_groups: list[list[int]] = []

    for group in result.groups:
        # Validate indices
        if any(idx < 0 or idx >= len(profiles) for idx in group.indices):
            logger.warning(
                "Consolidation: rejecting group with out-of-range indices: %s",
                group.indices,
            )
            continue

        if any(idx in used_indices for idx in group.indices):
            logger.warning(
                "Consolidation: rejecting group with already-used indices: %s",
                group.indices,
            )
            continue

        # Co-occurrence check: reject if any named+named pair co-occurs
        rejected = False
        group_profiles = [profiles[idx] for idx in group.indices]
        for a_idx in range(len(group_profiles)):
            for b_idx in range(a_idx + 1, len(group_profiles)):
                if _named_pair_cooccurs(
                    group_profiles[a_idx],
                    group_profiles[b_idx],
                    name_to_chapters,
                ):
                    logger.warning(
                        "Consolidation: rejecting group %s — "
                        "named pair '%s' and '%s' co-occur",
                        group.indices,
                        group_profiles[a_idx].name,
                        group_profiles[b_idx].name,
                    )
                    rejected = True
                    break
            if rejected:
                break

        if not rejected:
            valid_groups.append(list(group.indices))
            used_indices.update(group.indices)
            logger.info(
                "Consolidation: merging group %s (%s)",
                group.indices,
                group.reasoning,
            )

    if not valid_groups:
        logger.info("Consolidation: no valid groups after validation")
        return profiles

    # Apply merges
    merged_indices: set[int] = set()
    result_profiles: list[CharacterProfile] = []

    for group_indices in valid_groups:
        primary = profiles[group_indices[0]]
        for idx in group_indices[1:]:
            primary = _merge_two_profiles(primary, profiles[idx])
        result_profiles.append(primary)
        merged_indices.update(group_indices)

    # Add un-merged profiles
    for i, p in enumerate(profiles):
        if i not in merged_indices:
            result_profiles.append(p)

    logger.info(
        "Consolidation: %d profiles -> %d after LLM merge",
        len(profiles),
        len(result_profiles),
    )
    return result_profiles


# ---------------------------------------------------------------------------
# Main merge pipeline
# ---------------------------------------------------------------------------


def merge_characters(
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path | None = None,
) -> list[CharacterProfile]:
    """Merge per-chapter character lists into a deduplicated registry.

    Multi-stage merge:
    1. Exact name match (case-insensitive)
    2. Fuzzy name match (SequenceMatcher + title/name matching)
    3. Alias/substring match (with surname-only exclusion)
    4. LLM consolidation with co-occurrence guard

    Args:
        chapter_characters: Dict mapping chapter_num -> character list.
        cache_dir: Optional cache directory for LLM consolidation caching.

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

    # Stage 2: Fuzzy name match
    profiles = _merge_by_fuzzy(profiles)
    logger.info("After fuzzy merge: %d profiles", len(profiles))

    # Stage 3: Alias/substring match
    profiles = _merge_by_substring_and_alias(profiles)
    logger.info("After substring/alias merge: %d profiles", len(profiles))

    # Stage 4: LLM consolidation
    if cache_dir is not None:
        profiles = _consolidate_with_llm(profiles, chapter_characters, cache_dir)

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
