"""Character profile merger — alias detection and deduplication.

Merges per-chapter character lists into a single deduplicated registry.
Uses a 4-stage merge pipeline:
  1. Exact name match (always correct, records audit decisions)
  2. Candidate pair generation (fuzzy + substring + alias — no auto-merge)
  3. LLM merge arbiter (accepts/rejects candidates with confidence)
  4. Post-merge validation (flags anomalies, warn-and-continue)

Requirements covered: ATTR-02, MERGE-01 through MERGE-07
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import call_llm_structured
from src.attribution.models import (
    CharacterProfile,
    MergeAudit,
    MergeDecision,
    VoiceProfile,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_SUBSTRING_LENGTH = 3
"""Minimum length for a name to be considered in substring matching."""

TRAIT_CAP = 30
"""Maximum personality traits per profile after merge (MERGE-06)."""

LLM_CONFIDENCE_THRESHOLD = 0.7
"""Minimum LLM confidence to accept a merge (below = skip)."""

TITLES = {"mr", "mrs", "miss", "ms", "dr", "sir", "lady", "lord", "captain", "colonel"}
"""Common title prefixes for title/name matching."""


# ---------------------------------------------------------------------------
# LLM arbiter response models
# ---------------------------------------------------------------------------


class MergeArbiterDecision(BaseModel):
    """A single merge decision from the LLM arbiter."""
    pair_index: int
    decision: str  # "merge" or "reject"
    confidence: float
    reasoning: str


class MergeArbiterResult(BaseModel):
    """LLM response for batch merge arbitration."""
    decisions: list[MergeArbiterDecision]


# ---------------------------------------------------------------------------
# LLM arbiter prompt
# ---------------------------------------------------------------------------

MERGE_ARBITER_PROMPT = """\
You are a character identity specialist for novels. For each candidate pair, \
determine if they are the SAME person or DIFFERENT people.

Rules:
- Default to DIFFERENT unless you are confident they are the same person.
- Nicknames and formal names of the same person should be merged \
  (e.g. "Lizzy" and "Elizabeth Bennet" are the same person).
- Characters who share a surname are usually DIFFERENT people \
  (e.g. "Mr. Bennet" and "Elizabeth Bennet" are father and daughter).
- Titles change but the person doesn't: "Miss Darcy" and "Georgiana Darcy" \
  are the same person.
- "Mr. Bennet" and "Mrs. Bennet" are ALWAYS different (husband and wife).
- Spelling variants of the same name ARE the same person \
  (e.g. "Mrs. Phillips" and "Mrs. Philips").
- Co-occurrence in the same chapter does NOT automatically mean different people. \
  Name variants of the same person often appear in the same chapter.

For each pair, return:
- decision: "merge" or "reject"
- confidence: 0.0-1.0 (how sure you are)
- reasoning: brief explanation"""


# ---------------------------------------------------------------------------
# Name matching helpers
# ---------------------------------------------------------------------------


def _names_match_substring(name_a: str, name_b: str) -> bool:
    """Check if one name is a substring of the other (case-insensitive).

    Requires the shorter name to be at least MIN_SUBSTRING_LENGTH characters
    to avoid matching trivial strings like "I" or "Mr".
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
    """
    a_names = {profile_a.name.lower().strip()}
    a_names.update(alias.lower().strip() for alias in profile_a.aliases)

    b_names = {profile_b.name.lower().strip()}
    b_names.update(alias.lower().strip() for alias in profile_b.aliases)

    return bool(a_names & b_names)


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------


def _names_match_fuzzy(name_a: str, name_b: str, threshold: float = 0.85) -> bool:
    """Check if two names are fuzzy matches using SequenceMatcher.

    Uses a higher threshold for short names to avoid false positives.
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


# ---------------------------------------------------------------------------
# Audit trail helper
# ---------------------------------------------------------------------------


def _record_decision(
    audit: MergeAudit,
    stage: str,
    profile_a_name: str,
    profile_b_name: str,
    action: str,
    reason: str,
    confidence: float,
    details: dict | None = None,
) -> None:
    """Record a merge decision in the audit trail."""
    decision = MergeDecision(
        stage=stage,
        profile_a=profile_a_name,
        profile_b=profile_b_name,
        action=action,
        reason=reason,
        confidence=confidence,
        details=details or {},
    )
    audit.stages.setdefault(stage, []).append(decision)


