"""On-demand LibriTTS-R audio downloader.

Downloads only the speaker reference clips needed for a voice map,
avoiding the full 80GB+ dataset download.  Uses HuggingFace Parquet API
with predicate pushdown to fetch only rows matching needed speaker IDs,
falling back to streaming if the fast path fails.

Downloaded audio is cached at ``~/.local/share/libritts-r/audio/``
so subsequent runs skip already-downloaded speakers.
"""

from __future__ import annotations

import io
import json
import logging
import os
import tarfile
import wave
from collections import defaultdict
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


def _load_dotenv() -> None:
    """Load .env file from project root if HF_TOKEN not already set."""
    if os.environ.get("HF_TOKEN"):
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


# Default cache location for downloaded LibriTTS-R audio clips
LIBRITTS_R_CACHE = Path.home() / ".local" / "share" / "libritts-r" / "audio"

# LibriSpeech SPEAKERS.txt URL (maps speaker IDs to splits)
_SPEAKERS_TXT_URL = (
    "https://www.openslr.org/resources/12/raw-metadata.tar.gz"
)

# HuggingFace dataset config
_HF_DATASET = "mythicinfinity/libritts_r"

# Split name mapping: LibriSpeech names -> HF dataset split names
_SPLIT_TO_HF = {
    "dev-clean": "dev.clean",
    "dev-other": "dev.other",
    "test-clean": "test.clean",
    "test-other": "test.other",
    "train-clean-100": "train.clean.100",
    "train-clean-360": "train.clean.360",
    "train-other-500": "train.other.500",
}

# Target clip duration range (seconds)
_MIN_DURATION_S = 5.0
_TARGET_DURATION_S = 12.5
_MAX_DURATION_S = 25.0


