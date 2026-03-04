# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.
**Current focus:** Phase 3 — Voice-Character Matching COMPLETE

## Current Position

Phase: 3 of 5 (Voice-Character Matching) — COMPLETE
Plan: 3 of 3 in current phase — all plans complete
Status: Phase 3 complete — ready to begin Phase 4 (TTS Synthesis with Checkpoint/Resume)
Last activity: 2026-03-03 — Plan 03-03 complete (Orchestrator, CLI match command, voice_map.json)

Progress: [████████████░░░] 60%

## Performance Metrics

**Velocity:**
- Total plans completed: 9
- Average duration: 3 min
- Total execution time: 0.38 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-epub-parsing-and-cli-skeleton | 3 | 7 min | 2 min |
| 02-llm-character-extraction-and-speaker-attribution | 3 | 7 min | 2 min |
| 03-voice-character-matching | 3 | 13 min | 4 min |

**Recent Trend:**
- Last 5 plans: 02-02 (2 min), 02-03 (3 min), 03-01 (3 min), 03-02 (5 min), 03-03 (5 min)
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
- Plan 02-01: Pydantic strict mode on value objects but not container models — balances type safety with LLM flexibility
- Plan 02-01: Temperature 0 with format constraint — grammar-constrained decoding handles determinism
- Plan 02-01: Conservative 1:4 char-to-token ratio for context window budgeting
- Plan 02-01: Cache keys include pass_name prefix to differentiate extraction vs attribution
- Plan 02-02: [TYPE] prefixes on chapter text help LLM distinguish dialogue from narration
- Plan 02-02: MIN_SUBSTRING_LENGTH=3 for alias matching prevents false positives on short strings
- Plan 02-02: Surname-only check prevents merging "Mr. Bennet" and "Mrs. Bennet"
- Plan 02-03: REGISTRY_BUDGET_TOKENS=2000 reserves space for character registry in attribution prompt
- Plan 02-03: CONFIDENCE_FLAG_THRESHOLD=0.7 — attributions below this flagged in stats
- Plan 02-03: LLM failure fallback: speaker="unknown", confidence=0.0 rather than crashing
- Plan 03-01: Gender inferred from any trait containing "masculine"/"feminine" including modifiers like "very"
- Plan 03-01: Age filter is soft — falls back to all gender-matched speakers if no age keywords match
- Plan 03-01: First-person narrator detected by >30% pronoun ratio in 20 sampled narration segments
- Plan 03-02: LLM trait matcher retries up to 3 times for invalid speaker_id, then returns None for embedding fallback
- Plan 03-02: Embedding matcher uses all-MiniLM-L6-v2 (80MB, 384-dim) cached at module level
- Plan 03-02: Dedup keeps higher-confidence assignment; minor sharing allowed across chapters only
- Plan 03-03: Embedding pre-ranking limits >50 candidates to top 30 before LLM evaluation
- Plan 03-03: Re-run caching: existing voice_map.json returned without LLM calls
- Plan 03-03: sentence-transformers>=3.0 added to project dependencies

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: Qwen3 8B structured output reliability for fiction dialogue attribution is not fully characterised — recommend a prompt validation step at the start of Phase 2 planning
- Phase 3: RESOLVED — LibriTTS-P full 2,443-speaker index used with gender/age pre-filtering to manageable candidate pools
- Phase 4: Chatterbox MPS stability on Apple Silicon requires a focused validation sprint before writing production synthesis logic; set PYTORCH_ENABLE_MPS_FALLBACK=1 and run a 10-segment health check before any long run

## Session Continuity

Last session: 2026-03-03
Stopped at: Phase 4 context gathered
Resume file: .planning/phases/04-tts-synthesis-with-checkpoint-resume/04-CONTEXT.md
