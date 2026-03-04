"""Hybrid regex+LLM speech-act classification for dialogue segments.

Classifies every dialogue segment with a speech-act subtype:
- spoken: Normal dialogue (default baseline)
- thought: Internal monologue, musing, wondering
- shouted: Yelling, screaming, exclaiming
- whispered: Whispering, murmuring, muttering

Two-pass approach:
1. Regex pass: Catches obvious patterns (narration tags, ALL-CAPS, punctuation)
2. LLM pass: Refines ambiguous cases where regex confidence < 0.8

LLM always wins when it returns a result (per user decision).
Non-dialogue segments default to speech_act="spoken".

Requirements covered: LLM-02 (hybrid dialogue detection with speech-act tagging)
"""

from __future__ import annotations

import logging
import re

from src.attribution.llm_client import call_llm_structured
from src.attribution.models import SpeechActResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns for speech-act detection
# ---------------------------------------------------------------------------

# SHOUTED patterns (check narration context around dialogue)
_SHOUTED_NARRATION = re.compile(
    r"\b(shout|scream|yell|bellow|roar|exclaim|bark|thunder)"
    r"(?:ed|ing|s)?\b",
    re.IGNORECASE,
)
"""Explicit shouting tags in narration context."""

_SHOUTED_EXCLAMATION = re.compile(r"!{2,}")
"""Multiple exclamation marks in dialogue text."""

_SHOUTED_ALL_CAPS = re.compile(r"\b[A-Z]{3,}\b")
"""ALL-CAPS words in dialogue (3+ chars, will exclude common words)."""

# Common all-caps words that do NOT indicate shouting
_CAPS_EXCLUSIONS = frozenset({
    "I", "OK", "USA", "FBI", "CIA", "DNA", "CEO", "PhD", "MRS", "MR",
    "MS", "DR", "NYC", "THE", "AND", "BUT", "FOR", "NOT", "YOU", "ALL",
    "CAN", "HAD", "HER", "WAS", "ONE", "OUR", "OUT",
})

# WHISPERED patterns (check narration context)
_WHISPERED_NARRATION = re.compile(
    r"\b(whisper|murmur|hiss|breathe|mutter|mumble)"
    r"(?:ed|ing|s)?\b",
    re.IGNORECASE,
)
"""Explicit whispering tags in narration context."""

# THOUGHT patterns (check narration context + dialogue markers)
_THOUGHT_VERBS = re.compile(
    r"\b(thought|wondered|mused|pondered|reflected|realized|considered)"
    r"\b",
    re.IGNORECASE,
)
"""Explicit thought verbs in narration context."""

_THOUGHT_TO_SELF = re.compile(
    r"\bto\s+(?:her|him|them|it)self\b",
    re.IGNORECASE,
)
"""'to herself' / 'to himself' pattern in narration context."""

# ---------------------------------------------------------------------------
# Confidence levels
# ---------------------------------------------------------------------------

CONF_NARRATION_TAG = 0.9
"""High confidence for explicit narration tags ('she whispered')."""

CONF_TEXT_PATTERN = 0.7
"""Medium confidence for text patterns (ALL-CAPS, !!)."""

CONF_DEFAULT = 0.5
"""Low confidence for default 'spoken' when no patterns match."""

CONF_LLM_THRESHOLD = 0.8
"""Regex results below this confidence are sent to LLM for refinement."""

# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

_SPEECH_ACT_SYSTEM_PROMPT = """\
You are a speech-act classifier for audiobook production. \
Classify each dialogue line's delivery style.

Speech-act types:
- spoken: Normal dialogue (default for most lines)
- thought: Internal monologue, musing, character thinking to themselves
- shouted: Yelling, screaming, exclaiming with raised voice
- whispered: Whispering, murmuring, speaking very quietly

Consider:
1. Surrounding narration (e.g., "he whispered", "she shouted")
2. Punctuation (!! for shouting)
3. Content (internal monologue vs spoken dialogue)
4. Context (thought verbs like 'wondered', 'to herself')
5. ALL-CAPS words typically indicate shouting

Most lines are "spoken". Only classify as something else \
when there is clear evidence. When in doubt, default to "spoken".\
"""


# ---------------------------------------------------------------------------
# Core classification functions
# ---------------------------------------------------------------------------


def classify_speech_act_regex(
    text: str,
    context_before: str,
    context_after: str,
) -> tuple[str, float]:
    """Classify a dialogue segment's speech-act using regex patterns.

    Checks narration context (before and after) for explicit speech tags,
    then checks the dialogue text itself for patterns.

    Args:
        text: The dialogue segment text.
        context_before: Narration text before this dialogue segment.
        context_after: Narration text after this dialogue segment.

    Returns:
        Tuple of (speech_act, confidence). speech_act is one of
        'spoken', 'thought', 'shouted', 'whispered'. confidence
        is 0.0-1.0.
    """
    context = f"{context_before} {context_after}"

    # Check narration context first (highest confidence)

    # SHOUTED: narration tags
    if _SHOUTED_NARRATION.search(context):
        return ("shouted", CONF_NARRATION_TAG)

    # WHISPERED: narration tags
    if _WHISPERED_NARRATION.search(context):
        return ("whispered", CONF_NARRATION_TAG)

    # THOUGHT: narration verbs
    if _THOUGHT_VERBS.search(context):
        return ("thought", CONF_NARRATION_TAG)

    # THOUGHT: "to herself" etc.
    if _THOUGHT_TO_SELF.search(context):
        return ("thought", CONF_NARRATION_TAG)

    # Check dialogue text patterns (medium confidence)

    # SHOUTED: multiple exclamation marks
    if _SHOUTED_EXCLAMATION.search(text):
        return ("shouted", CONF_TEXT_PATTERN)

    # SHOUTED: ALL-CAPS words (excluding common abbreviations)
    caps_matches = _SHOUTED_ALL_CAPS.findall(text)
    significant_caps = [w for w in caps_matches if w not in _CAPS_EXCLUSIONS]
    if significant_caps:
        return ("shouted", CONF_TEXT_PATTERN)

    # Default: spoken
    return ("spoken", CONF_DEFAULT)


