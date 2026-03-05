"""Lightweight pre-pipeline checker for audio-book-plz.

Validates that required external dependencies (ffmpeg, Ollama, models, data)
are available before the pipeline runs, so failures surface early with
actionable messages rather than mid-synthesis crashes.
"""

from __future__ import annotations

import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import typer
from rich import print as rprint

_LIBRITTS_DEFAULT = Path.home() / ".local" / "share" / "libritts-p" / "data"
_ANNOTATOR_CSVS = ["df1_en.csv", "df2_en.csv", "df3_en.csv"]


def preflight_check(libritts_data: Path | None = None) -> None:
    """Check everything that would crash the pipeline and exit early on failure.

    Checks are run in order: ffmpeg, Ollama server, Ollama Qwen3 model,
    LibriTTS-P data files, and disk space.  All failures are collected so
    the user sees every problem at once.  Warnings (e.g. low disk space)
    are printed but do not count as failures.

    Parameters
    ----------
    libritts_data:
        Path to the LibriTTS-P data directory.  Falls back to
        ``~/.local/share/libritts-p/data/`` when *None*.

    Raises
    ------
    typer.Exit
        With code 1 if any hard failure is detected.
    """
    failures = 0
    ollama_running = True

    # 1. ffmpeg available
    if shutil.which("ffmpeg") is None:
        rprint("[red]✗ ffmpeg not found.[/red]")
        rprint("  Install it: [bold]brew install ffmpeg[/bold]")
        failures += 1

    # 2. Ollama running — auto-start if installed but not running
    def _ollama_reachable() -> bool:
        try:
            req = urllib.request.Request("http://localhost:11434/api/version")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except (urllib.error.URLError, OSError):
            return False

    if not _ollama_reachable():
        if shutil.which("ollama") is not None:
            rprint("[yellow]Ollama not running — starting it automatically...[/yellow]")
            # Try brew services first, fall back to ollama serve
            started = False
            try:
                subprocess.run(
                    ["brew", "services", "start", "ollama"],
                    capture_output=True, timeout=10,
                )
                started = True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
            if not started:
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            # Wait up to 30 seconds for Ollama to respond
            for _ in range(30):
                if _ollama_reachable():
                    rprint("[green]✓ Ollama started.[/green]")
                    break
                time.sleep(1)
            else:
                rprint("[red]✗ Ollama failed to start after 30 seconds.[/red]")
                failures += 1
                ollama_running = False
        else:
            rprint("[red]✗ Ollama is not installed.[/red]")
            rprint("  Install it: [bold]brew install ollama[/bold]")
            failures += 1
            ollama_running = False

    # 3. Ollama model available (skip when Ollama isn't running)
    if ollama_running:
        try:
            import ollama

            models = ollama.list()
            has_qwen = any(
                m.model.startswith("qwen3.5:") or m.model.startswith("qwen3:") for m in models.models
            )
            if not has_qwen:
                rprint("[red]✗ No Qwen model found in Ollama.[/red]")
                rprint("  Pull one: [bold]ollama pull qwen3.5:9b[/bold]")
                failures += 1
        except Exception:
            rprint("[red]✗ No Qwen model found in Ollama.[/red]")
            rprint("  Pull one: [bold]ollama pull qwen3.5:9b[/bold]")
            failures += 1

    # 4. LibriTTS-P data present
    data_dir = libritts_data if libritts_data is not None else _LIBRITTS_DEFAULT
    if not all((data_dir / csv).exists() for csv in _ANNOTATOR_CSVS):
        rprint(f"[red]✗ LibriTTS-P data not found at {data_dir}.[/red]")
        rprint("  Run [bold]bash setup.sh[/bold] to download it.")
        failures += 1

    # 5. Disk space warning (not a failure)
    free_bytes = shutil.disk_usage("/").free
    free_gb = free_bytes / (1024 ** 3)
    if free_gb < 2.0:
        rprint(f"[yellow]⚠ Low disk space ({free_gb:.1f} GB free).[/yellow]")
        rprint(
            "  Synthesis may need several GB. Free up space before proceeding."
        )

    if failures > 0:
        rprint(
            "[red]Preflight failed. Fix the issues above before running the pipeline.[/red]"
        )
        raise typer.Exit(1)