# ---------------------------------------------------------------------------
# Profile merging
# ---------------------------------------------------------------------------


def _merge_two_profiles(
    primary: CharacterProfile,
    secondary: CharacterProfile,
    all_canonical_names: set[str] | None = None,
    audit: MergeAudit | None = None,
    merge_group_names: set[str] | None = None,
) -> CharacterProfile:
    """Merge two profiles determined to be the same character.

    The primary profile is preferred for most fields, but the longer/more
    formal name is chosen as canonical. All aliases and traits are unioned.

    MERGE-04: Cross-name exclusion — aliases matching another profile's
    canonical name are blocked.
    MERGE-06: Trait cap — traits capped at TRAIT_CAP after merge.

    Args:
        primary: The profile to prefer for name/description.
        secondary: The profile to merge into primary.
        all_canonical_names: Set of lowercase canonical names of all profiles.
            Used for cross-name exclusion (MERGE-04).
        audit: Optional audit trail for logging blocked aliases.

    Returns:
        A new merged CharacterProfile.
    """
    if all_canonical_names is None:
        all_canonical_names = set()

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

    # MERGE-04: Cross-name exclusion — block aliases that match another
    # profile's canonical name (case-insensitive), but allow names from
    # profiles being merged together (LLM already approved the merge)
    if merge_group_names is None:
        merge_group_names = set()
    blocked_aliases: set[str] = set()
    for alias in all_aliases:
        alias_lower = alias.lower().strip()
        # Check against all canonical names EXCEPT this profile's own canonical
        # and names in the current merge group (LLM-approved merges)
        if (alias_lower in all_canonical_names
                and alias_lower != canonical_name.lower().strip()
                and alias_lower not in merge_group_names):
            blocked_aliases.add(alias)
            logger.warning(
                "Cross-name exclusion: blocked alias '%s' on profile '%s' "
                "(matches canonical name of another profile)",
                alias, canonical_name,
            )
            if audit is not None:
                _record_decision(
                    audit, "cross_name_exclusion",
                    canonical_name, alias,
                    action="rejected",
                    reason=f"Alias '{alias}' matches canonical name of another profile",
                    confidence=1.0,
                )
    all_aliases -= blocked_aliases

    # Merge voice profiles: prefer non-"unknown" values
    merged_vp = _merge_voice_profiles(primary.voice_profile, secondary.voice_profile)

    # Union of personality traits (deduplicated)
    all_traits: list[str] = list(dict.fromkeys(
        primary.personality_traits + secondary.personality_traits
    ))

    # MERGE-06: Trait cap
    if len(all_traits) > TRAIT_CAP:
        overflow_count = len(all_traits) - TRAIT_CAP
        logger.warning(
            "Trait overflow for '%s': %d traits exceed cap of %d, "
            "discarding %d overflow traits",
            canonical_name, len(all_traits), TRAIT_CAP, overflow_count,
        )
        if audit is not None:
            audit.warnings.append(
                f"Trait overflow for '{canonical_name}': {len(all_traits)} traits "
                f"exceed cap of {TRAIT_CAP}, discarded {overflow_count}"
            )
        all_traits = all_traits[:TRAIT_CAP]

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
    """Merge two VoiceProfiles, preferring non-unknown values."""
    prefer_a = len(vp_a.description) >= len(vp_b.description)

    def pick(val_a: str, val_b: str) -> str:
        if val_a == "unknown" and val_b != "unknown":
            return val_b
        if val_b == "unknown" and val_a != "unknown":
            return val_a
        if val_a != "unknown" and val_b != "unknown":
            return val_a if prefer_a else val_b
        return "unknown"

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
# Co-occurrence helpers
# ---------------------------------------------------------------------------


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
                    name_is_named.setdefault(alias_key, profile.is_named)

    return name_to_chapters, name_is_named


