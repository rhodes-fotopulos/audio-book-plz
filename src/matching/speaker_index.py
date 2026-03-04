"""LibriTTS-P speaker index loader with filtering and cast classification.

Loads speaker annotations from the three annotator CSV files (df1_en.csv,
df2_en.csv, df3_en.csv), merges them into a unified index, and provides
filtering by gender and age for candidate selection.

Also classifies characters as major/minor by dialogue line count.
"""

from __future__ import annotations

import csv
import logging
import re
from collections import Counter
from pathlib import Path

from src.matching.models import CastClassification, SpeakerAnnotation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANNOTATOR_FILES = ["df1_en.csv", "df2_en.csv", "df3_en.csv"]
"""LibriTTS-P annotator CSV filenames."""

AGE_KEYWORDS: dict[str, list[str]] = {
    "child": ["young", "childish"],
    "young adult": ["young", "adult-like"],
    "middle-aged": ["adult-like", "middle-aged"],
    "elderly": ["old", "middle-aged"],
}
"""Mapping from character age_range to LibriTTS-P trait keywords."""

# First-person pronoun pattern for narrator mode detection
_FIRST_PERSON_RE = re.compile(
    r"\b(I |I'[mdvs]|my |me |myself|mine )\b", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Speaker index loading
# ---------------------------------------------------------------------------


def _infer_gender(traits: set[str]) -> str:
    """Infer speaker gender from trait keywords.

    Checks for masculine/feminine keywords with any modifier
    (e.g., 'very masculine' still counts as masculine).
    """
    has_masculine = any(
        "masculine" in t for t in traits
    )
    has_feminine = any(
        "feminine" in t for t in traits
    )
    if has_masculine and not has_feminine:
        return "male"
    if has_feminine and not has_masculine:
        return "female"
    # Both or neither — ambiguous
    return "unknown"


def load_speaker_index(data_dir: Path) -> dict[str, SpeakerAnnotation]:
    """Load and merge LibriTTS-P speaker annotations from all 3 annotators.

    Each CSV uses pipe-delimited format with no header:
        speaker_id|comma,separated,traits

    Traits from all annotators are merged (union) and agreement is tracked.

    Args:
        data_dir: Path to directory containing df1_en.csv, df2_en.csv, df3_en.csv.

    Returns:
        Dict mapping speaker_id (str) to SpeakerAnnotation.

    Raises:
        FileNotFoundError: If any annotator CSV is missing.
    """
    # Collect traits per speaker across annotators
    all_traits: dict[str, list[list[str]]] = {}

    for csv_file in ANNOTATOR_FILES:
        path = data_dir / csv_file
        if not path.exists():
            raise FileNotFoundError(f"Missing annotator file: {path}")

        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="|")
            for row in reader:
                if len(row) != 2:
                    continue
                speaker_id = row[0].strip()
                traits = [t.strip() for t in row[1].split(",") if t.strip()]
                if speaker_id not in all_traits:
                    all_traits[speaker_id] = []
                all_traits[speaker_id].append(traits)

    # Merge annotations per speaker
    index: dict[str, SpeakerAnnotation] = {}
    for speaker_id, annotator_lists in all_traits.items():
        # Union all traits
        merged_traits: set[str] = set()
        # Count agreement
        trait_counter: Counter[str] = Counter()
        for trait_list in annotator_lists:
            merged_traits.update(trait_list)
            trait_counter.update(trait_list)

        sorted_traits = sorted(merged_traits)
        gender = _infer_gender(merged_traits)
        agreement = dict(trait_counter)

        index[speaker_id] = SpeakerAnnotation(
            speaker_id=speaker_id,
            traits=sorted_traits,
            trait_text=", ".join(sorted_traits),
            gender=gender,
            annotator_agreement=agreement,
        )

    logger.info("Loaded %d speakers from LibriTTS-P", len(index))
    return index


# ---------------------------------------------------------------------------
# Candidate filtering
# ---------------------------------------------------------------------------


