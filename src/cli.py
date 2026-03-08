"""Audio Book Plz — Convert EPUBs to multi-voice audiobooks."""

from pathlib import Path

import typer
from rich import print as rprint

from src.pipeline import (
    run_assemble,
    run_attribute,
    run_full_pipeline,
    run_match,
    run_parse,
    run_synthesize,
    run_voice_check,
)
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
    libritts_data: Path = typer.Option(
        None,
        help="Path to LibriTTS-P data directory (contains df1_en.csv). "
        "Default: LIBRITTS_P_DATA env var or ~/.local/share/libritts-p/data",
        envvar="LIBRITTS_P_DATA",
    ),
    libritts_audio: Path = typer.Option(
        None,
        help="Path to LibriTTS-R audio directory (optional). "
        "Default: LIBRITTS_R_AUDIO env var",
        envvar="LIBRITTS_R_AUDIO",
    ),
    engine: str = typer.Option(
        "qwen3",
        "--engine",
        help="TTS engine: qwen3 (MLX)",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Override LLM model (e.g., qwen3.5:9b, claude-code). "
        "Use 'claude-code' to run through Claude Code CLI (requires Max plan).",
    ),
    cpu: bool = typer.Option(
        False,
        "--cpu",
        help="Force CPU mode (skip MPS acceleration)",
    ),
    voice_threshold: float = typer.Option(
        0.60,
        "--voice-threshold",
        help="Cosine similarity threshold for voice consistency (0.0-1.0)",
    ),
    mp3_dir: Path = typer.Option(
        None,
        "--mp3-dir",
        help="Output directory for MP3 files (default: alongside input EPUB)",
    ),
    speech_act_fx: bool = typer.Option(
        False,
        "--speech-act-fx",
        help="Enable speech-act audio adjustments (whispered/shouted/thought volume/speed changes)",
    ),
    batch_by_character: bool = typer.Option(
        False,
        "--batch-by-character",
        help="Synthesize per-character (all segments for each voice consecutively) instead of chapter-by-chapter",
    ),
    clean_voices: bool = typer.Option(
        False,
        "--clean-voices",
        help="Delete cached LibriTTS-R voice reference clips after synthesis completes",
    ),
) -> None:
    """Run full pipeline: parse -> attribute -> match -> synthesize -> assemble."""
    if epub_file.suffix.lower() != ".epub":
        rprint(
            f"[red]Error:[/red] Expected an .epub file, got [bold]{epub_file.suffix!r}[/bold]."
        )
        raise typer.Exit(code=1)

    # Resolve libritts_data directory (same logic as match command)
    if libritts_data is None:
        default_data = Path.home() / ".local" / "share" / "libritts-p" / "data"
        if default_data.exists():
            libritts_data = default_data
        else:
            rprint(
                "[red]Error:[/red] LibriTTS-P data directory not specified. "
                "Use --libritts-data or set LIBRITTS_P_DATA env var."
            )
            raise typer.Exit(code=1)

    # Validate libritts_data has expected files
    if not (libritts_data / "df1_en.csv").exists():
        rprint(
            f"[red]Error:[/red] df1_en.csv not found in [bold]{libritts_data}[/bold]. "
            "Is this a valid LibriTTS-P data directory?"
        )
        raise typer.Exit(code=1)

    run_full_pipeline(
        epub_file, output_dir, libritts_data, libritts_audio,
        cpu=cpu, engine_type=engine, model_override=model,
        voice_threshold=voice_threshold, mp3_output_dir=mp3_dir,
        speech_act_fx=speech_act_fx,
        batch_by_character=batch_by_character,
    )

    if clean_voices:
        from src.matching.audio_downloader import clean_voice_cache

        clean_voice_cache()


