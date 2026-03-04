"""Audio Book Plz — Convert EPUBs to multi-voice audiobooks."""

from pathlib import Path

import typer
from rich import print as rprint

from src.pipeline import run_attribute, run_full_pipeline, run_parse

app = typer.Typer(
    no_args_is_help=True,
    help="Audio Book Plz — Convert EPUBs to multi-voice audiobooks.",
)


@app.command()
def parse(
    epub_file: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Path to EPUB file",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        help="Output directory",
    ),
) -> None:
    """Parse EPUB into speech-ready segments.json."""
    if epub_file.suffix.lower() != ".epub":
        rprint(
            f"[red]Error:[/red] Expected an .epub file, got [bold]{epub_file.suffix!r}[/bold]."
        )
        raise typer.Exit(code=1)

    run_parse(epub_file, output_dir)


@app.command()
def convert(
    epub_file: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        help="Path to EPUB file",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        help="Output directory",
    ),
) -> None:
    """Run full pipeline: parse -> attribute -> match -> synthesize -> assemble."""
    if epub_file.suffix.lower() != ".epub":
        rprint(
            f"[red]Error:[/red] Expected an .epub file, got [bold]{epub_file.suffix!r}[/bold]."
        )
        raise typer.Exit(code=1)

    run_full_pipeline(epub_file, output_dir)


@app.command()
def attribute(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
) -> None:
    """Attribute dialogue speakers using local LLM."""
    segments_file = book_dir / "segments.json"
    if not segments_file.exists():
        rprint(
            f"[red]Error:[/red] segments.json not found in [bold]{book_dir}[/bold]. "
            "Run 'parse' first."
        )
        raise typer.Exit(code=1)

    run_attribute(book_dir)


@app.command()
def match(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
) -> None:
    """Match characters to voice references."""
    rprint("[yellow]Not yet implemented — coming in Phase 3[/yellow]")
    raise typer.Exit(code=0)


@app.command()
def synthesize(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
) -> None:
    """Synthesize audio segments with Chatterbox TTS."""
    rprint("[yellow]Not yet implemented — coming in Phase 4[/yellow]")
    raise typer.Exit(code=0)


@app.command()
def assemble(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
) -> None:
    """Assemble segments into final audiobook MP3."""
    rprint("[yellow]Not yet implemented — coming in Phase 5[/yellow]")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
