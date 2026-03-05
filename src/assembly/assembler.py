"""Assembly orchestrator: WAV segments -> chapter MP3s + audiobook.mp3.

Coordinates the full assembly pipeline:
1. Validate inputs (wavs/, voice_map.json, attributed.json)
2. Extract EPUB metadata (title, author, cover)
3. Generate chapter announcement WAVs via Qwen3-TTS
4. Per-chapter: concatenate -> effects chain -> normalize LUFS -> export MP3 -> tag ID3
5. Combine chapter MP3s -> tag with CHAP/CTOC chapter markers

Phase 9 upgrade: pedalboard effects chain, descriptive file naming,
ACX-compliant export (44.1kHz 192kbps CBR).
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from rich import print as rprint

from src.assembly.models import AssemblyConfig, AssemblyStats, ChapterInfo

logger = logging.getLogger(__name__)


def _slugify_title(title: str, ch_num: int) -> str:
    """Produce a clean filename slug from a chapter title.

    Lowercase, replace spaces with hyphens, strip non-alphanumeric
    (except hyphens), prefix with zero-padded chapter number.

    Args:
        title: Chapter title string.
        ch_num: 1-based chapter number.

    Returns:
        Slug like "01-the-dark-forest" or "03-chapter-3" if title is empty.

    Examples:
        >>> _slugify_title("The Journey", 1)
        '01-the-journey'
        >>> _slugify_title("", 1)
        '01-chapter-1'
        >>> _slugify_title("Chapter 3: The Quest!", 3)
        '03-chapter-3-the-quest'
    """
    if not title or not title.strip():
        return f"{ch_num:02d}-chapter-{ch_num}"

    slug = title.lower().strip()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")

    if not slug:
        return f"{ch_num:02d}-chapter-{ch_num}"

    return f"{ch_num:02d}-{slug}"


def run_assembly(
    book_dir: Path,
    epub_path: Path | None = None,
    title_override: str | None = None,
    author_override: str | None = None,
    cover_override: Path | None = None,
    device: str = "auto",
    output_dir: Path | None = None,
) -> AssemblyStats:
    """Run the full audio assembly pipeline.

    Args:
        book_dir: Book output directory containing wavs/, voice_map.json,
            and attributed.json.
        epub_path: Optional source EPUB for metadata extraction.
        title_override: Override book title for ID3 tags.
        author_override: Override author for ID3 tags.
        cover_override: Override cover art image path (JPEG/PNG).
        device: Device for TTS announcement generation ('auto', 'mps', 'cpu').
        output_dir: If provided, use for MP3 output instead of book_dir.

    Returns:
        AssemblyStats with totals.

    Raises:
        FileNotFoundError: If required inputs are missing.
        RuntimeError: If FFmpeg is not available.
    """
    from src.assembly.announcer import generate_announcements
    from src.assembly.concatenator import assemble_chapter
    from src.assembly.effects import apply_effects_chain, create_mastering_chain
    from src.assembly.encoder import (
        check_ffmpeg,
        combine_chapter_mp3s,
        export_chapter_mp3,
    )
    from src.assembly.normalizer import normalize_audio
    from src.assembly.tagger import tag_audiobook, tag_chapter
    from src.matching.models import VoiceMap

    config = AssemblyConfig()
    stats = AssemblyStats()

    # Determine output location
    out_dir = output_dir if output_dir is not None else book_dir
    if output_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Validate inputs
    # ------------------------------------------------------------------
    wavs_dir = book_dir / "wavs"
    voice_map_path = book_dir / "voice_map.json"
    attributed_path = book_dir / "attributed.json"

    if not wavs_dir.exists() or not any(wavs_dir.glob("ch*/*.wav")):
        raise FileNotFoundError(
            f"No WAV files found in {wavs_dir}. Run 'synthesize' first."
        )
    if not voice_map_path.exists():
        raise FileNotFoundError(
            f"voice_map.json not found in {book_dir}. Run 'match' first."
        )
    if not attributed_path.exists():
        raise FileNotFoundError(
            f"attributed.json not found in {book_dir}. Run 'attribute' first."
        )

    # ------------------------------------------------------------------
    # 2. Check FFmpeg
    # ------------------------------------------------------------------
    check_ffmpeg()

    # ------------------------------------------------------------------
    # 3. Load data
    # ------------------------------------------------------------------
    with open(voice_map_path, "r", encoding="utf-8") as f:
        voice_map = VoiceMap.model_validate_json(f.read())

    with open(attributed_path, "r", encoding="utf-8") as f:
        attributed_segments: list[dict] = json.load(f)

    # Group segments by chapter
    chapters_map: dict[int, list[dict]] = defaultdict(list)
    for seg in attributed_segments:
        chapters_map[seg.get("chapter", 0)].append(seg)

    # Build chapters list with titles
    chapters_list: list[dict] = []
    for ch_num in sorted(chapters_map.keys()):
        segs = chapters_map[ch_num]
        # Find chapter title from first chapter_heading segment
        ch_title = ""
        for s in segs:
            if s.get("type") == "chapter_heading" and s.get("text", "").strip():
                ch_title = s["text"].strip()
                break
        chapters_list.append({"chapter_num": ch_num, "title": ch_title})

    total_chapters = len(chapters_list)
    stats.total_chapters = total_chapters
    stats.total_segments = len(attributed_segments)

    # ------------------------------------------------------------------
    # 4. Extract EPUB metadata
    # ------------------------------------------------------------------
    title = title_override or "Unknown Title"
    author = author_override or "Unknown Author"
    cover_data: bytes | None = None
    cover_mime: str | None = None

    if epub_path is not None and epub_path.exists():
        from src.assembly.metadata import extract_epub_metadata

        meta = extract_epub_metadata(epub_path)
        title = title_override or meta.title
        author = author_override or meta.author
        cover_data = meta.cover_data
        cover_mime = meta.cover_mime
        rprint(f"  EPUB metadata: [cyan]{title}[/cyan] by [cyan]{author}[/cyan]")

    # Cover override from CLI flag
    if cover_override is not None and cover_override.exists():
        cover_data = cover_override.read_bytes()
        suffix = cover_override.suffix.lower()
        cover_mime = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
        }.get(suffix, "image/jpeg")
        rprint(f"  Cover override: [cyan]{cover_override}[/cyan]")

    # ------------------------------------------------------------------
    # 5. Generate chapter announcements
    # ------------------------------------------------------------------
    narrator_clip = Path(voice_map.narrator.clip_path)
    rprint("[bold cyan]Generating chapter announcements...[/bold cyan]")

    announcements = generate_announcements(
        chapters_list,
        narrator_clip,
        book_dir / "announcements",
        device=device,
    )
    stats.announcements_generated = len(announcements)
    rprint(f"  Announcements: [cyan]{len(announcements)}[/cyan] generated")

    # ------------------------------------------------------------------
    # 6. Create mastering effects chain (once, reused for all chapters)
    # ------------------------------------------------------------------
    board = create_mastering_chain()
    rprint("[bold cyan]Effects chain: NoiseGate -> Compressor -> HighPass(80Hz) -> Limiter(-3dB)[/bold cyan]")

    # ------------------------------------------------------------------
    # 7. Process each chapter (memory-bounded)
    # ------------------------------------------------------------------
    chapters_dir = out_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    chapter_infos: list[ChapterInfo] = []
    chapter_mp3_paths: list[Path] = []

    rprint("[bold cyan]Assembling chapters...[/bold cyan]")

    for idx, ch_data in enumerate(chapters_list):
        ch_num = ch_data["chapter_num"]
        ch_title = ch_data["title"]
        segs = chapters_map[ch_num]

        # Collect WAV paths for this chapter's segments
        segment_wavs: list[tuple[dict, Path]] = []
        for seg in segs:
            seg_id = seg.get("id", 0)
            ch_num_for_path = seg.get("chapter", 0)
            wav_path = wavs_dir / f"ch{ch_num_for_path:02d}" / f"seg_{seg_id:04d}.wav"
            if wav_path.exists():
                segment_wavs.append((seg, wav_path))
            else:
                logger.warning("Missing WAV: %s — skipping segment %d", wav_path, seg_id)

        if not segment_wavs:
            logger.warning("Chapter %d has no WAV files — skipping", ch_num)
            continue

        # Get announcement WAV for this chapter
        announce_wav = announcements.get(ch_num)

        # Concatenate
        chapter_audio = assemble_chapter(segment_wavs, config, announce_wav)

        # Apply effects chain (between concatenation and normalization)
        chapter_audio, effects_metrics = apply_effects_chain(chapter_audio, board)
        logger.info(
            "Ch %d effects: before LUFS=%.1f peak=%.1fdB, after LUFS=%.1f peak=%.1fdB",
            ch_num,
            effects_metrics["before_lufs"],
            effects_metrics["before_peak_db"],
            effects_metrics["after_lufs"],
            effects_metrics["after_peak_db"],
        )

        # Normalize
        chapter_audio = normalize_audio(chapter_audio, config.target_lufs)

        # Export MP3 with descriptive filename
        display_title = ch_title if ch_title else f"Chapter {ch_num}"
        slug = _slugify_title(ch_title, ch_num)
        mp3_path = chapters_dir / f"{slug}.mp3"
        export_chapter_mp3(
            chapter_audio, mp3_path,
            config.mp3_bitrate, config.export_sample_rate,
        )

        # Tag chapter MP3
        tag_chapter(
            mp3_path,
            title=title,
            author=author,
            chapter_title=display_title,
            track_number=idx + 1,
            total_tracks=total_chapters,
            cover_data=cover_data,
            cover_mime=cover_mime,
        )

        duration_ms = len(chapter_audio)
        chapter_infos.append(
            ChapterInfo(
                chapter_num=ch_num,
                title=display_title,
                start_ms=0,  # Will be calculated below
                end_ms=0,
                segment_count=len(segment_wavs),
                duration_ms=duration_ms,
                mp3_path=str(mp3_path),
            )
        )
        chapter_mp3_paths.append(mp3_path)
        stats.chapter_mp3s_created += 1
        stats.total_duration_ms += duration_ms

        # Progress
        _fmt_dur = _format_duration(duration_ms / 1000)
        rprint(
            f"  Chapter {ch_num}/{total_chapters}: "
            f"[cyan]{display_title}[/cyan] ({_fmt_dur})"
        )

    # ------------------------------------------------------------------
    # 8. Calculate chapter offsets for CHAP frames
    # ------------------------------------------------------------------
    cumulative_ms = 0
    for info in chapter_infos:
        info.start_ms = cumulative_ms
        cumulative_ms += info.duration_ms
        info.end_ms = cumulative_ms

    # ------------------------------------------------------------------
    # 9. Combine into audiobook.mp3
    # ------------------------------------------------------------------
    rprint("[bold cyan]Combining into audiobook.mp3...[/bold cyan]")

    audiobook_path = out_dir / "audiobook.mp3"
    combine_chapter_mp3s(
        chapter_mp3_paths, audiobook_path,
        config.mp3_bitrate, config.export_sample_rate,
    )

    # Tag combined audiobook with chapter markers
    tag_audiobook(
        audiobook_path,
        title=title,
        author=author,
        chapters=chapter_infos,
        cover_data=cover_data,
        cover_mime=cover_mime,
    )
    stats.audiobook_created = True

    return stats


def _format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"
