"""LLM-based distinctiveness pass for voice profiles (PROF-02).

Reviews all character voice profiles together and pushes similar-sounding
characters apart so each sounds distinctly different in the audiobook.

Called after extraction + merge, before voice overrides and matching.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.attribution.cache import check_cache, get_cache_key, write_cache
from src.attribution.llm_client import call_llm_structured
from src.attribution.models import CharacterProfile, DistinctivenessResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DISTINCTIVENESS_PROMPT = """\
You are a voice casting director reviewing character voice profiles for an audiobook.
Your job: ensure every character sounds DISTINCTLY different from every other character.

Review the profiles below. For any pair that sound too similar, modify one or both to
create audible separation. Push traits to opposite extremes where possible.

Rules:
- Every character must be distinguishable by at least 2 voice traits
- If two characters share pitch+pace+tone, change at least one trait for one character
- Preserve traits that are strongly supported by literary evidence
- Push apart the character with LESS textual evidence (more flexibility)
- Return ALL profiles, even unmodified ones
- The modifications list should describe each change in human-readable form"""

# Maximum characters per distinctiveness batch (to fit in Qwen 3.5 9B context)
MAX_BATCH_SIZE = 15


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_distinctiveness_pass(
    characters: list[CharacterProfile],
    cache_dir: Path,
) -> list[CharacterProfile]:
    """Review all profiles together and push similar ones apart.

    Sends all character voice profiles to the LLM for review. If the LLM
    returns a valid result with matching character count, updates profiles
    from the response. Falls back to original profiles on any error.

    Args:
        characters: List of merged character profiles.
        cache_dir: Directory for cache files.

    Returns:
        Updated list of CharacterProfile with distinctive voice profiles.
    """
    if not characters:
        return characters

    # Build compact representation for LLM (name + voice_profile only)
    user_content = _build_user_content(characters)

    # Check cache
    cache_key = get_cache_key(user_content, "distinctiveness_v1")
    cached = check_cache(cache_dir, cache_key)
    if cached is not None:
        logger.info("Distinctiveness pass: cache hit, skipping LLM call")
        try:
            result = DistinctivenessResult.model_validate(cached)
            return _apply_result(characters, result)
        except Exception:
            logger.warning("Distinctiveness pass: cached data invalid, re-running")

    # Handle batching for large casts
    if len(characters) > MAX_BATCH_SIZE:
        return _batched_pass(characters, cache_dir, user_content, cache_key)

    # Single-pass for normal-sized casts
    result = call_llm_structured(
        DISTINCTIVENESS_PROMPT,
        user_content,
        DistinctivenessResult,
    )

    if result is None:
        logger.warning("Distinctiveness pass: LLM returned None, keeping originals")
        return characters

    # Validate character count
    if len(result.characters) != len(characters):
        logger.warning(
            "Distinctiveness pass: LLM returned %d characters (expected %d), "
            "falling back to originals",
            len(result.characters),
            len(characters),
        )
        return characters

    # Log modifications
    for mod in result.modifications:
        logger.info("Distinctiveness: %s", mod)

    # Cache the result
    write_cache(cache_dir, cache_key, result.model_dump())

    return _apply_result(characters, result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_user_content(characters: list[CharacterProfile]) -> str:
    """Build compact user content with just names and voice profiles."""
    lines: list[str] = []
    for char in characters:
        vp = char.voice_profile
        lines.append(
            f"Character: {char.name}\n"
            f"  pitch: {vp.pitch}\n"
            f"  pace: {vp.pace}\n"
            f"  tone: {vp.tone}\n"
            f"  accent: {vp.accent}\n"
            f"  pace_style: {vp.pace_style}\n"
            f"  tone_style: {vp.tone_style}\n"
            f"  energy: {vp.energy}\n"
            f"  typical_emotion: {vp.typical_emotion}\n"
            f"  description: {vp.description}"
        )
    return "\n\n".join(lines)


def _apply_result(
    originals: list[CharacterProfile],
    result: DistinctivenessResult,
) -> list[CharacterProfile]:
    """Apply LLM distinctiveness results to original profiles.

    Matches returned characters by name (case-insensitive). For matched
    characters, updates their voice_profile from the LLM result. For
    unmatched, keeps original.
    """
    # Build lookup by lowercase name
    result_map: dict[str, CharacterProfile] = {
        c.name.lower(): c for c in result.characters
    }

    updated: list[CharacterProfile] = []
    for orig in originals:
        matched = result_map.get(orig.name.lower())
        if matched is not None:
            # Update voice_profile from LLM result, keep everything else
            updated.append(orig.model_copy(update={"voice_profile": matched.voice_profile}))
        else:
            logger.warning(
                "Distinctiveness pass: no match for '%s', keeping original",
                orig.name,
            )
            updated.append(orig)

    return updated


def _batched_pass(
    characters: list[CharacterProfile],
    cache_dir: Path,
    user_content: str,
    cache_key: str,
) -> list[CharacterProfile]:
    """Run distinctiveness in batches for large casts (>15 characters)."""
    batch_size = 12
    all_updated = list(characters)  # Start with copies

    for start in range(0, len(characters), batch_size):
        batch = characters[start : start + batch_size]
        batch_content = _build_user_content(batch)

        result = call_llm_structured(
            DISTINCTIVENESS_PROMPT,
            batch_content,
            DistinctivenessResult,
        )

        if result is None or len(result.characters) != len(batch):
            logger.warning(
                "Distinctiveness batch %d-%d: invalid result, keeping originals",
                start,
                start + len(batch),
            )
            continue

        # Apply batch results
        batch_result_map = {c.name.lower(): c for c in result.characters}
        for i, orig in enumerate(batch):
            matched = batch_result_map.get(orig.name.lower())
            if matched is not None:
                all_updated[start + i] = orig.model_copy(
                    update={"voice_profile": matched.voice_profile}
                )

        for mod in result.modifications:
            logger.info("Distinctiveness: %s", mod)

    # Cache the combined result
    combined = DistinctivenessResult(characters=all_updated, modifications=[])
    write_cache(cache_dir, cache_key, combined.model_dump())

    return all_updated
