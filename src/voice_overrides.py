"""Voice overrides — user-controlled voice profile patches (PROF-03).

Loads voice_overrides.yaml from the book output directory and applies
overrides as the LAST step in the profile pipeline (after extraction,
merge, and distinctiveness).

Supports overriding individual voice_profile fields and forcing a
specific LibriTTS speaker_id per character.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

from src.attribution.models import CharacterProfile, VoiceProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class VoiceOverride(BaseModel):
    """Override specification for a single character."""

    voice_profile: dict[str, str] | None = None
    """Partial voice profile fields to merge (not replace)."""

    speaker_id: str | None = None
    """Force a specific LibriTTS speaker ID for this character."""


class VoiceOverrides(BaseModel):
    """Top-level voice_overrides.yaml schema."""

    characters: dict[str, VoiceOverride] = {}
    """Character name -> override mapping."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_voice_overrides(book_dir: Path) -> VoiceOverrides | None:
    """Load voice_overrides.yaml from book directory if it exists.

    Args:
        book_dir: Book output directory to search for voice_overrides.yaml.

    Returns:
        Parsed VoiceOverrides, or None if file doesn't exist or is empty.
    """
    overrides_path = book_dir / "voice_overrides.yaml"
    if not overrides_path.exists():
        return None

    with open(overrides_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if raw is None:
        return None

    return VoiceOverrides.model_validate(raw)


def apply_voice_overrides(
    characters: list[CharacterProfile],
    overrides: VoiceOverrides,
) -> list[CharacterProfile]:
    """Apply voice_overrides.yaml to character profiles (final step).

    Case-insensitive name matching. For matched characters, merges
    voice_profile fields from override dict (partial update, not replace).

    Args:
        characters: List of character profiles to patch.
        overrides: Parsed overrides from voice_overrides.yaml.

    Returns:
        Updated list of CharacterProfile with overrides applied.
    """
    override_map = {name.lower(): ov for name, ov in overrides.characters.items()}
    result: list[CharacterProfile] = []

    for char in characters:
        key = char.name.lower()
        ov = override_map.get(key)
        if ov is None:
            result.append(char)
            continue

        updates: dict = {}
        if ov.voice_profile:
            vp_dict = char.voice_profile.model_dump()
            vp_dict.update(ov.voice_profile)
            updates["voice_profile"] = VoiceProfile(**vp_dict)
            logger.info(
                "Voice override applied for '%s': %s",
                char.name,
                list(ov.voice_profile.keys()),
            )

        result.append(char.model_copy(update=updates))

    return result
