"""Pipeline orchestrator for audio-book-plz.

Coordinates the multi-phase conversion pipeline:
  Phase 1 - Parse:      EPUB -> segments.json
  Phase 2 - Attribute:  segments.json -> characters.json + attributed.json
  Phase 3 - Match:      attributed segments -> voice_map.json
  Phase 4 - Synthesize: segments -> WAV audio files via Chatterbox TTS
  Phase 5 - Assemble:   WAV segments -> chapter MP3s + audiobook.mp3
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

import typer
from rich import print as rprint
from rich.progress import track
from rich.table import Table

from src.attribution import (
    attribute_all_segments,
    extract_all_characters,
    merge_characters,
    preload_model,
    unload_model,
)
from src.attribution.emotion import annotate_scene_moods, detect_overrides
from src.attribution.attributor import CONFIDENCE_FLAG_THRESHOLD
from src.matching.models import VoiceMap
from src.matching.orchestrator import run_matching
from src.parser.epub_reader import get_story_chapters, load_epub
from src.parser.html_cleaner import chapter_to_text_blocks
from src.parser.segmenter import process_chapter_blocks
from src.synthesis.models import SynthesisConfig

logger = logging.getLogger(__name__)


def _make_book_slug(epub_path: Path) -> str:
    """Derive a filesystem-safe slug from an EPUB filename.

    Lowercases the stem, replaces spaces and underscores with hyphens, and
    strips characters that are not alphanumeric or hyphens.

    Examples:
        "The Name of the Wind.epub" -> "the-name-of-the-wind"
        "my_book (2024).epub"       -> "my-book-2024"
    """
    slug = epub_path.stem.lower()
    slug = slug.replace(" ", "-").replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    # Collapse multiple consecutive hyphens into one
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug or "book"


def run_parse(epub_path: Path, output_dir: Path) -> Path:
    """End-to-end parse phase: EPUB -> segments.json.

    Loads the EPUB, iterates story chapters in reading order, processes each
    chapter through the full parsing stack (html_cleaner -> segmenter), and
    writes the result to output_dir/{book-slug}/segments.json.

    Shows a Rich progress bar per chapter during processing and prints a
    coloured summary on completion.

    Args:
        epub_path: Path to the source EPUB file.
        output_dir: Root output directory (segments.json lands in a sub-dir).

    Returns:
        Path to the written segments.json file.
    """
    book = load_epub(str(epub_path))
    chapters = get_story_chapters(book)

    all_segments = []
    start_id = 0

    for chapter_num, chapter in enumerate(
        track(chapters, description="Parsing chapters..."), start=1
    ):
        blocks = chapter_to_text_blocks(chapter)

        # Extract chapter title from first heading block
        chapter_title = ""
        for tag_name, text, _attrs in blocks:
            if tag_name in ("h1", "h2", "h3") and text.strip():
                chapter_title = text.strip()
                break

        segments = process_chapter_blocks(blocks, chapter_num, chapter_title, start_id)
        all_segments.extend(segments)
        start_id += len(segments)

    # Write output
    book_slug = _make_book_slug(epub_path)
    output_book_dir = output_dir / book_slug
    output_book_dir.mkdir(parents=True, exist_ok=True)
    segments_path = output_book_dir / "segments.json"

    with open(segments_path, "w", encoding="utf-8") as f:
        json.dump(
            [dataclasses.asdict(s) for s in all_segments],
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Print coloured summary
    dialogue_count = sum(1 for s in all_segments if s.type == "dialogue")
    rprint(
        f"\n[bold green]Parse complete[/bold green]\n"
        f"  Chapters   : [cyan]{len(chapters)}[/cyan]\n"
        f"  Segments   : [cyan]{len(all_segments)}[/cyan]\n"
        f"  Dialogue   : [cyan]{dialogue_count}[/cyan]\n"
        f"  Output     : [cyan]{segments_path}[/cyan]"
    )

    return segments_path


def run_attribute(
    book_dir: Path,
    model_override: str | None = None,
) -> tuple[Path, Path]:
    """End-to-end attribution phase: segments.json -> characters.json + attributed.json.

    Runs the three-stage attribution pipeline:
    1. Extract characters from each chapter via LLM
    2. Merge character profiles (alias deduplication)
    3. Attribute a speaker to every segment

    Writes characters.json and attributed.json to book_dir, prints a
    coloured stats summary on completion, and unloads the Ollama model
    to free memory.

    Args:
        book_dir: Book output directory containing segments.json.
        model_override: If set, force this Ollama model (e.g., ``'qwen3:14b'``).
            Otherwise auto-selects based on available RAM.

    Returns:
        Tuple of (characters_path, attributed_path).
    """
    # Load segments
    segments_path = book_dir / "segments.json"
    with open(segments_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    cache_dir = book_dir / ".cache"

    # --- Preload LLM model (stays resident through extraction + merge + attribution) ---
    model_name = preload_model(model_override)
    rprint(f"[bold cyan]Using LLM: {model_name}[/bold cyan]")

    # --- Extraction pass ---
    rprint("[bold cyan]Extracting characters...[/bold cyan]")
    chapter_characters = extract_all_characters(segments, cache_dir)

    # --- Merge pass ---
    rprint("[bold cyan]Merging character profiles...[/bold cyan]")
    characters = merge_characters(chapter_characters, cache_dir)

    # --- Write characters.json ---
    characters_path = book_dir / "characters.json"
    with open(characters_path, "w", encoding="utf-8") as f:
        json.dump(
            [profile.model_dump() for profile in characters],
            f,
            indent=2,
            ensure_ascii=False,
        )

    # --- Attribution pass ---
    rprint("[bold cyan]Attributing speakers...[/bold cyan]")
    attributed_segments = attribute_all_segments(
        segments, characters, cache_dir
    )

    # --- Write attributed.json ---
    attributed_path = book_dir / "attributed.json"
    with open(attributed_path, "w", encoding="utf-8") as f:
        json.dump(attributed_segments, f, indent=2, ensure_ascii=False)

    # --- Emotion annotation ---
    rprint("[bold cyan]Annotating scene moods and emotions...[/bold cyan]")
    chapters_for_emotion: dict[int, list[dict]] = defaultdict(list)
    for seg in attributed_segments:
        chapters_for_emotion[seg["chapter"]].append(seg)

    chapter_emotions: dict[int, tuple[list, list]] = {}
    total_scenes = 0
    total_overrides = 0

    for ch_num in sorted(chapters_for_emotion.keys()):
        ch_segs = chapters_for_emotion[ch_num]
        scene_moods = annotate_scene_moods(ch_segs, ch_num)
        overrides = detect_overrides(ch_segs, scene_moods)
        chapter_emotions[ch_num] = (scene_moods, overrides)
        total_scenes += len(scene_moods)
        total_overrides += len(overrides)

    # Write emotion.json
    emotion_data = {
        "chapters": {
            str(ch_num): {
                "scenes": [s.model_dump() for s in scene_moods],
                "overrides": [o.model_dump() for o in overrides],
            }
            for ch_num, (scene_moods, overrides) in chapter_emotions.items()
        }
    }
    emotion_path = book_dir / "emotion.json"
    with open(emotion_path, "w", encoding="utf-8") as f:
        json.dump(emotion_data, f, indent=2, ensure_ascii=False)

    rprint(
        f"  Emotion    : [cyan]{total_scenes}[/cyan] scenes annotated, "
        f"[cyan]{total_overrides}[/cyan] line overrides"
    )

    # --- Unload model ---
    unload_model()

    # --- Print stats summary ---
    named_count = sum(1 for c in characters if c.is_named)
    unnamed_count = len(characters) - named_count

    dialogue_count = sum(
        1 for s in attributed_segments if s.get("type") == "dialogue"
    )
    narration_count = sum(
        1 for s in attributed_segments if s.get("type") != "dialogue"
    )

    # Confidence distribution (dialogue only)
    dialogue_segs = [
        s for s in attributed_segments if s.get("type") == "dialogue"
    ]
    if dialogue_segs:
        high = sum(1 for s in dialogue_segs if s.get("confidence", 0) >= 0.8)
        medium = sum(
            1
            for s in dialogue_segs
            if 0.5 <= s.get("confidence", 0) < 0.8
        )
        low = sum(1 for s in dialogue_segs if s.get("confidence", 0) < 0.5)
        total_d = len(dialogue_segs)
        high_pct = round(high / total_d * 100)
        medium_pct = round(medium / total_d * 100)
        low_pct = round(low / total_d * 100)
    else:
        high_pct = medium_pct = low_pct = 0

    flagged_count = sum(
        1
        for s in dialogue_segs
        if s.get("confidence", 0) < CONFIDENCE_FLAG_THRESHOLD
    )

    rprint(
        f"\n[bold green]Attribution complete[/bold green]\n"
        f"\n"
        f"  Characters : [cyan]{len(characters)}[/cyan]"
        f" ({named_count} named, {unnamed_count} unnamed)\n"
        f"  Dialogue   : [cyan]{dialogue_count}[/cyan] segments attributed\n"
        f"  Narration  : [cyan]{narration_count}[/cyan] segments (narrator)\n"
        f"  Confidence : [cyan]{high_pct}%[/cyan] high (>=0.8),"
        f" [cyan]{medium_pct}%[/cyan] medium (0.5-0.79),"
        f" [cyan]{low_pct}%[/cyan] low (<0.5)\n"
        f"  Flagged    : [cyan]{flagged_count}[/cyan]"
        f" segments below {CONFIDENCE_FLAG_THRESHOLD} confidence\n"
        f"  Output     : [cyan]characters.json, attributed.json[/cyan]"
    )

    return characters_path, attributed_path


def run_match(
    book_dir: Path,
    libritts_data_dir: Path,
    libritts_audio_dir: Path | None = None,
    auto_confirm: bool = False,
    model_override: str | None = None,
) -> Path:
    """End-to-end match phase: attributed segments -> voice_map.json.

    Runs the matching orchestrator, displays a Rich table of assignments,
    prompts the user for confirmation, and writes voice_map.json.

    Args:
        book_dir: Book output directory containing characters.json and attributed.json.
        libritts_data_dir: Path to LibriTTS-P data directory.
        libritts_audio_dir: Path to LibriTTS-R audio directory (optional).
        auto_confirm: If True, skip interactive confirmation (pipeline mode).
        model_override: If set, force this Ollama model for LLM-based matching.

    Returns:
        Path to the written voice_map.json file.
    """
    voice_map_path = book_dir / "voice_map.json"

    # --- Preload LLM model for matching ---
    model_name = preload_model(model_override)
    rprint(f"[bold cyan]Using LLM: {model_name}[/bold cyan]")

    # Run matching pipeline
    voice_map = run_matching(book_dir, libritts_data_dir, libritts_audio_dir)

    # If voice_map.json already existed, just print summary and return
    if voice_map_path.exists():
        rprint(
            f"\n[bold green]Voice map loaded[/bold green]\n"
            f"  Characters : [cyan]{len(voice_map.characters)}[/cyan]\n"
            f"  Narrator   : speaker [cyan]{voice_map.narrator.speaker_id}[/cyan]\n"
            f"  Output     : [cyan]{voice_map_path}[/cyan]"
        )
        return voice_map_path

    # --- Display Rich table ---
    book_slug = voice_map.book_slug
    table = Table(title=f'Voice Assignments for "{book_slug}"')
    table.add_column("#", style="dim", width=4)
    table.add_column("Character", style="bold")
    table.add_column("Speaker ID", style="cyan")
    table.add_column("Method")
    table.add_column("Conf", justify="right")
    table.add_column("Reasoning", max_width=50)

    # Narrator row
    n = voice_map.narrator
    narrator_style = "yellow" if n.warning else ""
    table.add_row(
        "0",
        "narrator",
        n.speaker_id,
        n.method,
        f"{n.confidence:.2f}",
        n.reasoning[:50] if len(n.reasoning) > 50 else n.reasoning,
        style=narrator_style,
    )

    # Character rows
    for idx, a in enumerate(voice_map.characters, start=1):
        label = a.character_name
        if not a.is_major:
            label += " (minor)"
        row_style = "yellow" if a.warning else ""
        table.add_row(
            str(idx),
            label,
            a.speaker_id,
            a.method,
            f"{a.confidence:.2f}",
            a.reasoning[:50] if len(a.reasoning) > 50 else a.reasoning,
            style=row_style,
        )

    rprint()
    rprint(table)

    # --- Stats ---
    major_count = sum(1 for a in voice_map.characters if a.is_major)
    minor_count = len(voice_map.characters) - major_count
    major_speakers = {a.speaker_id for a in voice_map.characters if a.is_major}
    minor_speakers = [a.speaker_id for a in voice_map.characters if not a.is_major]
    unique_minor = len(set(minor_speakers))
    shared_minor = len(minor_speakers) - unique_minor

    rprint(
        f"\n  Major: [cyan]{major_count}[/cyan] unique speakers | "
        f"Minor: [cyan]{minor_count}[/cyan] speakers "
        f"([cyan]{shared_minor}[/cyan] shared)"
    )

    # --- User confirmation (skip in pipeline mode) ---
    if auto_confirm:
        with open(voice_map_path, "w", encoding="utf-8") as f:
            json.dump(voice_map.model_dump(), f, indent=2, ensure_ascii=False)
        rprint(f"\n[bold green]Voice map saved:[/bold green] [cyan]{voice_map_path}[/cyan]")
    elif typer.confirm("Write voice_map.json?", default=True):
        with open(voice_map_path, "w", encoding="utf-8") as f:
            json.dump(voice_map.model_dump(), f, indent=2, ensure_ascii=False)
        rprint(f"\n[bold green]Voice map saved:[/bold green] [cyan]{voice_map_path}[/cyan]")
    else:
        rprint(
            "\n[yellow]Voice map not saved.[/yellow] To customize assignments:\n"
            "  1. Edit voice_map.json manually (or create from the table above)\n"
            f"  2. Re-run: python main.py match {book_dir}"
        )
        raise typer.Exit(code=0)

    # Unload Ollama model after matching
    unload_model()

    return voice_map_path


def run_synthesize(
    book_dir: Path,
    chapter: int | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    cpu: bool = False,
    engine_type: str = "qwen3",
    libritts_audio_dir: Path | None = None,
) -> Path:
    """End-to-end synthesis phase: attributed segments -> WAV audio files.

    Loads voice_map.json and attributed.json, then either shows a dry-run
    estimate or runs full synthesis via the configured TTS engine with
    checkpoint/resume.

    Args:
        book_dir: Book output directory containing voice_map.json and attributed.json.
        chapter: If set, only synthesise this chapter number.
        dry_run: If True, show estimates without generating audio.
        verbose: If True, show per-segment detail during synthesis.
        cpu: If True, force CPU mode (skip MPS acceleration).
        engine_type: TTS engine to use (``'qwen3'`` or ``'chatterbox'``).
        libritts_audio_dir: Path to LibriTTS-R audio directory for voice
            reference preparation with transcripts.

    Returns:
        Path to the wavs output directory.
    """
    # ---- Validate inputs ----
    voice_map_path = book_dir / "voice_map.json"
    attributed_path = book_dir / "attributed.json"

    if not voice_map_path.exists():
        rprint(
            f"[red]Error:[/red] voice_map.json not found in [bold]{book_dir}[/bold]. "
            "Run 'match' first."
        )
        raise typer.Exit(code=1)

    if not attributed_path.exists():
        rprint(
            f"[red]Error:[/red] attributed.json not found in [bold]{book_dir}[/bold]. "
            "Run 'attribute' first."
        )
        raise typer.Exit(code=1)

    # ---- Load data ----
    with open(voice_map_path, "r", encoding="utf-8") as f:
        voice_map = VoiceMap.model_validate_json(f.read())

    with open(attributed_path, "r", encoding="utf-8") as f:
        attributed_segments: list[dict] = json.load(f)

    # ---- Filter by chapter if requested ----
    segments = attributed_segments
    if chapter is not None:
        segments = [s for s in segments if s.get("chapter") == chapter]

    # ---- Dry run mode ----
    if dry_run:
        chapter_set = {s.get("chapter") for s in segments}
        num_chapters = len(chapter_set)
        num_segments = len(segments)

        # Estimates: ~3s average audio per segment, 1.5x real-time generation
        avg_audio_s = 3.0
        est_audio_s = num_segments * avg_audio_s
        est_wall_s = num_segments * 4.5  # 1.5x real-time factor
        # WAV size: 24kHz 16-bit mono = 48000 bytes/sec
        est_disk_bytes = num_segments * avg_audio_s * 48000

        def _fmt_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            if hours > 0:
                return f"~{hours}h {minutes:02d}m"
            return f"~{minutes}m"

        def _fmt_size(nbytes: float) -> str:
            if nbytes >= 1_073_741_824:
                return f"~{nbytes / 1_073_741_824:.1f} GB"
            return f"~{nbytes / 1_048_576:.0f} MB"

        wavs_dir = book_dir / "wavs"

        table = Table(title="Dry Run Estimate")
        table.add_column("", style="bold")
        table.add_column("", style="cyan")
        table.add_row("Chapters", str(num_chapters))
        table.add_row("Segments", str(num_segments))
        table.add_row("Est. audio", _fmt_time(est_audio_s))
        table.add_row("Est. wall time", _fmt_time(est_wall_s))
        table.add_row("Est. disk space", _fmt_size(est_disk_bytes))
        table.add_row("WAV output", str(wavs_dir))

        rprint()
        rprint(table)
        return wavs_dir

    # ---- Build config ----
    config = SynthesisConfig(
        device="cpu" if cpu else "auto",
        engine_type=engine_type,
    )

    # Handle --cpu with Qwen3 (MLX manages device selection)
    if cpu and engine_type == "qwen3":
        logger.info(
            "MLX manages device selection for Qwen3-TTS (--cpu ignored)"
        )

    # ---- Run synthesis ----
    wavs_dir = book_dir / "wavs"
    try:
        from src.synthesis.synthesizer import run_synthesis

        stats = run_synthesis(
            book_dir, voice_map, attributed_segments, config,
            chapter=chapter, verbose=verbose,
            libritts_root=libritts_audio_dir,
        )

        # Print completion summary
        def _fmt_duration(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            if hours > 0:
                return f"{hours}h {minutes:02d}m {secs:02d}s"
            return f"{minutes}m {secs:02d}s"

        rprint(
            f"\n[bold green]Synthesis complete[/bold green]\n"
            f"  Segments   : [cyan]{stats.completed}[/cyan] completed"
            f" ({stats.skipped_cached} cached, {stats.failed} failed)\n"
            f"  Audio      : [cyan]{_fmt_duration(stats.total_audio_duration_s)}[/cyan]\n"
            f"  Wall time  : [cyan]{_fmt_duration(stats.total_wall_time_s)}[/cyan]\n"
            f"  Output     : [cyan]{wavs_dir}[/cyan]"
        )

    except KeyboardInterrupt:
        rprint(
            "\n[yellow]Synthesis interrupted.[/yellow] "
            "Checkpoint saved — resume with same command."
        )

    return wavs_dir


def run_assemble(
    book_dir: Path,
    epub_path: Path | None = None,
    title: str | None = None,
    author: str | None = None,
    cover: Path | None = None,
    cpu: bool = False,
) -> Path:
    """End-to-end assembly phase: WAV segments -> chapter MP3s + audiobook.mp3.

    Validates inputs, runs the assembly pipeline (concat, normalize, encode,
    tag), and prints a Rich completion summary.

    Args:
        book_dir: Book output directory containing wavs/, voice_map.json,
            and attributed.json.
        epub_path: Optional source EPUB for metadata extraction.
        title: Override book title for ID3 tags.
        author: Override author for ID3 tags.
        cover: Override cover art image path (JPEG/PNG).
        cpu: If True, force CPU mode for chapter announcement generation.

    Returns:
        Path to the generated audiobook.mp3 file.
    """
    # Validate inputs
    if not book_dir.exists():
        rprint(f"[red]Error:[/red] Directory not found: [bold]{book_dir}[/bold]")
        raise typer.Exit(code=1)

    wavs_dir = book_dir / "wavs"
    if not wavs_dir.exists() or not any(wavs_dir.glob("ch*/*.wav")):
        rprint(
            f"[red]Error:[/red] No WAV files found in [bold]{wavs_dir}[/bold]. "
            "Run 'synthesize' first."
        )
        raise typer.Exit(code=1)

    # Late import to defer torch loading for announcements
    from src.assembly.assembler import run_assembly

    rprint("\n[bold green]Phase 5: Assembly[/bold green]")
    device = "cpu" if cpu else "auto"
    stats = run_assembly(
        book_dir,
        epub_path=epub_path,
        title_override=title,
        author_override=author,
        cover_override=cover,
        device=device,
    )

    # Completion summary
    audiobook_path = book_dir / "audiobook.mp3"
    chapters_dir = book_dir / "chapters"

    def _fmt_duration(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes:02d}m {secs:02d}s"
        return f"{minutes}m {secs:02d}s"

    def _fmt_size(path: Path) -> str:
        if not path.exists():
            return "N/A"
        size = path.stat().st_size
        if size >= 1_073_741_824:
            return f"{size / 1_073_741_824:.1f} GB"
        if size >= 1_048_576:
            return f"{size / 1_048_576:.1f} MB"
        return f"{size / 1024:.1f} KB"

    # Calculate total chapter MP3 size
    chapter_mp3_total = 0
    if chapters_dir.exists():
        for mp3 in chapters_dir.glob("*.mp3"):
            chapter_mp3_total += mp3.stat().st_size

    def _fmt_bytes(nbytes: int) -> str:
        if nbytes >= 1_073_741_824:
            return f"{nbytes / 1_073_741_824:.1f} GB"
        if nbytes >= 1_048_576:
            return f"{nbytes / 1_048_576:.1f} MB"
        return f"{nbytes / 1024:.1f} KB"

    duration_str = _fmt_duration(stats.total_duration_ms / 1000)

    rprint(
        f"\n[bold green]Assembly complete[/bold green]\n"
        f"  Chapters     : [cyan]{stats.chapter_mp3s_created}[/cyan]\n"
        f"  Duration     : [cyan]{duration_str}[/cyan]\n"
        f"  Chapters dir : [cyan]{chapters_dir}[/cyan]"
        f" ({_fmt_bytes(chapter_mp3_total)})\n"
        f"  Audiobook    : [cyan]{audiobook_path}[/cyan]"
        f" ({_fmt_size(audiobook_path)})"
    )

    return audiobook_path


def run_full_pipeline(
    epub_path: Path,
    output_dir: Path,
    libritts_data_dir: Path,
    libritts_audio_dir: Path | None = None,
    cpu: bool = False,
    engine_type: str = "qwen3",
    model_override: str | None = None,
) -> None:
    """Orchestrate all 5 pipeline phases.

    Runs parse -> attribute -> match -> synthesize -> assemble sequentially.
    Designed for unattended overnight runs — no confirmation prompts.

    Args:
        epub_path: Path to the source EPUB file.
        output_dir: Root output directory.
        libritts_data_dir: Path to LibriTTS-P data directory (contains df1_en.csv).
        libritts_audio_dir: Path to LibriTTS-R audio directory (optional).
        cpu: If True, force CPU mode for synthesis and assembly.
        engine_type: TTS engine to use (``'qwen3'`` or ``'chatterbox'``).
        model_override: If set, force this Ollama model for LLM phases.
    """
    rprint("\n[bold green]Phase 1: Parse[/bold green]")
    run_parse(epub_path, output_dir)

    # Derive the book output directory from the epub path
    book_slug = _make_book_slug(epub_path)
    output_book_dir = output_dir / book_slug

    rprint("\n[bold green]Phase 2: Attribute[/bold green]")
    run_attribute(output_book_dir, model_override=model_override)

    rprint("\n[bold green]Phase 3: Match[/bold green]")
    run_match(
        output_book_dir,
        libritts_data_dir,
        libritts_audio_dir,
        auto_confirm=True,  # No interactive prompt in pipeline mode
        model_override=model_override,
    )

    rprint("\n[bold green]Phase 4: Synthesize[/bold green]")
    run_synthesize(
        output_book_dir,
        cpu=cpu,
        engine_type=engine_type,
        libritts_audio_dir=libritts_audio_dir,
    )

    rprint("\n[bold green]Phase 5: Assemble[/bold green]")
    run_assemble(output_book_dir, epub_path=epub_path, cpu=cpu)
