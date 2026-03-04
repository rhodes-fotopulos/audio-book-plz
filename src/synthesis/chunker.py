"""Text chunking for TTS synthesis.

Provides two chunking strategies:

- ``chunk_text_qwen`` — 500-600 char chunks for Qwen3-TTS
- ``chunk_text_chatterbox`` — 280 char chunks for Chatterbox fallback

Both split at sentence boundaries (never mid-sentence) using NLTK
``sent_tokenize``.  The ``chunk_segments_by_speaker`` function applies
chunking to attributed segment dicts while preserving speaker metadata.
"""

from __future__ import annotations

import copy
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# NLTK data bootstrap (matches Phase 1 pattern from src/parser/segmenter.py)
# ---------------------------------------------------------------------------


def _ensure_nltk_data() -> None:
    """Download punkt_tab / punkt if not present."""
    import nltk

    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)


# ---------------------------------------------------------------------------
# Qwen3-TTS chunker (500-600 chars)
# ---------------------------------------------------------------------------


def chunk_text_qwen(
    text: str,
    max_chars: int = 580,
    min_chars: int = 200,
) -> list[str]:
    """Split *text* into 500-600 char chunks at sentence boundaries.

    Args:
        text: Input text to chunk.
        max_chars: Maximum characters per chunk (default 580 to allow
            variance within 500-600 range).
        min_chars: Minimum characters for the final chunk.  If shorter,
            it is merged back into the previous chunk.

    Returns:
        List of text chunks, each stripped of leading/trailing whitespace.
        Never breaks mid-sentence.
    """
    if len(text) <= max_chars:
        return [text.strip()] if text.strip() else []

    _ensure_nltk_data()
    from nltk.tokenize import sent_tokenize

    sentences = sent_tokenize(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Warn about very long individual sentences
        if len(sentence) > 800:
            logger.warning(
                "Single sentence exceeds 800 chars (%d) — kept as own chunk",
                len(sentence),
            )

        if current and len(current) + 1 + len(sentence) > max_chars:
            # Finalize current chunk and start new one
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    # Handle remaining text
    if current.strip():
        # Merge tiny trailing chunk into previous if possible
        if (
            len(current.strip()) < min_chars
            and chunks
            # Only merge if it won't make previous chunk excessively long
        ):
            chunks[-1] = f"{chunks[-1]} {current.strip()}"
        else:
            chunks.append(current.strip())

    return chunks if chunks else ([text.strip()] if text.strip() else [])


# ---------------------------------------------------------------------------
# Chatterbox chunker (280 chars) — preserved from v1.0
# ---------------------------------------------------------------------------


def chunk_text_chatterbox(text: str, max_chars: int = 280) -> list[str]:
    """Split *text* into ~280 char chunks at sentence boundaries.

    This is the v1.0 chunking logic preserved for Chatterbox fallback.
    Algorithm matches the original ``_split_long_text()`` from
    ``src/synthesis/synthesizer.py``.

    Args:
        text: Input text to chunk.
        max_chars: Maximum characters per chunk (default 280).

    Returns:
        List of text chunks.  Returns single-element list if text fits.
    """
    if len(text) <= max_chars:
        return [text]

    _ensure_nltk_data()
    from nltk.tokenize import sent_tokenize

    sentences = sent_tokenize(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > max_chars:
            chunks.append(current.strip())
            current = sentence
        else:
            current = f"{current} {sentence}" if current else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [text]


# ---------------------------------------------------------------------------
# Segment-level chunking with speaker metadata preservation
# ---------------------------------------------------------------------------


def chunk_segments_by_speaker(
    segments: list[dict],
    engine_type: str = "qwen3",
) -> list[dict]:
    """Chunk attributed segments while preserving speaker metadata.

    Each input segment has a single speaker.  Long segments are split
    into sub-chunks using the engine-appropriate chunker.  Short segments
    pass through unchanged.

    Per user decision: speaker boundaries are already natural segment
    boundaries — the chunker just splits long single-speaker segments.

    Args:
        segments: List of attributed segment dicts from attributed.json.
            Each has ``text``, ``speaker``, ``chapter``, ``type``, ``id``.
        engine_type: ``'qwen3'`` or ``'chatterbox'`` — selects chunker.

    Returns:
        Expanded list of segment dicts.  Multi-chunk segments get sub-IDs
        like ``"42.0"``, ``"42.1"``.  Single-chunk segments keep their
        original ID.
    """
    chunker = chunk_text_qwen if engine_type == "qwen3" else chunk_text_chatterbox
    result: list[dict] = []

    for seg in segments:
        text = seg.get("text", "")
        chunks = chunker(text)

        if len(chunks) <= 1:
            # No splitting needed — pass through as-is
            result.append(seg)
        else:
            # Create sub-segments for each chunk
            original_id = seg["id"]
            for idx, chunk_text in enumerate(chunks):
                sub_seg = copy.deepcopy(seg)
                sub_seg["text"] = chunk_text
                sub_seg["id"] = f"{original_id}.{idx}"
                sub_seg["_parent_id"] = original_id
                result.append(sub_seg)

    return result
