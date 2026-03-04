# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.
**Current focus:** Phase 1 — EPUB Parsing and CLI Skeleton COMPLETE

## Current Position

Phase: 1 of 5 (EPUB Parsing and CLI Skeleton) — COMPLETE
Plan: 3 of 3 in current phase — all plans complete
Status: Phase 1 complete — ready to begin Phase 2 (Dialogue Attribution)
Last activity: 2026-03-04 — Plan 01-03 complete (Typer CLI and pipeline orchestrator)

Progress: [████░░░░░░] 20%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 2 min
- Total execution time: 0.12 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-epub-parsing-and-cli-skeleton | 3 | 7 min | 2 min |

**Recent Trend:**
- Last 5 plans: 01-01 (2 min), 01-02 (4 min), 01-03 (1 min)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Sequential phases (not concurrent): Memory safety on 16GB M4 — LLM and TTS run in separate phases with explicit teardown at the Phase 3/4 boundary
- Python 3.11 required: Chatterbox pins sub-dependencies that break on 3.12+
- Chatterbox standard 500M model only: Turbo variant has a known Float64 MPS error — must not be used
- Plan 01-01: setuptools.build_meta used as build backend (setuptools.backends.legacy not available in Python 3.11 setuptools bundled with uv)
- Plan 01-01: uv venv .venv with Python 3.11.14 for environment management (system pip blocked by PEP 668)
- Plan 01-01: 4 SegmentType values only — no 5th for internal monologue; Phase 2 LLM handles that distinction with full story context
- Plan 01-02: Short text blocks (<=280 chars) returned as single segment without NLTK splitting — dialogue lines kept together when they fit
- Plan 01-02: Conservative dialogue tagging — any double quote presence tags block as dialogue; Phase 2 LLM refines attribution
- Plan 01-02: Plain apostrophe (U+0027) excluded from dialogue detection; only curly single U+2018/U+2019 triggers dialogue
- Plan 01-03: Book slug derived from EPUB filename (stem.lower, spaces/underscores to hyphens, strip non-alphanumeric, collapse hyphens)
- Plan 01-03: Stub commands use typer.Exit(code=0) for clean exit and testability
- Plan 01-03: run_full_pipeline has no confirmation prompt — designed for unattended overnight runs
- Plan 01-03: .epub extension validated manually in CLI (Typer exists=True validates path existence, not extension)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: Qwen3 8B structured output reliability for fiction dialogue attribution is not fully characterised — recommend a prompt validation step at the start of Phase 2 planning
- Phase 3: LibriTTS-P subset scope (train-clean-360 vs full 100GB+ dataset) needs confirmation before Phase 3 planning
- Phase 4: Chatterbox MPS stability on Apple Silicon requires a focused validation sprint before writing production synthesis logic; set PYTORCH_ENABLE_MPS_FALLBACK=1 and run a 10-segment health check before any long run

## Session Continuity

Last session: 2026-03-03
Stopped at: Phase 2 context gathered
Resume file: .planning/phases/02-llm-character-extraction-and-speaker-attribution/02-CONTEXT.md