def _get_cooccurrence_chapters(
    profile_a: CharacterProfile,
    profile_b: CharacterProfile,
    name_to_chapters: dict[str, set[int]],
) -> list[int]:
    """Get sorted list of chapters where both profiles appear.

    Used as a SIGNAL (not gate) for the LLM arbiter (MERGE-05).
    """
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

    shared = chapters_a & chapters_b
    return sorted(shared)


# ---------------------------------------------------------------------------
# Stage 1: Exact name match
# ---------------------------------------------------------------------------


def _merge_by_exact_name(
    profiles: list[CharacterProfile],
    all_canonical_names: set[str],
    audit: MergeAudit,
) -> list[CharacterProfile]:
    """Stage 1: Group and merge profiles with identical names (case-insensitive).

    Records MergeDecision for every merge with confidence=1.0.
    """
    groups: dict[str, list[CharacterProfile]] = {}
    for profile in profiles:
        key = profile.name.lower().strip()
        groups.setdefault(key, []).append(profile)

    merged: list[CharacterProfile] = []
    for group in groups.values():
        result = group[0]
        for other in group[1:]:
            _record_decision(
                audit, "exact_name",
                result.name, other.name,
                action="merged",
                reason="Exact name match (case-insensitive)",
                confidence=1.0,
            )
            result = _merge_two_profiles(result, other, all_canonical_names, audit)
        merged.append(result)

    return merged


# ---------------------------------------------------------------------------
# Stage 2: Candidate pair generation
# ---------------------------------------------------------------------------


def _generate_candidate_pairs(
    profiles: list[CharacterProfile],
    all_canonical_names: set[str],
    audit: MergeAudit,
) -> list[tuple[int, int, str, float]]:
    """Stage 2: Generate candidate merge pairs without auto-merging.

    Runs fuzzy match, substring match, alias overlap, and title/name match
    on all profile pairs. Applies surname-only exclusion to filter.

    Returns:
        List of (profile_a_idx, profile_b_idx, merge_reason, similarity_score).
    """
    candidates: list[tuple[int, int, str, float]] = []

    for i in range(len(profiles)):
        for j in range(i + 1, len(profiles)):
            profile_a = profiles[i]
            profile_b = profiles[j]

            # MERGE-07: Surname-only exclusion blocks candidate generation
            if _names_share_surname_only(profile_a.name, profile_b.name):
                _record_decision(
                    audit, "candidate_generation",
                    profile_a.name, profile_b.name,
                    action="rejected",
                    reason="Surname-only match (different titles/given names)",
                    confidence=1.0,
                )
                continue

            # Check various match signals
            merge_reasons: list[str] = []
            best_score = 0.0

            # Fuzzy match on canonical names
            a_lower = profile_a.name.lower().strip()
            b_lower = profile_b.name.lower().strip()
            ratio = SequenceMatcher(None, a_lower, b_lower).ratio()
            if _names_match_fuzzy(profile_a.name, profile_b.name):
                merge_reasons.append(f"fuzzy name match ({ratio:.2f})")
                best_score = max(best_score, ratio)

            # Title/name match on canonical names
            if _title_name_match(profile_a.name, profile_b.name):
                merge_reasons.append("title/name equivalence")
                best_score = max(best_score, 0.8)

            # Substring match
            if _names_match_substring(profile_a.name, profile_b.name):
                merge_reasons.append("substring match")
                best_score = max(best_score, 0.75)

            # Alias overlap
            if _alias_overlap(profile_a, profile_b):
                merge_reasons.append("alias overlap")
                best_score = max(best_score, 0.85)

            # Alias-to-canonical substring match
            # e.g. alias "Catherine Bennet" contains canonical "Catherine"
            if not merge_reasons:
                a_name_l = profile_a.name.lower().strip()
                b_name_l = profile_b.name.lower().strip()
                for alias in profile_b.aliases:
                    if _names_match_substring(a_name_l, alias.lower().strip()):
                        merge_reasons.append(
                            f"alias substring: '{profile_a.name}' in alias '{alias}'"
                        )
                        best_score = max(best_score, 0.7)
                        break
                if not merge_reasons:
                    for alias in profile_a.aliases:
                        if _names_match_substring(b_name_l, alias.lower().strip()):
                            merge_reasons.append(
                                f"alias substring: '{profile_b.name}' in alias '{alias}'"
                            )
                            best_score = max(best_score, 0.7)
                            break

            # Fuzzy match on aliases
            if not merge_reasons:
                all_a = [profile_a.name] + list(profile_a.aliases)
                all_b = [profile_b.name] + list(profile_b.aliases)
                for na in all_a:
                    for nb in all_b:
                        if _names_match_fuzzy(na, nb):
                            ratio = SequenceMatcher(
                                None, na.lower().strip(), nb.lower().strip()
                            ).ratio()
                            merge_reasons.append(
                                f"fuzzy alias match: '{na}' ~ '{nb}' ({ratio:.2f})"
                            )
                            best_score = max(best_score, ratio)
                            break
                        if _title_name_match(na, nb):
                            merge_reasons.append(
                                f"title/name alias match: '{na}' ~ '{nb}'"
                            )
                            best_score = max(best_score, 0.8)
                            break
                    if merge_reasons:
                        break

            if merge_reasons:
                reason_str = "; ".join(merge_reasons)
                candidates.append((i, j, reason_str, best_score))
            # No need to record rejected non-matches (too verbose)

    logger.info("Candidate generation: %d candidate pairs from %d profiles",
                len(candidates), len(profiles))
    return candidates


