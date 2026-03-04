# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-04)

**Core value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.
**Current focus:** Phase 7 — TTS Engine Swap (v1.1)

## Current Position

Phase: 7 of 9 (TTS Engine Swap)
Plan: 0 of ? in current phase
Status: Ready to plan
Last activity: 2026-03-04 — v1.1 roadmap created (3 phases, 18 requirements)

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

- mlx-audio v0.3.1 has active bugs (#464 audio dropout, #439 accent loss) — validate in Phase 7 spike
- Qwen3-TTS Base model ignores `instruct` param with cloned voices — emotion system redesigned around this
- Ollama 14B on 16GB needs empirical validation under full novel-length attribution

## Session Continuity

Last session: 2026-03-04
Stopped at: v1.1 roadmap created, ready to plan Phase 7
Resume file: N/A
