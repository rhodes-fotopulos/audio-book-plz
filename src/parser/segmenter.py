"""Text segmenter: dialogue detection, type classification, and sentence splitting.

Transforms raw text blocks from the HTML cleaner into typed, speech-ready segments.

Requirements covered: PARSE-03, PARSE-04, PARSE-06
"""

from __future__ import annotations

import re
import nltk

from src.parser.models import Segment, SegmentType


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

CHAR_LIMIT = 280
"""Maximum characters per segment (safe ceiling below Chatterbox's ~300 hard limit)."""


# ---------------------------------------------------------------------------
# NLTK bootstrap
# ---------------------------------------------------------------------------

def _ensure_nltk_data() -> None:
    """Download punkt_tab if not present. Called at module import time."""
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)
    # Also ensure legacy punkt is available as fallback
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)


_ensure_nltk_data()


# ---------------------------------------------------------------------------
# Dialogue detection patterns
# ---------------------------------------------------------------------------

# Straight double-quote:   "..."  or  "..."  (with content inside or just opening)
_STRAIGHT_DOUBLE_RE = re.compile(r'"')

# Curly double open quote: \u201c
_CURLY_DOUBLE_OPEN_RE = re.compile(r'\u201c')

# Curly double close quote: \u201d
_CURLY_DOUBLE_CLOSE_RE = re.compile(r'\u201d')

# Curly single open quote: \u2018
_CURLY_SINGLE_OPEN_RE = re.compile(r'\u2018')

# Curly single close quote: \u2019
_CURLY_SINGLE_CLOSE_RE = re.compile(r'\u2019')

# Scene break patterns for paragraph text
_SCENE_BREAK_TEXT_RE = re.compile(
    r"^\s*(?:"
    r"\*\s*\*\s*\*"   # * * * or ***
    r"|[-\u2014]{3,}" # --- or em-dash sequences
    r"|#{1,6}"        # # or ## etc (solo hash)
    r")\s*$"
)

# CSS classes that indicate a scene break element
_SCENE_BREAK_CLASSES = {"break", "separator", "divider"}

# Clause-boundary split pattern: comma, semicolon, em-dash (with surrounding space)
_CLAUSE_BOUNDARY_RE = re.compile(r'(?<=[,;\u2014])\s+|(?<=--)\s+')


# ---------------------------------------------------------------------------
# Core classification function
# ---------------------------------------------------------------------------

def classify_block(
    tag_name: str,
    text: str,
    attrs: dict,
    dialogue_open: bool,
) -> tuple[str, bool]:
    """Classify a single HTML block into a SegmentType.

    Args:
        tag_name: HTML tag (e.g. 'p', 'h1', 'hr', 'blockquote').
        text: Cleaned text content of the block.
        attrs: HTML attributes dict (e.g. {'class': ['separator']}).
        dialogue_open: Whether a multi-paragraph dialogue quote is currently open.

    Returns:
        Tuple of (segment_type_value, new_dialogue_open_state).
        segment_type_value is a SegmentType enum member.
    """
    # --- Headings: always chapter_heading, reset dialogue state ---
    if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        return SegmentType.CHAPTER_HEADING, False

    # --- HR tag: always scene_break, reset dialogue state ---
    if tag_name == "hr":
        return SegmentType.SCENE_BREAK, False

    # --- CSS class-based scene break ---
    css_classes = set(attrs.get("class", []))
    if css_classes & _SCENE_BREAK_CLASSES:
        return SegmentType.SCENE_BREAK, False

    stripped = text.strip()

    # --- Text-pattern scene break (asterisks, dashes) ---
    if _SCENE_BREAK_TEXT_RE.match(stripped):
        return SegmentType.SCENE_BREAK, False

    # --- blockquote: letters/notes → always dialogue ---
    if tag_name == "blockquote":
        # Determine if this closes any open-quote state
        new_open = _update_dialogue_state(stripped, dialogue_open)
        return SegmentType.DIALOGUE, new_open

    # --- Dialogue detection ---
    has_dialogue = _contains_dialogue_quote(stripped)

    if has_dialogue:
        new_open = _update_dialogue_state(stripped, dialogue_open)
        return SegmentType.DIALOGUE, new_open

    # --- Carry multi-paragraph dialogue state ---
    if dialogue_open:
        new_open = _update_dialogue_state(stripped, dialogue_open)
        return SegmentType.DIALOGUE, new_open

    # --- Default: narration ---
    return SegmentType.NARRATION, False