# ---------------------------------------------------------------------------
# Stage 3: LLM merge arbiter
# ---------------------------------------------------------------------------


def _arbitrate_with_llm(
    profiles: list[CharacterProfile],
    candidate_pairs: list[tuple[int, int, str, float]],
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path | None,
    audit: MergeAudit,
) -> list[CharacterProfile]:
    """Stage 3: Use LLM to accept/reject candidate merge pairs.

    Builds a batch prompt with all candidate pairs and their context.
    Uses co-occurrence as a signal (MERGE-05), not a binary gate.
    Applies confidence threshold (>= 0.7 merge, < 0.7 skip).
    Uses union-find for transitive merge group resolution.

    Args:
        profiles: Current profile list.
        candidate_pairs: From _generate_candidate_pairs.
        chapter_characters: Original per-chapter data for co-occurrence.
        cache_dir: Cache directory (None = skip LLM).
        audit: Audit trail to record decisions.

    Returns:
        Merged profile list after applying LLM-accepted merges.
    """
    if not candidate_pairs:
        logger.info("LLM arbiter: no candidate pairs, skipping")
        return profiles

    if cache_dir is None:
        logger.info("LLM arbiter: no cache_dir, skipping LLM call")
        # Record all candidates as skipped
        for idx_a, idx_b, reason, score in candidate_pairs:
            _record_decision(
                audit, "llm_arbiter",
                profiles[idx_a].name, profiles[idx_b].name,
                action="rejected",
                reason="LLM call skipped (no cache_dir)",
                confidence=0.0,
                details={"merge_reason": reason, "similarity": score},
            )
        return profiles

    # Build co-occurrence map
    name_to_chapters, _ = _build_cooccurrence(chapter_characters)

    # Build prompt with candidate pairs
    pair_lines: list[str] = []
    for pair_idx, (idx_a, idx_b, reason, score) in enumerate(candidate_pairs):
        pa = profiles[idx_a]
        pb = profiles[idx_b]

        # Co-occurrence chapters as signal (MERGE-05)
        cooccur_chapters = _get_cooccurrence_chapters(pa, pb, name_to_chapters)
        cooccur_str = (
            f"Co-occur in chapters: {cooccur_chapters}"
            if cooccur_chapters
            else "No co-occurrence detected"
        )

        aliases_a = ", ".join(pa.aliases) if pa.aliases else "none"
        aliases_b = ", ".join(pb.aliases) if pb.aliases else "none"

        pair_lines.append(
            f"Pair {pair_idx}:\n"
            f"  A: {pa.name} | aliases: {aliases_a} | gender: {pa.gender} | "
            f"age: {pa.age_range} | named: {pa.is_named} | {pa.description}\n"
            f"  B: {pb.name} | aliases: {aliases_b} | gender: {pb.gender} | "
            f"age: {pb.age_range} | named: {pb.is_named} | {pb.description}\n"
            f"  Match reason: {reason}\n"
            f"  {cooccur_str}"
        )

    user_content = (
        f"Evaluate these {len(candidate_pairs)} candidate merge pairs:\n\n"
        + "\n\n".join(pair_lines)
    )

    # Cache check
    cache_key = get_cache_key(user_content, "merge_arbiter_v1")
    cached = check_cache(cache_dir, cache_key)

    if cached is not None:
        logger.info("LLM arbiter: cache hit")
        arbiter_result = MergeArbiterResult.model_validate(cached)
    else:
        logger.info(
            "LLM arbiter: calling LLM with %d candidate pairs",
            len(candidate_pairs),
        )
        arbiter_result = call_llm_structured(
            MERGE_ARBITER_PROMPT,
            user_content,
            MergeArbiterResult,
        )
        if arbiter_result is None:
            logger.warning("LLM arbiter: LLM call failed, skipping all merges")
            for idx_a, idx_b, reason, score in candidate_pairs:
                _record_decision(
                    audit, "llm_arbiter",
                    profiles[idx_a].name, profiles[idx_b].name,
                    action="rejected",
                    reason="LLM call failed",
                    confidence=0.0,
                    details={"merge_reason": reason, "similarity": score},
                )
            return profiles
        write_cache(cache_dir, cache_key, arbiter_result.model_dump())

    # Process LLM decisions
    accepted_pairs: list[tuple[int, int]] = []

    for llm_decision in arbiter_result.decisions:
        pair_idx = llm_decision.pair_index
        if pair_idx < 0 or pair_idx >= len(candidate_pairs):
            logger.warning(
                "LLM arbiter: ignoring out-of-range pair_index %d", pair_idx
            )
            continue

        idx_a, idx_b, reason, score = candidate_pairs[pair_idx]

        if llm_decision.decision == "merge" and llm_decision.confidence >= LLM_CONFIDENCE_THRESHOLD:
            _record_decision(
                audit, "llm_arbiter",
                profiles[idx_a].name, profiles[idx_b].name,
                action="merged",
                reason=llm_decision.reasoning,
                confidence=llm_decision.confidence,
                details={
                    "merge_reason": reason,
                    "similarity": score,
                    "llm_decision": llm_decision.decision,
                },
            )
            accepted_pairs.append((idx_a, idx_b))
        else:
            reject_reason = llm_decision.reasoning
            if llm_decision.decision == "merge" and llm_decision.confidence < LLM_CONFIDENCE_THRESHOLD:
                reject_reason = (
                    f"Below confidence threshold ({llm_decision.confidence:.2f} < "
                    f"{LLM_CONFIDENCE_THRESHOLD}): {llm_decision.reasoning}"
                )
            _record_decision(
                audit, "llm_arbiter",
                profiles[idx_a].name, profiles[idx_b].name,
                action="rejected",
                reason=reject_reason,
                confidence=llm_decision.confidence,
                details={
                    "merge_reason": reason,
                    "similarity": score,
                    "llm_decision": llm_decision.decision,
                },
            )

    if not accepted_pairs:
        logger.info("LLM arbiter: no merges accepted")
        return profiles

    # Union-find for transitive merge groups
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for idx_a, idx_b in accepted_pairs:
        union(idx_a, idx_b)

    # Build merge groups
    groups: dict[int, list[int]] = {}
    all_involved = set()
    for idx_a, idx_b in accepted_pairs:
        all_involved.add(idx_a)
        all_involved.add(idx_b)

    for idx in all_involved:
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    # Deduplicate and sort each group
    for root in groups:
        groups[root] = sorted(set(groups[root]))

    # Build canonical names set for cross-name exclusion
    all_canonical = {p.name.lower().strip() for p in profiles}

    # Apply merges
    merged_indices: set[int] = set()
    result_profiles: list[CharacterProfile] = []

    for group_indices in groups.values():
        # Build set of all canonical names in this merge group so
        # cross-name exclusion doesn't block LLM-approved merges
        group_names = {profiles[idx].name.lower().strip() for idx in group_indices}
        primary = profiles[group_indices[0]]
        for idx in group_indices[1:]:
            primary = _merge_two_profiles(
                primary, profiles[idx], all_canonical, audit,
                merge_group_names=group_names,
            )
        result_profiles.append(primary)
        merged_indices.update(group_indices)

    # Add un-merged profiles
    for i, p in enumerate(profiles):
        if i not in merged_indices:
            result_profiles.append(p)

    logger.info(
        "LLM arbiter: %d profiles -> %d after merge (%d pairs accepted)",
        len(profiles), len(result_profiles), len(accepted_pairs),
    )
    return result_profiles