def classify_speech_acts_llm(
    segments: list[dict],
    chapter_num: int,
) -> dict[int, tuple[str, float]]:
    """Classify speech-acts for dialogue segments via LLM.

    Sends a batch of dialogue segments with context to the LLM for
    speech-act classification.

    Args:
        segments: List of dialogue segment dicts to classify.
            Each must have 'id', 'text', and optionally 'context_before'
            and 'context_after' keys.
        chapter_num: Chapter number for logging.

    Returns:
        Dict mapping segment_id -> (speech_act, confidence).
        Empty dict if LLM call fails.
    """
    if not segments:
        return {}

    # Build user prompt with segments and their context
    lines: list[str] = []
    for seg in segments:
        seg_id = seg["id"]
        text = seg.get("text", "")
        ctx_before = seg.get("_context_before", "")
        ctx_after = seg.get("_context_after", "")

        lines.append(f"Segment {seg_id}: {text}")
        if ctx_before:
            lines.append(f'  [Before: "{ctx_before}"]')
        if ctx_after:
            lines.append(f'  [After: "{ctx_after}"]')
        lines.append("")

    user_content = "\n".join(lines)

    logger.info(
        "Chapter %d: classifying %d segments via LLM (%d chars)",
        chapter_num, len(segments), len(user_content),
    )

    result = call_llm_structured(
        _SPEECH_ACT_SYSTEM_PROMPT,
        user_content,
        SpeechActResult,
    )

    if result is None:
        logger.warning(
            "Chapter %d: LLM speech-act classification failed", chapter_num
        )
        return {}

    # Build result map
    result_map: dict[int, tuple[str, float]] = {}
    valid_acts = {"spoken", "thought", "shouted", "whispered"}
    for tag in result.tags:
        act = tag.speech_act.lower().strip()
        if act not in valid_acts:
            act = "spoken"
        result_map[tag.segment_id] = (act, tag.confidence)

    return result_map


def classify_speech_acts(
    segments: list[dict],
    chapter_num: int,
) -> list[dict]:
    """Classify speech-acts for all segments in a chapter.

    Main entry point. Runs hybrid regex+LLM classification:
    1. Regex pass on all dialogue segments with surrounding context
    2. LLM pass for segments where regex confidence < 0.8
    3. Merge: LLM wins when it returns a result

    Non-dialogue segments get speech_act="spoken" (default/baseline).

    Args:
        segments: Full chapter segment list (includes narration for context).
        chapter_num: 1-based chapter number.

    Returns:
        The same segments list with speech_act field added to each segment.
    """
    # Pass 1: Regex on all dialogue segments
    regex_results: dict[int, tuple[str, float]] = {}
    needs_llm: list[dict] = []

    for i, seg in enumerate(segments):
        if seg.get("type") != "dialogue":
            seg["speech_act"] = "spoken"
            continue

        # Build context from surrounding segments
        context_before = ""
        for offset in range(1, 3):
            prev_idx = i - offset
            if prev_idx >= 0:
                prev_text = segments[prev_idx].get("text", "")[:200]
                context_before = f"{prev_text} {context_before}"

        context_after = ""
        for offset in range(1, 3):
            next_idx = i + offset
            if next_idx < len(segments):
                next_text = segments[next_idx].get("text", "")[:200]
                context_after = f"{context_after} {next_text}"

        text = seg.get("text", "")
        act, conf = classify_speech_act_regex(text, context_before, context_after)
        regex_results[seg["id"]] = (act, conf)

        if conf < CONF_LLM_THRESHOLD:
            # Prepare segment for LLM with context
            seg_copy = dict(seg)
            seg_copy["_context_before"] = context_before.strip()
            seg_copy["_context_after"] = context_after.strip()
            needs_llm.append(seg_copy)

    # Pass 2: LLM for low-confidence regex results
    llm_results: dict[int, tuple[str, float]] = {}
    if needs_llm:
        logger.info(
            "Chapter %d: %d/%d dialogue segments need LLM refinement",
            chapter_num,
            len(needs_llm),
            len(regex_results),
        )
        llm_results = classify_speech_acts_llm(needs_llm, chapter_num)

    # Pass 3: Merge and apply
    for seg in segments:
        if seg.get("type") != "dialogue":
            continue

        seg_id = seg["id"]

        # LLM always wins when available
        if seg_id in llm_results:
            act, _ = llm_results[seg_id]
            seg["speech_act"] = act
        elif seg_id in regex_results:
            act, _ = regex_results[seg_id]
            seg["speech_act"] = act
        else:
            seg["speech_act"] = "spoken"

    # Stats
    act_counts: dict[str, int] = {}
    for seg in segments:
        act = seg.get("speech_act", "spoken")
        act_counts[act] = act_counts.get(act, 0) + 1

    logger.info(
        "Chapter %d speech-acts: %s",
        chapter_num,
        ", ".join(f"{k}={v}" for k, v in sorted(act_counts.items())),
    )

    return segments