def _contains_dialogue_quote(text: str) -> bool:
    """Return True if text contains dialogue-indicating quotes.

    Conservative rule: any double quote (straight or curly) signals dialogue.
    Curly single quotes also signal dialogue. Plain apostrophes in contractions
    do NOT count — they are ASCII `'` (U+0027), not curly single open `'` (U+2018).
    """
    if not text:
        return False

    # Straight double quote
    if _STRAIGHT_DOUBLE_RE.search(text):
        return True

    # Curly double quote (open or close)
    if _CURLY_DOUBLE_OPEN_RE.search(text) or _CURLY_DOUBLE_CLOSE_RE.search(text):
        return True

    # Curly single quote (open or close — NOT plain apostrophe U+0027)
    if _CURLY_SINGLE_OPEN_RE.search(text) or _CURLY_SINGLE_CLOSE_RE.search(text):
        return True

    return False


def _update_dialogue_state(text: str, current_open: bool) -> bool:
    """Compute new dialogue_open state after processing this block's text.

    Rules:
    - If text has a curly open-quote (\u201c or \u2018) without matching close → open=True
    - If current open and text has a curly close-quote (\u201d or \u2019) → open=False
    - If text has both open and close curly quotes → open=False (balanced)
    - Straight quotes: count pairs; odd number → open=True
    """
    curly_double_opens = len(_CURLY_DOUBLE_OPEN_RE.findall(text))
    curly_double_closes = len(_CURLY_DOUBLE_CLOSE_RE.findall(text))
    curly_single_opens = len(_CURLY_SINGLE_OPEN_RE.findall(text))
    curly_single_closes = len(_CURLY_SINGLE_CLOSE_RE.findall(text))
    straight_quotes = len(_STRAIGHT_DOUBLE_RE.findall(text))

    # Check curly double quotes first (most common in ebooks)
    if curly_double_opens > 0 or curly_double_closes > 0:
        # More opens than closes → still open
        if curly_double_opens > curly_double_closes:
            return True
        # Close found (even if no explicit open in this block) → close the state
        if curly_double_closes > 0:
            return False
        return current_open

    # Check curly single quotes
    if curly_single_opens > 0 or curly_single_closes > 0:
        if curly_single_opens > curly_single_closes:
            return True
        if curly_single_closes > 0:
            return False
        return current_open

    # Straight double quotes: odd count → open
    if straight_quotes > 0:
        if straight_quotes % 2 == 1:
            return True
        return False

    # No quote markers in this block — preserve current state
    return current_open


# ---------------------------------------------------------------------------
# Sentence / segment splitting
# ---------------------------------------------------------------------------

def split_to_segments(text: str, segment_type: str) -> list[str]:
    """Split text into chunks of at most CHAR_LIMIT characters.

    Strategy:
    1. Use NLTK sent_tokenize to find sentence boundaries.
    2. Each sentence that fits within CHAR_LIMIT becomes one segment.
    3. Sentences exceeding CHAR_LIMIT are force-split at clause boundaries
       (comma, semicolon, em-dash). If no clause boundary found, split at
       nearest word boundary near midpoint.

    Args:
        text: The text to split (may contain multiple sentences).
        segment_type: SegmentType of the block (informational, not used for splitting logic).

    Returns:
        List of string segments, each <= CHAR_LIMIT characters.
    """
    if not text or not text.strip():
        return []

    # Tokenize into sentences using NLTK.
    # Per plan: "Split text at sentence boundaries — each sentence becomes its own segment".
    # "Dialogue lines from one speaker are kept as a single segment when they fit within the
    # limit" means individual sentences that fit are NOT further split (handled below).
    try:
        sentences = nltk.tokenize.sent_tokenize(text)
    except Exception:
        sentences = [text]

    segments: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= CHAR_LIMIT:
            segments.append(sentence)
        else:
            # Split the long sentence into sub-segments
            segments.extend(_split_long_sentence(sentence))

    return segments