def filter_candidates(
    index: dict[str, SpeakerAnnotation],
    gender: str,
    age_range: str = "unknown",
) -> list[SpeakerAnnotation]:
    """Filter speakers by gender and age for candidate selection.

    Gender filter is mandatory (unless character gender is 'unknown').
    Age filter is soft — falls back to all gender-matched if no age matches.

    Args:
        index: Full speaker index from load_speaker_index.
        gender: Character gender ('male', 'female', 'unknown', etc.).
        age_range: Character age range ('child', 'young adult', etc.).

    Returns:
        List of matching SpeakerAnnotation objects, sorted by speaker_id.
    """
    speakers = list(index.values())

    # Gender filter (mandatory unless unknown)
    if gender != "unknown":
        # Map character gender to speaker annotation gender
        target_gender = gender.lower()
        if target_gender in ("male", "female"):
            speakers = [s for s in speakers if s.gender == target_gender]
        # If no matches after gender filter, fall back to all
        if not speakers:
            speakers = list(index.values())

    # Age filter (soft)
    age_keywords = AGE_KEYWORDS.get(age_range, [])
    if age_keywords:
        age_matched = [
            s for s in speakers
            if any(
                any(kw in trait for trait in s.traits)
                for kw in age_keywords
            )
        ]
        # Only apply age filter if it yields results
        if age_matched:
            speakers = age_matched

    return sorted(speakers, key=lambda s: s.speaker_id)


# ---------------------------------------------------------------------------
# Cast classification
# ---------------------------------------------------------------------------


def classify_cast(
    characters: list[dict],
    segments: list[dict],
    default_threshold: int = 5,
) -> CastClassification:
    """Classify characters as major or minor by dialogue line count.

    Major characters (>= threshold) get LLM-based matching with
    uniqueness enforcement. Minor characters use embedding similarity
    and can share voices if not in the same chapter.

    Threshold adjusts for large casts: if >20 characters, uses
    max(default_threshold, total_dialogue_lines // 20).

    Args:
        characters: List of character profile dicts (from characters.json).
        segments: List of attributed segment dicts (from attributed.json).
        default_threshold: Base dialogue count threshold for major status.

    Returns:
        CastClassification with major/minor lists and narrator mode.
    """
    # Count dialogue lines per speaker
    dialogue_counts: Counter[str] = Counter()
    for seg in segments:
        if seg.get("type") == "dialogue":
            speaker = seg.get("speaker", "")
            if speaker and speaker != "narrator" and speaker != "unknown":
                dialogue_counts[speaker] += 1

    # Build character name list
    char_names = [c.get("name", "") if isinstance(c, dict) else c.name for c in characters]

    # Adjust threshold for large casts
    threshold = default_threshold
    if len(char_names) > 20:
        total_dialogue = sum(dialogue_counts.values())
        threshold = max(default_threshold, total_dialogue // 20)

    # Classify
    major = []
    minor = []
    for name in char_names:
        if dialogue_counts.get(name, 0) >= threshold:
            major.append(name)
        else:
            minor.append(name)

    # Determine narrator mode
    narrator_mode = _detect_narrator_mode(segments)

    return CastClassification(
        major=major,
        minor=minor,
        threshold=threshold,
        narrator_mode=narrator_mode,
    )


def _detect_narrator_mode(segments: list[dict]) -> str:
    """Detect whether the book uses first-person or third-person narration.

    Samples narration segments for first-person pronoun usage.
    If >30% of sampled narration contains first-person pronouns,
    classifies as first_person.

    Returns:
        'first_person' or 'third_person'.
    """
    narration_segments = [
        s for s in segments
        if s.get("type") == "narration" and s.get("speaker") == "narrator"
    ]

    # Sample up to 20 narration segments
    sample = narration_segments[:20]
    if not sample:
        return "third_person"

    first_person_count = sum(
        1 for s in sample
        if _FIRST_PERSON_RE.search(s.get("text", ""))
    )

    ratio = first_person_count / len(sample)
    return "first_person" if ratio > 0.3 else "third_person"
