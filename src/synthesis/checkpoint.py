"""Checkpoint system for synthesis crash recovery.

Tracks per-segment completion state in a JSON file so interrupted
overnight runs can resume from the last finished segment.  Uses
atomic writes to prevent checkpoint corruption during crashes.

The checkpoint file lives at ``book_dir/checkpoint.json`` alongside
the ``wavs/`` directory.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)

CHECKPOINT_FILENAME = "checkpoint.json"


# ---------------------------------------------------------------------------
# Create / save / load
# ---------------------------------------------------------------------------


def create_checkpoint(
    book_slug: str,
    total_segments: int,
    config: SynthesisConfig,
) -> dict:
    """Create a fresh checkpoint dict for a new synthesis run.

    Args:
        book_slug: Book identifier (from EPUB filename).
        total_segments: Total number of segments to synthesise.
        config: Synthesis configuration snapshot.

    Returns:
        Checkpoint dict ready for ``save_checkpoint()``.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "book_slug": book_slug,
        "started_at": now,
        "updated_at": now,
        "total_segments": total_segments,
        "completed": {},
        "failed": {},
        "config": {
            "narration_exaggeration": config.narration_exaggeration,
            "dialogue_exaggeration": config.dialogue_exaggeration,
            "cfg_weight": config.cfg_weight,
            "device": config.device,
            "model": "chatterbox-500m",
        },
    }


def save_checkpoint(checkpoint: dict, checkpoint_dir: Path) -> None:
    """Atomically save checkpoint to disk.

    Writes to a ``.tmp`` file first, then renames to prevent
    corruption if the process is killed mid-write.
    """
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    target = checkpoint_dir / CHECKPOINT_FILENAME
    tmp = target.with_suffix(".json.tmp")

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)

    os.rename(tmp, target)


def load_checkpoint(checkpoint_dir: Path) -> dict | None:
    """Load an existing checkpoint from disk, or return None."""
    target = checkpoint_dir / CHECKPOINT_FILENAME
    if not target.exists():
        return None

    with open(target, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Validation (resume)
# ---------------------------------------------------------------------------


def validate_checkpoint(
    checkpoint: dict,
    wavs_dir: Path,
    min_duration_s: float = 0.1,  # noqa: ARG001 — reserved for future use
) -> tuple[dict, list[str]]:
    """Validate that completed WAVs actually exist on disk.

    Removes entries whose WAV files are missing or empty and returns
    them as a re-queue list.  This implements the user decision:
    "delete the WAV file and re-run — checkpoint detects missing file
    and regenerates."

    Args:
        checkpoint: Loaded checkpoint dict (mutated in place).
        wavs_dir: Root directory for WAV files.
        min_duration_s: Reserved for future file-size-based checks.

    Returns:
        Tuple of (cleaned checkpoint, list of segment IDs to re-queue).
    """
    re_queue: list[str] = []
    to_remove: list[str] = []

    for seg_id, info in checkpoint.get("completed", {}).items():
        wav_path = Path(info["wav"])
        # If path is relative, resolve against wavs_dir's parent (book_dir)
        if not wav_path.is_absolute():
            wav_path = wavs_dir.parent / wav_path

        if not wav_path.exists() or wav_path.stat().st_size == 0:
            logger.info("Missing/empty WAV for segment %s — re-queuing", seg_id)
            to_remove.append(seg_id)
            re_queue.append(seg_id)

    for seg_id in to_remove:
        del checkpoint["completed"][seg_id]

    return checkpoint, re_queue


# ---------------------------------------------------------------------------
# Segment state updates
# ---------------------------------------------------------------------------


def mark_completed(
    checkpoint: dict,
    segment_id: int,
    wav_path: str,
    duration_s: float,
    took_s: float,
) -> None:
    """Record a segment as successfully synthesised."""
    key = str(segment_id)
    checkpoint["completed"][key] = {
        "wav": wav_path,
        "duration_s": round(duration_s, 3),
        "took_s": round(took_s, 3),
    }
    # Remove from failed if it was retried successfully
    checkpoint.get("failed", {}).pop(key, None)
    checkpoint["updated_at"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


def mark_failed(
    checkpoint: dict,
    segment_id: int,
    error: str,
    attempts: int,
) -> None:
    """Record a segment synthesis failure."""
    key = str(segment_id)
    checkpoint.setdefault("failed", {})[key] = {
        "error": error,
        "attempts": attempts,
    }
    checkpoint["updated_at"] = (
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Pending segments
# ---------------------------------------------------------------------------


def get_pending_segments(
    checkpoint: dict,
    all_segment_ids: list[int],
) -> list[int]:
    """Return segment IDs that still need synthesis.

    A segment is pending if it is neither completed nor has exhausted
    its retry budget in the failed dict.
    """
    completed = set(checkpoint.get("completed", {}).keys())
    pending: list[int] = []

    for seg_id in all_segment_ids:
        key = str(seg_id)
        if key in completed:
            continue
        pending.append(seg_id)

    return pending
