---
phase: 01-epub-parsing-and-cli-skeleton
plan: 03
subsystem: cli
tags: [typer, rich, pipeline, cli, json, epub, segments]

# Dependency graph
requires:
  - src/parser/epub_reader.py (load_epub, get_story_chapters from Plan 01)
  - src/parser/html_cleaner.py (chapter_to_text_blocks from Plan 01)
  - src/parser/segmenter.py (process_chapter_blocks from Plan 02)
  - src/parser/models.py (Segment, SegmentType from Plan 01)
provides:
  - main.py Typer CLI entry point with 6 commands (parse, convert, attribute, match, synthesize, assemble)
  - src/pipeline.py with run_parse() and run_full_pipeline()
  - output/{book-slug}/segments.json produced by `python main.py parse book.epub`
  - src/parser/__init__.py with clean public API exports
affects:
  - Phase 2 (attribute command stub wired; pipeline.py is the integration point for all future phases)
  - Phase 3, 4, 5 (stub commands wired; pipeline.py run_full_pipeline orchestrates all phases)

# Tech tracking
tech-stack:
  added:
    - typer 0.24.1 (CLI framework — Argument/Option with built-in exists/readable validation)
    - rich.progress.track (per-chapter progress bar during parsing)
    - rich.print (coloured terminal summary output)
    - dataclasses.asdict (Segment -> dict for JSON serialisation)
    - json.dump with indent=2 and ensure_ascii=False (segments.json formatting)
  patterns:
    - Typer Argument with exists=True provides built-in file existence validation
    - rich.progress.track() wraps any iterable for automatic progress display
    - _make_book_slug(): stem.lower() -> replace spaces/underscores -> strip non-alphanumeric
    - Stub commands print phase message and raise typer.Exit(code=0) for clean exit
    - app = typer.Typer(no_args_is_help=True) shows help when invoked bare

key-files:
  created:
    - main.py
    - src/pipeline.py
  modified:
    - src/parser/__init__.py

key-decisions:
  - "Book slug derived from EPUB filename: stem.lower(), spaces/underscores to hyphens, strip non-alphanumeric, collapse multiple hyphens"
  - "Stub commands use typer.Exit(code=0) not sys.exit — cleaner Typer integration and testable"
  - "run_full_pipeline has no confirmation prompt — designed for unattended overnight runs per user decision"
  - ".epub extension validated manually in parse/convert commands (Typer's exists=True validates path existence but not extension)"

patterns-established:
  - "Pipeline entry: always call via run_parse() or run_full_pipeline() from src/pipeline.py"
  - "Segment JSON output: json.dump([dataclasses.asdict(s) for s in segments], f, ensure_ascii=False, indent=2)"
  - "Book output dir: output_dir / book_slug / segments.json (one sub-dir per book)"

requirements-completed:
  - PARSE-07
  - CLI-01
  - CLI-02

# Metrics
duration: 1min
completed: 2026-03-04
---

# Phase 01 Plan 03: CLI and Pipeline Wiring Summary

**Typer CLI with 6 commands wired to pipeline orchestrator that reads EPUBs end-to-end and writes indent=2 segments.json with Rich progress bar and coloured summary**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-03-04T05:48:12Z
- **Completed:** 2026-03-04T05:49:30Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `src/pipeline.py` with `run_parse()` (EPUB -> segments.json with Rich progress + coloured summary) and `run_full_pipeline()` (calls run_parse then stubs phases 2-5)
- `main.py` Typer CLI with all 6 commands: parse, convert, attribute, match, synthesize, assemble — each with auto-generated `--help` text
- `src/parser/__init__.py` exporting the full public API (load_epub, get_story_chapters, chapter_to_text_blocks, process_chapter_blocks) for clean downstream imports
- Book slug derived from EPUB filename ensures unique, filesystem-safe output directories under `output/`
- All stub commands print phase-specific messages and exit cleanly with code 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Create pipeline orchestrator with parse phase logic and JSON output** - `1d1b105` (feat)
2. **Task 2: Create Typer CLI with all phase commands** - `4c2ad93` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `main.py` - Typer app with 6 commands; epub extension validation; imports from src.pipeline
- `src/pipeline.py` - run_parse() and run_full_pipeline(); Rich progress.track and rprint summary; json.dump output
- `src/parser/__init__.py` - Public API exports for all 4 parser functions

## Decisions Made

- **Book slug construction:** `stem.lower().replace(' ', '-').replace('_', '-')` then `re.sub(r'[^a-z0-9-]', '', slug)` then collapse multiple hyphens. Fallback to `"book"` if result is empty. Handles parentheses, years, and special characters in filenames.
- **Stub exit pattern:** `raise typer.Exit(code=0)` rather than `return` — Typer distinguishes between function return (exit 0) and explicit Exit(code=N), making stub intent unambiguous and testable.
- **No confirmation prompt in convert:** Follows the user decision that the pipeline is "suitable for overnight unattended runs."
- **Manual .epub extension check:** Typer's `exists=True` on Argument validates path existence but does not enforce file extension. Added explicit `if epub_file.suffix.lower() != ".epub"` check with clear error message.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 1 complete: all 3 plans executed. The full parsing stack is operational end-to-end.
- `python main.py parse book.epub` will produce `output/{slug}/segments.json` for any EPUB
- Phase 2 (attribute) entry point is stubbed and ready: `python main.py attribute output/{slug}/`
- Blockers noted in STATE.md still apply for Phases 2-4 planning (Qwen3 validation, LibriTTS scope, Chatterbox MPS stability)

## Self-Check: PASSED

- `main.py` exists at project root (111 lines, min_lines: 40 met)
- `src/pipeline.py` exists (127 lines, min_lines: 30 met)
- `src/parser/__init__.py` exports all 4 required symbols
- `python main.py --help` lists all 6 commands
- `python main.py parse --help` shows epub_file argument and output_dir option
- `python main.py convert --help` shows epub_file argument and output_dir option
- `python main.py attribute --help` shows book_dir argument
- `python main.py synthesize --help` shows book_dir argument
- All stub commands exit 0 with correct messages
- `from src.pipeline import run_parse, run_full_pipeline` imports without error
- `app = typer.Typer` present in main.py
- `from src.pipeline import` import link present in main.py
- `load_epub|get_story_chapters` pattern present in pipeline.py
- `chapter_to_text_blocks` pattern present in pipeline.py
- `process_chapter_blocks` pattern present in pipeline.py
- `json.dump` and `asdict` patterns present in pipeline.py
- Commits 1d1b105 and 4c2ad93 verified in git log

---
*Phase: 01-epub-parsing-and-cli-skeleton*
*Completed: 2026-03-04*