@app.command()
def attribute(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Override LLM model (e.g., qwen3.5:9b, claude-code). "
        "Use 'claude-code' to run through Claude Code CLI (requires Max plan).",
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

    run_attribute(book_dir, model_override=model)


@app.command()
def match(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
    libritts_data: Path = typer.Option(
        None,
        help="Path to LibriTTS-P data directory (contains df1_en.csv). "
        "Default: LIBRITTS_P_DATA env var or ~/.local/share/libritts-p/data",
        envvar="LIBRITTS_P_DATA",
    ),
    libritts_audio: Path = typer.Option(
        None,
        help="Path to LibriTTS-R audio directory (optional). "
        "Default: LIBRITTS_R_AUDIO env var",
        envvar="LIBRITTS_R_AUDIO",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="Override LLM model (e.g., qwen3.5:9b, claude-code). "
        "Use 'claude-code' to run through Claude Code CLI (requires Max plan).",
    ),
) -> None:
    """Match characters to LibriTTS-P voice references."""
    # Validate book_dir has required files
    characters_file = book_dir / "characters.json"
    attributed_file = book_dir / "attributed.json"

    if not characters_file.exists():
        rprint(
            f"[red]Error:[/red] characters.json not found in [bold]{book_dir}[/bold]. "
            "Run 'attribute' first."
        )
        raise typer.Exit(code=1)

    if not attributed_file.exists():
        rprint(
            f"[red]Error:[/red] attributed.json not found in [bold]{book_dir}[/bold]. "
            "Run 'attribute' first."
        )
        raise typer.Exit(code=1)

    # Resolve libritts_data directory
    if libritts_data is None:
        default_data = Path.home() / ".local" / "share" / "libritts-p" / "data"
        if default_data.exists():
            libritts_data = default_data
        else:
            rprint(
                "[red]Error:[/red] LibriTTS-P data directory not specified. "
                "Use --libritts-data or set LIBRITTS_P_DATA env var."
            )
            raise typer.Exit(code=1)

    # Validate libritts_data has expected files
    if not (libritts_data / "df1_en.csv").exists():
        rprint(
            f"[red]Error:[/red] df1_en.csv not found in [bold]{libritts_data}[/bold]. "
            "Is this a valid LibriTTS-P data directory?"
        )
        raise typer.Exit(code=1)

    run_match(book_dir, libritts_data, libritts_audio, model_override=model)


@app.command()
def synthesize(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
    chapter: int = typer.Option(
        None,
        help="Synthesize only this chapter number (useful for voice testing)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show estimated time and disk space without synthesizing",
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Show per-segment detail during synthesis",
    ),
    engine: str = typer.Option(
        "qwen3",
        "--engine",
        help="TTS engine: qwen3 (MLX)",
    ),
    cpu: bool = typer.Option(
        False,
        "--cpu",
        help="Force CPU mode (skip MPS acceleration)",
    ),
    libritts_audio: Path = typer.Option(
        None,
        "--libritts-audio",
        help="Path to LibriTTS-R audio directory (optional). "
        "Default: LIBRITTS_R_AUDIO env var",
        envvar="LIBRITTS_R_AUDIO",
    ),
    speech_act_fx: bool = typer.Option(
        False,
        "--speech-act-fx",
        help="Enable speech-act audio adjustments (whispered/shouted/thought volume/speed changes)",
    ),
    batch_by_character: bool = typer.Option(
        False,
        "--batch-by-character",
        help="Synthesize per-character (all segments for each voice consecutively) instead of chapter-by-chapter",
    ),
) -> None:
    """Synthesize audio segments with Qwen3-TTS."""
    # Validate prerequisites
    voice_map_file = book_dir / "voice_map.json"
    attributed_file = book_dir / "attributed.json"

    if not voice_map_file.exists():
        rprint(
            f"[red]Error:[/red] voice_map.json not found in [bold]{book_dir}[/bold]. "
            "Run 'match' first."
        )
        raise typer.Exit(code=1)

    if not attributed_file.exists():
        rprint(
            f"[red]Error:[/red] attributed.json not found in [bold]{book_dir}[/bold]. "
            "Run 'attribute' first."
        )
        raise typer.Exit(code=1)

    run_synthesize(
        book_dir, chapter=chapter, dry_run=dry_run, verbose=verbose,
        cpu=cpu, engine_type=engine,
        libritts_audio_dir=libritts_audio,
        speech_act_fx=speech_act_fx,
        batch_by_character=batch_by_character,
    )


@app.command()
def assemble(
    book_dir: Path = typer.Argument(
        ...,
        help="Output directory for a specific book (e.g. output/the-name-of-the-wind/)",
    ),
    epub: Path = typer.Option(
        None,
        "--epub",
        help="Source EPUB for metadata extraction (title, author, cover)",
    ),
    title: str = typer.Option(
        None,
        "--title",
        help="Override book title for ID3 tags",
    ),
    author: str = typer.Option(
        None,
        "--author",
        help="Override author for ID3 tags",
    ),
    cover: Path = typer.Option(
        None,
        "--cover",
        help="Override cover art image (JPEG/PNG)",
    ),
    cpu: bool = typer.Option(
        False,
        "--cpu",
        help="Force CPU mode for chapter announcement generation",
    ),
    voice_threshold: float = typer.Option(
        0.60,
        "--voice-threshold",
        help="Cosine similarity threshold for voice consistency (0.0-1.0)",
    ),
    mp3_dir: Path = typer.Option(
        None,
        "--mp3-dir",
        help="Output directory for MP3 files (default: alongside book dir)",
    ),
) -> None:
    """Assemble WAV segments into chapter MP3s and combined audiobook."""
    # Validate book_dir exists
    if not book_dir.exists():
        rprint(f"[red]Error:[/red] Directory not found: [bold]{book_dir}[/bold]")
        raise typer.Exit(code=1)

    # Validate epub if provided
    if epub is not None and not epub.exists():
        rprint(f"[red]Error:[/red] EPUB file not found: [bold]{epub}[/bold]")
        raise typer.Exit(code=1)

    # Validate cover if provided
    if cover is not None and not cover.exists():
        rprint(f"[red]Error:[/red] Cover image not found: [bold]{cover}[/bold]")
        raise typer.Exit(code=1)

    # Run voice consistency check before assembly
    rprint("\n[bold green]Voice Consistency Check[/bold green]")
    run_voice_check(book_dir, voice_threshold=voice_threshold)

    run_assemble(
        book_dir, epub_path=epub, title=title, author=author, cover=cover,
        cpu=cpu, output_dir=mp3_dir,
    )


@app.command()
def verify_voices(
    book_dir: Path = typer.Argument(
        ...,
        help="Book output directory (e.g. output/the-name-of-the-wind/)",
    ),
    voice_threshold: float = typer.Option(
        0.60,
        "--voice-threshold",
        help="Cosine similarity threshold for voice consistency (0.0-1.0)",
    ),
) -> None:
    """Verify voice consistency of synthesized segments (standalone check)."""
    if not book_dir.exists():
        rprint(f"[red]Error:[/red] Directory not found: [bold]{book_dir}[/bold]")
        raise typer.Exit(code=1)

    wavs_dir = book_dir / "wavs"
    if not wavs_dir.exists():
        rprint(
            f"[red]Error:[/red] No wavs/ directory in [bold]{book_dir}[/bold]. "
            "Run 'synthesize' first."
        )
        raise typer.Exit(code=1)

    rprint("\n[bold green]Voice Consistency Check[/bold green]")
    report_path = run_voice_check(book_dir, voice_threshold=voice_threshold)
    rprint(f"\n  Report: [cyan]{report_path}[/cyan]")


@app.command(name="clean-voices")
def clean_voices_cmd() -> None:
    """Delete cached LibriTTS-R voice reference clips (~/.local/share/libritts-r/audio/)."""
    from src.matching.audio_downloader import clean_voice_cache

    clean_voice_cache()


@app.command()
def doctor() -> None:
    """Check system health and dependencies."""
    from src.doctor import run_doctor

    all_ok = run_doctor()
    if not all_ok:
        raise typer.Exit(code=1)