# ---------------------------------------------------------------------------
# Stage 4: Post-merge validation (MERGE-02)
# ---------------------------------------------------------------------------


def _validate_merged_profiles(
    profiles: list[CharacterProfile],
    audit: MergeAudit,
) -> None:
    """Validate merged profiles and append warnings to audit.

    Checks each profile for:
    - >5 aliases (suspicious over-merging)
    - >50 traits (should be capped, but validate)
    - alias matching another profile's canonical name (cross-contamination)

    Warn-and-continue: never blocks the pipeline.
    """
    canonical_names = {p.name.lower().strip() for p in profiles}

    for profile in profiles:
        # Check alias count
        if len(profile.aliases) > 5:
            w = (
                f"Validation: '{profile.name}' has {len(profile.aliases)} "
                f"aliases (threshold: 5)"
            )
            audit.warnings.append(w)
            logger.warning(w)

        # Check trait count
        if len(profile.personality_traits) > 50:
            w = (
                f"Validation: '{profile.name}' has "
                f"{len(profile.personality_traits)} traits (threshold: 50)"
            )
            audit.warnings.append(w)
            logger.warning(w)

        # Check alias-canonical cross-contamination
        for alias in profile.aliases:
            alias_lower = alias.lower().strip()
            if (
                alias_lower in canonical_names
                and alias_lower != profile.name.lower().strip()
            ):
                w = (
                    f"Validation: '{profile.name}' has alias '{alias}' "
                    f"matching another character's canonical name"
                )
                audit.warnings.append(w)
                logger.warning(w)


