"""Rich progress display and synthesis.log writer for overnight runs.

Two display modes (per user decision):
- Default: Chapter-level progress bar ("Chapter 3/24 -- segment 47/312")
- Verbose (-v): Adds per-segment scrolling log (character name, duration, time)

Always writes synthesis.log for morning-after debugging regardless of mode.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from rich import print as rprint
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from src.synthesis.models import SegmentResult, SynthesisStats

logger = logging.getLogger(__name__)


class SynthesisProgress:
    """Track and display synthesis progress with Rich UI and log file.

    Usage::

        progress = SynthesisProgress(24, 2847, wavs_dir, verbose=True)
        progress.start()
        progress.update_chapter(1, "Chapter One")
        progress.update_segment(result)
        progress.show_stats(stats)
        progress.close()
    """

    def __init__(
        self,
        total_chapters: int,
        total_segments: int,
        wavs_dir: Path,
        verbose: bool = False,
    ) -> None:
        self.total_chapters = total_chapters
        self.total_segments = total_segments
        self.verbose = verbose

        # Synthesis log file
        wavs_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = wavs_dir / "synthesis.log"
        self._log_file = open(self._log_path, "a", encoding="utf-8")  # noqa: SIM115

        # Rolling average for ETA (last 20 generation times)
        self._recent_times: deque[float] = deque(maxlen=20)

        # Counters
        self._completed = 0
        self._failed = 0
        self._total_audio_s = 0.0

        # Rich progress bar
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("{task.fields[info]}"),
        )
        self._chapter_task = self._progress.add_task(
            f"Chapter 0/{total_chapters}",
            total=total_chapters,
            info="",
        )
        self._segment_task = self._progress.add_task(
            f"Segment 0/{total_segments}",
            total=total_segments,
            info="",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Enter Rich progress display context."""
        self._progress.start()
        self._log_write("START", f"chapters={self.total_chapters} segments={self.total_segments}")

    def close(self) -> None:
        """Stop progress display and close log file."""
        self._progress.stop()
        if self._log_file and not self._log_file.closed:
            self._log_file.close()

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update_chapter(self, chapter_num: int, chapter_title: str) -> None:
        """Update chapter-level progress bar."""
        desc = f"Chapter {chapter_num}/{self.total_chapters}"
        self._progress.update(
            self._chapter_task,
            completed=chapter_num - 1,
            description=desc,
            info=chapter_title[:40],
        )
        self._log_write("CHAPTER", f"{chapter_num} | {chapter_title}")

    def complete_chapter(self, chapter_num: int) -> None:
        """Mark a chapter as fully processed."""
        self._progress.update(self._chapter_task, completed=chapter_num)

    def update_segment(self, result: SegmentResult) -> None:
        """Update segment-level progress after a segment completes."""
        if result.success:
            self._completed += 1
            self._total_audio_s += result.duration_s
            self._recent_times.append(result.generation_time_s)
        else:
            self._failed += 1

        current = self._completed + self._failed
        self._progress.update(
            self._segment_task,
            completed=current,
            description=f"Segment {current}/{self.total_segments}",
            info=self._eta_str(),
        )

        # Verbose per-segment output
        if self.verbose:
            if result.success:
                rprint(
                    f"  [green]{result.segment_id:>5}[/green] | "
                    f"{result.character_name:<20} | "
                    f"{result.duration_s:.1f}s audio | "
                    f"{result.generation_time_s:.1f}s gen"
                )
            else:
                rprint(
                    f"  [red]{result.segment_id:>5}[/red] | "
                    f"{result.character_name:<20} | "
                    f"FAILED: {result.error}"
                )

        # Always log to synthesis.log
        if result.success:
            self._log_write(
                "OK",
                f"seg_{result.segment_id:04d} | {result.character_name} | "
                f"{result.duration_s:.1f}s audio | {result.generation_time_s:.1f}s gen",
            )
        else:
            self._log_write(
                "FAIL",
                f"seg_{result.segment_id:04d} | {result.character_name} | "
                f"attempt {result.attempts}/{result.attempts} | {result.error}",
            )

    def log_failure(
        self,
        segment_id: int,
        error: str,
        attempt: int,
        max_attempts: int,
    ) -> None:
        """Log a per-attempt failure (before final status is determined)."""
        self._log_write(
            "RETRY",
            f"seg_{segment_id:04d} | attempt {attempt}/{max_attempts} | {error}",
        )
        if self.verbose:
            rprint(
                f"  [yellow]{segment_id:>5}[/yellow] | "
                f"retry {attempt}/{max_attempts} | {error}"
            )

    def log_message(self, message: str) -> None:
        """Write a general message to synthesis.log and console."""
        self._log_write("INFO", message)
        rprint(f"  [dim]{message}[/dim]")

    # ------------------------------------------------------------------
    # Completion summary
    # ------------------------------------------------------------------

    def show_stats(self, stats: SynthesisStats) -> None:
        """Display Rich stats table at end of run."""
        # Format durations
        audio_h = int(stats.total_audio_duration_s // 3600)
        audio_m = int((stats.total_audio_duration_s % 3600) // 60)
        wall_h = int(stats.total_wall_time_s // 3600)
        wall_m = int((stats.total_wall_time_s % 3600) // 60)
        avg_s = (
            stats.total_wall_time_s / stats.completed
            if stats.completed > 0
            else 0
        )

        table = Table(title="Synthesis Complete", show_header=False, padding=(0, 2))
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="cyan")

        table.add_row("Chapters", f"{stats.chapters_completed}/{stats.total_chapters}")
        table.add_row("Segments completed", str(stats.completed))
        table.add_row("Segments failed", str(stats.failed))
        table.add_row("Segments cached", str(stats.skipped_cached))
        table.add_row("Total audio", f"{audio_h}h {audio_m:02d}m")
        table.add_row("Wall clock time", f"{wall_h}h {wall_m:02d}m")
        table.add_row("Avg time/segment", f"{avg_s:.1f}s")

        rprint()
        rprint(table)

        # Log summary
        self._log_write(
            "DONE",
            f"{stats.completed} ok | {stats.failed} failed | "
            f"{audio_h}h{audio_m:02d}m audio | {wall_h}h{wall_m:02d}m wall",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _eta_str(self) -> str:
        """Compute ETA string from rolling average."""
        if not self._recent_times:
            return ""
        avg = sum(self._recent_times) / len(self._recent_times)
        remaining = self.total_segments - (self._completed + self._failed)
        eta_s = avg * remaining
        if eta_s < 3600:
            return f"ETA {int(eta_s // 60)}m {int(eta_s % 60)}s"
        return f"ETA {int(eta_s // 3600)}h {int((eta_s % 3600) // 60)}m"

    def _log_write(self, level: str, message: str) -> None:
        """Write a timestamped line to synthesis.log."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{ts} | {level} | {message}\n"
        if self._log_file and not self._log_file.closed:
            self._log_file.write(line)
            self._log_file.flush()