def _split_long_sentence(text: str) -> list[str]:
    """Split a single sentence that exceeds CHAR_LIMIT.

    Tries clause boundaries first; falls back to word-boundary midpoint split.
    Recursively handles resulting chunks that are still too long.
    """
    if len(text) <= CHAR_LIMIT:
        return [text]

    # Try to find a clause boundary within the first CHAR_LIMIT characters
    # Search backwards from CHAR_LIMIT for a good split point
    split_pos = _find_clause_split(text, CHAR_LIMIT)

    if split_pos is None:
        # No clause boundary: split at word boundary near midpoint
        split_pos = _find_word_split(text, len(text) // 2)

    if split_pos is None or split_pos <= 0:
        # Last resort: hard split at CHAR_LIMIT (should be very rare)
        return [text[:CHAR_LIMIT], text[CHAR_LIMIT:]]

    left = text[:split_pos].strip()
    right = text[split_pos:].strip()

    result = []
    if left:
        result.extend(_split_long_sentence(left))
    if right:
        result.extend(_split_long_sentence(right))
    return result


def _find_clause_split(text: str, max_pos: int) -> int | None:
    """Find the rightmost clause boundary at or before max_pos.

    Clause boundaries: comma, semicolon, em-dash (followed by a space).
    Returns the position to split AT (i.e., include the boundary char in left part).
    """
    # Search in the window [max_pos-1 .. 0] for a boundary char + space
    search_region = text[:max_pos]

    # Find last occurrence of ", " or "; " or "\u2014 " or "-- "
    best_pos = None
    for pattern in [", ", "; ", "\u2014 ", "-- "]:
        idx = search_region.rfind(pattern)
        if idx != -1:
            # Split after the boundary char (i.e., include the comma/semicolon in left)
            candidate = idx + len(pattern) - 1  # position of the space
            if best_pos is None or candidate > best_pos:
                best_pos = candidate

    return best_pos


def _find_word_split(text: str, target_pos: int) -> int | None:
    """Find a word boundary near target_pos.

    Searches outward from target_pos for a space character.
    Returns the index of the space (caller should split at that index).
    """
    # Search in expanding radius around target_pos
    low = target_pos
    high = target_pos

    while low > 0 or high < len(text) - 1:
        # Try going left
        if low > 0:
            low -= 1
            if text[low] == " ":
                return low
        # Try going right (but must be before CHAR_LIMIT)
        if high < len(text) - 1 and high < CHAR_LIMIT:
            high += 1
            if text[high] == " ":
                return high

    return None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def process_chapter_blocks(
    blocks: list[tuple[str, str, dict]],
    chapter_num: int,
    chapter_title: str,
    start_id: int,
) -> list[Segment]:
    """Process a chapter's HTML blocks into typed, split Segment objects.

    Args:
        blocks: List of (tag_name, text, attrs) tuples from html_cleaner.
        chapter_num: 1-based chapter number.
        chapter_title: Extracted chapter heading (or empty string).
        start_id: Sequential ID for the first segment produced.

    Returns:
        List of Segment objects with sequential IDs, correct types, and
        text <= CHAR_LIMIT characters each.
    """
    segments: list[Segment] = []
    dialogue_open = False
    current_id = start_id

    for tag_name, text, attrs in blocks:
        seg_type, dialogue_open = classify_block(tag_name, text, attrs, dialogue_open)

        # Split text into sub-segments respecting the character limit
        sub_texts = split_to_segments(text, seg_type)

        # If no text (e.g. hr tag), still produce one segment for the structural marker
        if not sub_texts:
            sub_texts = [text.strip()]

        for sub_text in sub_texts:
            segment = Segment(
                id=current_id,
                chapter=chapter_num,
                chapter_title=chapter_title,
                type=seg_type,
                text=sub_text,
                char_count=len(sub_text),
            )
            segments.append(segment)
            current_id += 1

    # Reset dialogue state at chapter end (state is local, not returned)
    return segments