# ---------------------------------------------------------------------------
# Stage 3b: Orphan rescue
# ---------------------------------------------------------------------------

MAX_ORPHAN_ALIASES = 1
"""Profiles with at most this many aliases are considered orphan candidates."""


def _rescue_orphan_profiles(
    profiles: list[CharacterProfile],
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path | None,
    audit: MergeAudit,
) -> list[CharacterProfile]:
    """Rescue orphan profiles that may be alternate names for other characters.

    An "orphan" is a named, single-word canonical name profile with few aliases
    that didn't merge in Stage 3.  We pair each orphan against same-gender
    named profiles and ask the LLM arbiter to decide.

    This catches cases like "Catherine" (Kitty Bennet's given name) that share
    no aliases or fuzzy match with the primary profile.
    """
    # Identify orphans: single-word name, few aliases, named
    orphan_indices: list[int] = []
    for i, p in enumerate(profiles):
        if (
            p.is_named
            and len(p.name.split()) == 1
            and len(p.aliases) <= MAX_ORPHAN_ALIASES
        ):
            orphan_indices.append(i)

    if not orphan_indices:
        logger.info("Orphan rescue: no orphan profiles found")
        return profiles

    # Generate candidate pairs: orphan vs all other named profiles of same gender
    candidate_pairs: list[tuple[int, int, str, float]] = []
    for oi in orphan_indices:
        orphan = profiles[oi]
        for j, other in enumerate(profiles):
            if j == oi:
                continue
            if not other.is_named:
                continue
            if orphan.gender != other.gender:
                continue
            # Skip if this pair was already evaluated in Stage 3
            # (they would have been generated as candidates by heuristics)
            # We only want genuinely new pairs
            already_evaluated = False
            for stage in ("llm_arbiter",):
                for e in audit.stages.get(stage, []):
                    if (
                        (e.profile_a == orphan.name and e.profile_b == other.name)
                        or (e.profile_a == other.name and e.profile_b == orphan.name)
                    ):
                        already_evaluated = True
                        break
                if already_evaluated:
                    break
            if already_evaluated:
                continue
            candidate_pairs.append(
                (oi, j, "orphan rescue (single-word name, few aliases)", 0.5)
            )

    if not candidate_pairs:
        logger.info("Orphan rescue: no new candidate pairs")
        return profiles

    logger.info(
        "Orphan rescue: %d candidate pairs for %d orphan profiles",
        len(candidate_pairs), len(orphan_indices),
    )

    profiles = _arbitrate_with_llm(
        profiles, candidate_pairs, chapter_characters, cache_dir, audit
    )
    return profiles