def _load_speaker_splits() -> dict[str, str]:
    """Download and parse LibriSpeech SPEAKERS.txt.

    Returns:
        Dict mapping speaker_id -> split name (e.g. "train-clean-360").
    """
    logger.info("Downloading speaker-to-split mapping...")
    resp = httpx.get(_SPEAKERS_TXT_URL, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    mapping: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            if "SPEAKERS" in member.name:
                f = tar.extractfile(member)
                if f is None:
                    continue
                for raw_line in f:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or line.startswith(";"):
                        continue
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 3:
                        mapping[parts[0]] = parts[2]
                break

    logger.info("Loaded split mapping for %d speakers", len(mapping))
    return mapping


def _get_needed_speakers(voice_map_path: Path) -> set[str]:
    """Extract unique speaker IDs from a voice_map.json."""
    with open(voice_map_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ids: set[str] = set()
    if "narrator" in data:
        ids.add(str(data["narrator"]["speaker_id"]))
    for char in data.get("characters", []):
        ids.add(str(char["speaker_id"]))
    return ids


def _speaker_already_cached(speaker_id: str, cache_dir: Path) -> bool:
    """Check if a speaker already has cached audio files."""
    for item in cache_dir.iterdir() if cache_dir.exists() else []:
        if not item.is_dir():
            continue
        speaker_dir = item / speaker_id
        if speaker_dir.is_dir() and any(speaker_dir.rglob("*.wav")):
            return True
    return False


def _wav_duration_from_bytes(wav_bytes: bytes) -> float:
    """Estimate WAV duration from raw bytes."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / rate
    except Exception:
        pass
    # Fallback: assume 24kHz 16-bit mono
    return len(wav_bytes) / (24000 * 2)


def _pick_best_clip(
    best_clips: dict[str, tuple[float, bytes, str, str]],
    sid: str,
    wav_bytes: bytes,
    filename: str,
    transcript: str,
) -> None:
    """Update best_clips dict if this clip is a better candidate for sid."""
    duration = _wav_duration_from_bytes(wav_bytes)

    if duration < _MIN_DURATION_S or duration > _MAX_DURATION_S:
        # Outside ideal range — keep only if we have nothing for this speaker
        if sid not in best_clips:
            score = -abs(duration - _TARGET_DURATION_S)
            best_clips[sid] = (score, wav_bytes, filename, transcript)
        return

    score = 1.0 / (1.0 + abs(duration - _TARGET_DURATION_S))
    if sid not in best_clips or score > best_clips[sid][0]:
        best_clips[sid] = (score, wav_bytes, filename, transcript)


def _save_best_clips(
    best_clips: dict[str, tuple[float, bytes, str, str]],
    cache_dir: Path,
    split_name: str,
) -> set[str]:
    """Save best clips to disk and return set of saved speaker IDs."""
    saved: set[str] = set()
    for sid, (_, wav_bytes, filename, transcript) in best_clips.items():
        out_dir = cache_dir / split_name / sid
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename
        out_path.write_bytes(wav_bytes)
        if transcript:
            txt_path = out_path.with_suffix(".normalized.txt")
            txt_path.write_text(transcript, encoding="utf-8")
        saved.add(sid)
    return saved


def _download_speakers_parquet(
    hf_split: str,
    speaker_ids: set[str],
    cache_dir: Path,
    split_name: str,
) -> set[str]:
    """Fast speaker download using Parquet predicate pushdown.

    Fetches parquet file URLs from the HuggingFace API, then uses
    pyarrow to read only rows matching our speaker IDs.  This avoids
    scanning the entire dataset and is orders of magnitude faster
    than streaming for large splits like train-other-500.
    """
    import pyarrow.parquet as pq
    from fsspec.implementations.http import HTTPFileSystem

    from rich import print as rprint

    hf_token = os.environ.get("HF_TOKEN")
    headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}

    # Get parquet file URLs for this split
    api_url = (
        f"https://huggingface.co/api/datasets/"
        f"{_HF_DATASET}/parquet/all/{hf_split}"
    )
    resp = httpx.get(
        api_url, headers=headers, follow_redirects=True, timeout=30
    )
    resp.raise_for_status()
    parquet_urls = resp.json()

    if not isinstance(parquet_urls, list) or not parquet_urls:
        raise ValueError(f"Unexpected parquet API response: {parquet_urls!r}")

    logger.info(
        "Got %d parquet files for %s, filtering for %d speakers",
        len(parquet_urls), hf_split, len(speaker_ids),
    )

    # Build int filter set (speaker_id is int in the dataset)
    speaker_id_ints = [int(s) for s in speaker_ids]

    fs = HTTPFileSystem(headers=headers)
    best_clips: dict[str, tuple[float, bytes, str, str]] = {}

    for url in parquet_urls:
        try:
            pf = pq.ParquetFile(fs.open(url))
            table = pf.read(
                filters=[("speaker_id", "in", speaker_id_ints)],
                columns=["speaker_id", "audio", "text_normalized"],
            )
        except Exception as exc:
            logger.warning("Failed to read parquet file %s: %s", url, exc)
            continue

        for i in range(len(table)):
            sid = str(table.column("speaker_id")[i].as_py())
            audio_data = table.column("audio")[i].as_py()
            transcript = table.column("text_normalized")[i].as_py() or ""

            # Audio column is a struct {bytes: binary, path: string}
            if isinstance(audio_data, dict):
                wav_bytes = audio_data.get("bytes")
                filename = audio_data.get("path", f"{sid}_clip.wav")
            else:
                continue

            if not wav_bytes:
                continue

            _pick_best_clip(best_clips, sid, wav_bytes, filename, transcript)

    saved = _save_best_clips(best_clips, cache_dir, split_name)
    logger.info("Saved %d clips from %s via parquet", len(saved), hf_split)
    return saved


def _download_speakers_streaming(
    hf_split: str,
    speaker_ids: set[str],
    cache_dir: Path,
    split_name: str,
) -> set[str]:
    """Fallback: stream a HuggingFace dataset split row by row.

    Only used when the fast parquet path fails.
    """
    from datasets import Audio, load_dataset

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
    )

    ds = load_dataset(
        _HF_DATASET, "all", split=hf_split, streaming=True
    )
    ds = ds.cast_column("audio", Audio(decode=False))

    best_clips: dict[str, tuple[float, bytes, str, str]] = {}
    remaining = set(speaker_ids)
    rows_after_complete = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("speakers found"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(
            f"Scanning {split_name}", total=len(speaker_ids)
        )
        found_count = 0

        for row in ds:
            sid = row["speaker_id"]

            if sid not in speaker_ids:
                # Once all found, count rows to allow finding better clips
                if not remaining:
                    rows_after_complete += 1
                    if rows_after_complete > 100:
                        break
                continue

            audio = row["audio"]
            wav_bytes = audio.get("bytes")
            if not wav_bytes:
                continue

            filename = audio.get("path", f"{sid}_clip.wav")
            transcript = row.get("text_normalized", "")

            was_new = sid in remaining
            _pick_best_clip(best_clips, sid, wav_bytes, filename, transcript)

            if was_new and sid in best_clips:
                remaining.discard(sid)
                found_count += 1
                progress.update(task, completed=found_count)

            if not remaining:
                rows_after_complete += 1
                if rows_after_complete > 100:
                    break

    saved = _save_best_clips(best_clips, cache_dir, split_name)
    logger.info("Saved %d clips from %s via streaming", len(saved), hf_split)
    return saved


def _download_speakers_from_hf_split(
    hf_split: str,
    speaker_ids: set[str],
    cache_dir: Path,
    split_name: str,
) -> set[str]:
    """Download clips for needed speakers from a HuggingFace dataset split.

    Tries the fast parquet predicate-pushdown approach first, falling
    back to row-by-row streaming if that fails.
    """
    from rich import print as rprint

    try:
        return _download_speakers_parquet(
            hf_split, speaker_ids, cache_dir, split_name,
        )
    except Exception as exc:
        logger.warning(
            "Fast parquet download failed for %s, falling back to streaming: %s",
            hf_split, exc,
        )
        rprint(
            f"  [yellow]Parquet fast-path failed ({exc}), "
            f"falling back to streaming...[/yellow]"
        )
        return _download_speakers_streaming(
            hf_split, speaker_ids, cache_dir, split_name,
        )


def download_voice_clips(
    voice_map_path: Path,
    cache_dir: Path | None = None,
) -> Path:
    """Download LibriTTS-R audio clips for all speakers in a voice map.

    Only downloads speakers not already cached.  Streams the HuggingFace
    dataset filtering by speaker ID to download the minimum data needed.

    Args:
        voice_map_path: Path to voice_map.json.
        cache_dir: Where to cache audio.  Defaults to
            ``~/.local/share/libritts-r/audio/``.

    Returns:
        Path to the audio cache directory (usable as ``libritts_audio_dir``).
    """
    from rich import print as rprint

    _load_dotenv()

    if cache_dir is None:
        cache_dir = LIBRITTS_R_CACHE
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Get needed speaker IDs
    needed = _get_needed_speakers(voice_map_path)
    logger.info("Voice map has %d unique speakers", len(needed))

    # Filter out already-cached speakers
    to_download = {
        sid for sid in needed if not _speaker_already_cached(sid, cache_dir)
    }

    if not to_download:
        rprint(
            f"[green]All {len(needed)} speaker clips already cached[/green]"
        )
        # Still update voice_map clip paths if needed
        _update_voice_map_clips(voice_map_path, cache_dir)
        return cache_dir

    rprint(
        f"Downloading reference clips for "
        f"[bold]{len(to_download)}[/bold] speakers "
        f"({len(needed) - len(to_download)} already cached)"
    )

    # Map speakers to splits using LibriSpeech SPEAKERS.txt
    speaker_splits = _load_speaker_splits()
    splits_needed: dict[str, set[str]] = defaultdict(set)
    unmapped: set[str] = set()

    for sid in to_download:
        split = speaker_splits.get(sid)
        if split:
            splits_needed[split].add(sid)
        else:
            unmapped.add(sid)
            logger.warning("Speaker %s not found in SPEAKERS.txt", sid)

    if unmapped:
        rprint(
            f"[yellow]Warning: {len(unmapped)} speakers not found "
            f"in LibriSpeech mapping[/yellow]"
        )

    # Process each split
    total_downloaded: set[str] = set()
    for split, speakers in splits_needed.items():
        hf_split = _SPLIT_TO_HF.get(split)
        if not hf_split:
            logger.warning("No HF split mapping for %s", split)
            continue

        rprint(
            f"  [cyan]{split}[/cyan]: "
            f"[bold]{len(speakers)}[/bold] speakers..."
        )
        downloaded = _download_speakers_from_hf_split(
            hf_split, speakers, cache_dir, split,
        )
        total_downloaded |= downloaded

    rprint(
        f"[green]Downloaded reference clips for "
        f"{len(total_downloaded)}/{len(to_download)} speakers[/green]"
    )

    still_missing = to_download - total_downloaded - unmapped
    if still_missing:
        rprint(
            f"[yellow]Warning: {len(still_missing)} speakers not found "
            f"in dataset: {still_missing}[/yellow]"
        )

    # Update voice_map.json with real clip paths
    _update_voice_map_clips(voice_map_path, cache_dir)

    return cache_dir


def _update_voice_map_clips(
    voice_map_path: Path, audio_dir: Path
) -> None:
    """Update voice_map.json to replace placeholder clip paths with real ones.

    Uses the same clip selection logic as the matching orchestrator.
    """
    from src.matching.clip_selector import select_reference_clip_with_transcript

    with open(voice_map_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0

    # Update narrator
    narrator = data.get("narrator", {})
    clip_path = narrator.get("clip_path", "")
    if clip_path.startswith("AUDIO_DIR/") or not clip_path:
        clip, transcript = select_reference_clip_with_transcript(
            narrator["speaker_id"], audio_dir
        )
        if clip:
            narrator["clip_path"] = clip
            if transcript:
                narrator["transcript"] = transcript
            updated += 1

    # Update characters
    for char in data.get("characters", []):
        clip_path = char.get("clip_path", "")
        if clip_path.startswith("AUDIO_DIR/") or not clip_path:
            clip, transcript = select_reference_clip_with_transcript(
                char["speaker_id"], audio_dir
            )
            if clip:
                char["clip_path"] = clip
                if transcript:
                    char["transcript"] = transcript
                updated += 1

    with open(voice_map_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    if updated:
        from rich import print as rprint
        rprint(f"  Updated [bold]{updated}[/bold] clip paths in voice_map.json")

    logger.info("Updated %d clip paths in voice_map.json", updated)


def clean_voice_cache(cache_dir: Path | None = None) -> None:
    """Delete all cached LibriTTS-R voice reference clips.

    Args:
        cache_dir: Cache directory to clean. Defaults to
            ``~/.local/share/libritts-r/audio/``.
    """
    import shutil

    from rich import print as rprint

    if cache_dir is None:
        cache_dir = LIBRITTS_R_CACHE

    if not cache_dir.exists():
        rprint("[yellow]No voice cache to clean[/yellow]")
        return

    # Count what we're deleting
    wav_count = len(list(cache_dir.rglob("*.wav")))
    total_bytes = sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
    size_mb = total_bytes / (1024 * 1024)

    shutil.rmtree(cache_dir)
    rprint(
        f"[green]Cleaned voice cache:[/green] "
        f"{wav_count} clips ({size_mb:.1f}MB) removed from {cache_dir}"
    )
