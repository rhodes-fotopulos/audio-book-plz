"""Pipeline orchestrator for audio-book-plz.

Coordinates the multi-phase conversion pipeline:
  Phase 1 - Parse:      EPUB -> segments.json
  Phase 2 - Attribute:  segments.json -> attributed segments (stub)
  Phase 3 - Match:      attributed segments -> voice assignments (stub)
  Phase 4 - Synthesize: segments -> audio files (stub)
  Phase 5 - Assemble:   audio files -> final MP3 (stub)
"""

from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from rich import print as rprint
from rich.progress import track

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


def run_full_pipeline(epub_path: Path, output_dir: Path) -> None:
    """Orchestrate all 5 pipeline phases.

    Phase 1 (parse) is fully implemented. Phases 2-5 print stub messages and
    return immediately. Designed for unattended overnight runs — no
    confirmation prompts.

    Args:
        epub_path: Path to the source EPUB file.
        output_dir: Root output directory.
    """
    run_parse(epub_path, output_dir)

    rprint("[yellow]Phase 2 (attribute): not yet implemented[/yellow]")
    rprint("[yellow]Phase 3 (match): not yet implemented[/yellow]")
    rprint("[yellow]Phase 4 (synthesize): not yet implemented[/yellow]")
    rprint("[yellow]Phase 5 (assemble): not yet implemented[/yellow]")