# ---------------------------------------------------------------------------
# Main merge pipeline
# ---------------------------------------------------------------------------


def merge_characters(
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path | None = None,
    book_title: str = "",
) -> tuple[list[CharacterProfile], MergeAudit]:
    """Merge per-chapter character lists into a deduplicated registry.

    4-stage pipeline:
    1. Exact name match (case-insensitive, always correct)
    2. Candidate pair generation (fuzzy/substring/alias — no auto-merge)
    3. LLM merge arbiter (accepts/rejects candidates with confidence)
    4. Post-merge validation (flags anomalies, warn-and-continue)

    Args:
        chapter_characters: Dict mapping chapter_num -> character list.
        cache_dir: Optional cache directory for LLM arbiter caching.
        book_title: Book title for audit metadata.

    Returns:
        Tuple of (sorted list of deduplicated CharacterProfile, MergeAudit).
    """
    # Initialize audit trail
    audit = MergeAudit(
        book_title=book_title,
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_raw_profiles=0,
        total_merged_profiles=0,
    )

    # Collect all profiles into a flat list
    all_profiles: list[CharacterProfile] = []
    for chapter_num in sorted(chapter_characters.keys()):
        all_profiles.extend(chapter_characters[chapter_num])

    if not all_profiles:
        return [], audit

    audit.total_raw_profiles = len(all_profiles)
    logger.info("Merging %d raw character entries", len(all_profiles))

    # Build canonical name set for cross-name exclusion
    all_canonical_names = {p.name.lower().strip() for p in all_profiles}

    # Stage 1: Exact name match
    profiles = _merge_by_exact_name(all_profiles, all_canonical_names, audit)
    logger.info("After exact-name merge: %d profiles", len(profiles))

    # Update canonical names after exact merge
    all_canonical_names = {p.name.lower().strip() for p in profiles}

    # Stage 2: Candidate pair generation (no auto-merge)
    candidate_pairs = _generate_candidate_pairs(profiles, all_canonical_names, audit)
    logger.info("Candidate pairs generated: %d", len(candidate_pairs))

    # Stage 3: LLM merge arbiter
    if cache_dir is not None:
        profiles = _arbitrate_with_llm(
            profiles, candidate_pairs, chapter_characters, cache_dir, audit
        )
    else:
        # No cache_dir = no LLM call, record candidates as skipped
        for idx_a, idx_b, reason, score in candidate_pairs:
            _record_decision(
                audit, "llm_arbiter",
                profiles[idx_a].name, profiles[idx_b].name,
                action="rejected",
                reason="LLM call skipped (no cache_dir)",
                confidence=0.0,
                details={"merge_reason": reason, "similarity": score},
            )

    # Stage 3b: Orphan rescue — single-name profiles with no aliases that
    # didn't merge may be alternate names for another character (e.g.
    # "Catherine" for Kitty Bennet).  Pair them against same-gender named
    # profiles and ask the LLM.
    if cache_dir is not None:
        profiles = _rescue_orphan_profiles(
            profiles, chapter_characters, cache_dir, audit
        )

    # Stage 4: Post-merge validation
    _validate_merged_profiles(profiles, audit)

    # Sort: named first, then alphabetically
    profiles.sort(key=lambda p: (not p.is_named, p.name.lower()))

    # Finalize audit
    audit.total_merged_profiles = len(profiles)
    audit.final_profiles = [p.name for p in profiles]

    logger.info("Final registry: %d characters", len(profiles))
    return profiles, audit
