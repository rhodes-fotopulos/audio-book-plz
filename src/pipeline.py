"""Pipeline orchestrator for audio-book-plz.

Coordinates the multi-phase conversion pipeline:
  Phase 1 - Parse:      EPUB -> segments.json
  Phase 2 - Attribute:  segments.json -> characters.json + attributed.json
  Phase 3 - Match:      attributed segments -> voice_map.json
  Phase 4 - Synthesize: segments -> audio files (stub)
  Phase 5 - Assemble:   audio files -> final MP3 (stub)
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

import typer
from rich import print as rprint
from rich.progress import track
from rich.table import Table

from src.attribution import (
    attribute_all_segments,
    extract_all_characters,
    merge_characters,
    unload_model,
)
from src.attribution.attributor import CONFIDENCE_FLAG_THRESHOLD
from src.matching.orchestrator import run_matching
from src.parser.epub_reader import get_story_chapters, load_epub
from src.parser.html_cleaner import chapter_to_text_blocks
from src.parser.segmenter import process_chapter_blocks


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


def run_attribute(book_dir: Path) -> tuple[Path, Path]:
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

    Returns:
        Tuple of (characters_path, attributed_path).
    """
    # Load segments
    segments_path = book_dir / "segments.json"
    with open(segments_path, "r", encoding="utf-8") as f:
        segments = json.load(f)

    cache_dir = book_dir / ".cache"

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
) -> Path:
    """End-to-end match phase: attributed segments -> voice_map.json.

    Runs the matching orchestrator, displays a Rich table of assignments,
    prompts the user for confirmation, and writes voice_map.json.

    Args:
        book_dir: Book output directory containing characters.json and attributed.json.
        libritts_data_dir: Path to LibriTTS-P data directory.
        libritts_audio_dir: Path to LibriTTS-R audio directory (optional).

    Returns:
        Path to the written voice_map.json file.
    """
    voice_map_path = book_dir / "voice_map.json"

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

    # --- User confirmation ---
    if typer.confirm("Write voice_map.json?", default=True):
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


def run_full_pipeline(epub_path: Path, output_dir: Path) -> None:
    """Orchestrate all 5 pipeline phases.

    Phases 1 (parse) and 2 (attribute) are fully implemented.
    Phases 3-5 print stub messages and return immediately.
    Designed for unattended overnight runs — no confirmation prompts.

    Args:
        epub_path: Path to the source EPUB file.
        output_dir: Root output directory.
    """
    run_parse(epub_path, output_dir)

    # Derive the book output directory from the epub path
    book_slug = _make_book_slug(epub_path)
    output_book_dir = output_dir / book_slug
    run_attribute(output_book_dir)

    rprint(
        "[yellow]Phase 3 (match): requires --libritts-data path. "
        "Run separately: python main.py match <book-dir> --libritts-data <path>[/yellow]"
    )
    rprint("[yellow]Phase 4 (synthesize): not yet implemented[/yellow]")
    rprint("[yellow]Phase 5 (assemble): not yet implemented[/yellow]")
