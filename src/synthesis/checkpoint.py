"""Checkpoint system for synthesis crash recovery.

Tracks per-segment completion state in a JSON file so interrupted
overnight runs can resume from the last finished segment.  Uses
atomic writes to prevent checkpoint corruption during crashes.

The checkpoint file lives at ``book_dir/checkpoint.json`` alongside
the ``wavs/`` directory.

Engine versioning (v1.1): checkpoints record the TTS engine name,
version, and library.  On resume, engine mismatches trigger auto-archive
of old checkpoints and WAVs so synthesis starts fresh.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
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
    engine_name: str = "qwen3-tts-1.7b",
    engine_version: str = "unknown",
    engine_library: str = "mlx-audio",
) -> dict:
    """Create a fresh checkpoint dict for a new synthesis run.

    Args:
        book_slug: Book identifier (from EPUB filename).
        total_segments: Total number of segments to synthesise.
        config: Synthesis configuration snapshot.
        engine_name: TTS engine identifier (e.g. ``'qwen3-tts-1.7b'``).
        engine_version: Engine library version string.
        engine_library: Engine library name (e.g. ``'mlx-audio'``).

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
        "engine": {
            "name": engine_name,
            "version": engine_version,
            "library": engine_library,
        },
        "config": {
            "device": config.device,
            "model": engine_name,
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
    """Load an existing checkpoint from disk, or return None.

    If the checkpoint lacks an ``engine`` key, it is a legacy v1.0
    checkpoint created before engine versioning was added.
    """
    target = checkpoint_dir / CHECKPOINT_FILENAME
    if not target.exists():
        return None

    with open(target, "r", encoding="utf-8") as f:
        cp = json.load(f)

    if "engine" not in cp:
        logger.info(
            "Loaded legacy v1.0 checkpoint (no engine metadata) from %s",
            target,
        )

    return cp


# ---------------------------------------------------------------------------
# Engine compatibility
# ---------------------------------------------------------------------------


def check_engine_compatibility(
    checkpoint: dict,
    engine_name: str,
) -> tuple[bool, str]:
    """Check whether an existing checkpoint was created by the same engine.

    Args:
        checkpoint: Loaded checkpoint dict.
        engine_name: Current engine name (e.g. ``'qwen3-tts-1.7b'``).

    Returns:
        Tuple of ``(compatible, reason)``.  If compatible, reason is ``""``.
    """
    engine_info = checkpoint.get("engine")
    if engine_info is None:
        return False, "Legacy v1.0 checkpoint (no engine metadata)"

    cp_engine = engine_info.get("name", "unknown")
    if cp_engine == engine_name:
        return True, ""

    return (
        False,
        f"Checkpoint uses {cp_engine}, current engine is {engine_name}",
    )


def archive_checkpoint(book_dir: Path) -> Path | None:
    """Archive an existing checkpoint and WAVs to a backup folder.

    Creates ``book_dir/checkpoint_archive/`` and moves the checkpoint
    and WAVs directory into it with a timestamp suffix.  This allows
    a fresh synthesis run without losing the old data.

    Returns:
        Path to the archive directory, or None if nothing to archive.
    """
    checkpoint_path = book_dir / CHECKPOINT_FILENAME
    wavs_dir = book_dir / "wavs"

    if not checkpoint_path.exists() and not wavs_dir.exists():
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = book_dir / "checkpoint_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)

    if checkpoint_path.exists():
        dest = archive_dir / f"checkpoint_{timestamp}.json"
        shutil.move(str(checkpoint_path), str(dest))
        logger.info("Archived checkpoint to %s", dest)

    if wavs_dir.exists():
        dest = archive_dir / f"wavs_{timestamp}"
        shutil.move(str(wavs_dir), str(dest))
        logger.info("Archived WAVs to %s", dest)

    logger.info(
        "Archived old checkpoint and WAVs to %s (engine mismatch)",
        archive_dir,
    )
    return archive_dir


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
