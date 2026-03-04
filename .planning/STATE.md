# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-04)

**Core value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.
**Current focus:** Phase 7 — TTS Engine Swap (v1.1)

## Current Position

Phase: 7 of 9 (TTS Engine Swap)
Plan: 0 of 3 in current phase
Status: Planned — ready to execute
Last activity: 2026-03-04 — Phase 7 planned (3 plans in 2 waves)

Progress: [██████████████████░░░░░░░░░░░░] 17/17 v1.0 plans complete | v1.1: 0% started

## Performance Metrics

**Velocity (v1.0):**
- Total plans completed: 17
- Total execution time: ~2 days
- Phases completed: 6

**v1.1:** No plans executed yet.

## Accumulated Context

### Decisions

All v1.0 decisions documented in PROJECT.md Key Decisions table with outcomes.
v1.1 key decisions from research:
- Emotion system uses text-semantic inference + speech-act post-processing (NOT TTS instruct prompts — Base model ignores them with cloned voices)
- mlx-audio is young (v0.3.1) — Phase 7 needs spike/research before full build
- Voice consistency threshold starts at 0.60 cosine, capped at 3 regen attempts

### Pending Todos

None yet.

### Blockers/Concerns

- mlx-audio v0.3.1 had bugs (#464 audio dropout, #439 accent loss) — both CLOSED as of 2026-01-31; require mlx>=0.30.3
- Qwen3-TTS Base model ignores `instruct` param with cloned voices — emotion system redesigned around this
- Ollama 14B on 16GB needs empirical validation under full novel-length attribution

## Session Continuity

Last session: 2026-03-04
Stopped at: Phase 7 planned, ready to execute
Resume file: .planning/phases/07-tts-engine-swap/07-01-PLAN.md
