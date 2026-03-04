# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.
**Current focus:** Phase 6 — Integration Fixes and Full Pipeline Wiring COMPLETE

## Current Position

Phase: 6 of 6 (Integration Fixes and Full Pipeline Wiring) — COMPLETE
Plan: 2 of 2 in current phase — all plans complete
Status: ALL PHASES COMPLETE — full pipeline operational end-to-end
Last activity: 2026-03-04 — Plan 06-02 complete (pipeline wiring, CLI options)

Progress: [████████████████████] 100%

## Performance Metrics

**Velocity:**
- Total plans completed: 17
- Average duration: 3 min
- Total execution time: 0.83 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-epub-parsing-and-cli-skeleton | 3 | 7 min | 2 min |
| 02-llm-character-extraction-and-speaker-attribution | 3 | 7 min | 2 min |
| 03-voice-character-matching | 3 | 13 min | 4 min |
| 04-tts-synthesis-with-checkpoint-resume | 3 | 12 min | 4 min |
| 05-audio-assembly-and-final-output | 3 | 11 min | 4 min |
| 06-integration-fixes-and-full-pipeline-wiring | 2 | 7 min | 4 min |

**Recent Trend:**
- Last 5 plans: 05-01 (3 min), 05-02 (3 min), 05-03 (5 min), 06-01 (3 min), 06-02 (4 min)
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
- Plan 04-01: CPU-first model loading with component-wise MPS migration (t3, s3gen, ve) for Chatterbox on Apple Silicon
- Plan 04-01: Atomic WAV writes via .tmp + os.rename to prevent corruption on crashes
- Plan 04-01: Checkpoint JSON tracks completed/failed segments with WAV validation on resume
- Plan 04-02: Failure threshold stops run if >15% segments fail after minimum 20 processed
- Plan 04-02: Memory cleanup every 15 segments via config.cleanup_interval
- Plan 04-02: End-of-run retry pass gated by failure threshold (prevents retrying fundamentally broken runs)
- Plan 04-03: Dry-run estimates: 3s avg audio/segment, 1.5x real-time factor, 48KB/s WAV size
- Plan 04-03: run_synthesis() imported inside run_synthesize() to defer torch/chatterbox import
- Plan 04-03: chatterbox-tts>=0.1.6 added to project dependencies
- Plan 05-01: Silence spacing: sentence=400ms, paragraph=900ms, scene_break=2500ms, chapter=1500ms, post-announcement=800ms
- Plan 05-01: Anti-truncation padding: 100ms silence appended before MP3 export to prevent pydub end-truncation bug
- Plan 05-01: pydub>=0.25.1, pyloudnorm>=0.2.0, mutagen>=1.47.0 added to project dependencies
- Plan 05-02: LUFS normalization target -19.0 (audiobook standard range -23 to -18, slightly louder for personal listening)
- Plan 05-02: Minimum 400ms audio for valid LUFS measurement; shorter audio returned unchanged
- Plan 05-02: MP3 bitrate 64k CBR mono (ACX/Audible standard for spoken word)
- Plan 05-02: Chapter announcements use exaggeration=0.2 and cfg_weight=0.3 for neutral narrator tone
- Plan 05-03: Zero-padded CHAP element IDs (chp000, chp001...) to prevent chapter ordering issues in players
- Plan 05-03: Genre always set to "Audiobook" for ID3 tags
- Plan 05-03: Late import of run_assembly in pipeline.py to defer torch loading for announcements
- Plan 05-03: WAV files not cleaned up after assembly per user decision
- [Phase 06]: Plan 06-01: AUDIO_DIR/ prefix detected as placeholder pattern before file existence check
- [Phase 06]: Plan 06-01: Announcer returns empty dict (not None) for consistent downstream handling
- [Phase 06]: Plan 06-02: auto_confirm=True in pipeline mode — voice map written without interactive prompt
- [Phase 06]: Plan 06-02: libritts_data_dir is required parameter for run_full_pipeline (Phase 3 cannot run without it)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: Qwen3 8B structured output reliability for fiction dialogue attribution is not fully characterised — recommend a prompt validation step at the start of Phase 2 planning
- Phase 3: RESOLVED — LibriTTS-P full 2,443-speaker index used with gender/age pre-filtering to manageable candidate pools
- Phase 4: Chatterbox MPS stability on Apple Silicon requires a focused validation sprint before writing production synthesis logic; set PYTORCH_ENABLE_MPS_FALLBACK=1 and run a 10-segment health check before any long run

## Session Continuity

Last session: 2026-03-04
Stopped at: Completed 06-02-PLAN.md — Phase 6 complete, all phases done
Resume file: N/A — all phases complete
