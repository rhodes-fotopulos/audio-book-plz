---
phase: 15-opinionated-profiles-and-expressive-clips
plan: 01
subsystem: attribution
tags: [llm-prompting, voice-profiles, distinctiveness, yaml-overrides, cli]

# Dependency graph
requires:
  - phase: 14-character-profile-merger-hardening
    provides: Stable merged character profiles with audit trail
provides:
  - Opinionated extraction prompt variant via --opinionated flag
  - LLM-based distinctiveness pass reviewing all profiles together
  - voice_overrides.yaml loading and application as final pipeline step
  - Pipeline order enforcement (extraction -> merge -> distinctiveness -> overrides -> write)
affects: [15-02-expressiveness-clip-selection, voice-matching]

# Tech tracking
tech-stack:
  added: [pyyaml (already installed)]
  patterns: [prompt-addendum-pattern, llm-review-pass, yaml-override-loading]

key-files:
  created:
    - src/attribution/distinctiveness.py
    - src/voice_overrides.py
    - tests/test_extractor_opinionated.py
    - tests/test_distinctiveness.py
    - tests/test_voice_overrides.py
  modified:
    - src/attribution/extractor.py
    - src/attribution/models.py
    - src/pipeline.py
    - src/cli.py

key-decisions:
  - "Opinionated mode appends addendum to existing prompt (not separate prompt variant)"
  - "Distinctiveness pass uses compact representation (name + voice_profile only) to fit Qwen 3.5 9B context"
  - "Batching at 12 characters per batch when cast exceeds 15 characters"
  - "Voice overrides merge fields (partial update) rather than replacing entire voice_profile"

patterns-established:
  - "Prompt addendum pattern: append mode-specific instructions to base prompt"
  - "LLM review pass: send all items for holistic review after individual extraction"
  - "YAML override pattern: load from book_dir, validate with Pydantic, apply last in pipeline"

requirements-completed: [PROF-01, PROF-02, PROF-03]

# Metrics
duration: 6min
completed: 2026-03-09
---

# Phase 15 Plan 01: Opinionated Profiles Summary

**Opinionated voice extraction with banned bland vocabulary, LLM distinctiveness pass pushing similar characters apart, and voice_overrides.yaml for user control**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-09T22:01:42Z
- **Completed:** 2026-03-09T22:08:10Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- OPINIONATED_ADDENDUM bans "moderate", "medium", "average", "normal", "standard", "typical", "ordinary" from voice profiles when --opinionated flag is set
- LLM distinctiveness pass sends all profiles to casting director prompt, validates output count, falls back gracefully on mismatch
- voice_overrides.yaml support with case-insensitive name matching and partial field merge
- Pipeline order enforced: extraction -> merge -> distinctiveness -> overrides -> write characters.json

## Task Commits

Each task was committed atomically:

1. **Task 1: Opinionated extraction prompt and distinctiveness pass**
   - `75fd655` (test: RED - failing tests for extraction and distinctiveness)
   - `d5f3953` (feat: GREEN - implement opinionated prompt, DistinctivenessResult model, distinctiveness.py)
2. **Task 2: Voice overrides and pipeline wiring**
   - `37726a2` (test: RED - failing tests for voice overrides)
   - `794ef7a` (feat: GREEN - voice_overrides.py, pipeline wiring, CLI flags)

_Note: TDD tasks each have two commits (test then feat)_

## Files Created/Modified
- `src/attribution/extractor.py` - Added OPINIONATED_ADDENDUM, get_extraction_prompt(), system_prompt parameter on _extract_chunk, opinionated cache key
- `src/attribution/models.py` - Added DistinctivenessResult Pydantic model
- `src/attribution/distinctiveness.py` - NEW: LLM-based distinctiveness pass with caching and batching
- `src/voice_overrides.py` - NEW: YAML loading, Pydantic validation, profile patching
- `src/pipeline.py` - Wired distinctiveness pass and voice overrides into run_attribute; added opinionated param
- `src/cli.py` - Added --opinionated flag to convert and attribute commands
- `tests/test_extractor_opinionated.py` - 7 tests for opinionated extraction
- `tests/test_distinctiveness.py` - 6 tests for distinctiveness pass
- `tests/test_voice_overrides.py` - 7 tests for voice overrides

## Decisions Made
- Opinionated mode appends addendum to existing prompt rather than maintaining separate prompt variant -- easier to maintain and test
- Distinctiveness pass sends compact representation (name + voice_profile fields only) to keep within Qwen 3.5 9B context window
- Batching threshold set at 15 characters, batch size 12 -- provides overlap room for context
- Voice overrides do partial merge (update specific fields) rather than full replacement -- user only needs to specify changed fields

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- CLI import verification (`from src.cli import app`) fails due to pre-existing missing `soundfile` module in test environment (audio_analyzer.py import chain). This is a pre-existing environment issue unrelated to this plan's changes. Source-level verification confirmed --opinionated flag is correctly wired.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Opinionated profiles and distinctiveness pass ready for use
- voice_overrides.yaml support ready for user testing
- Plan 02 (expressiveness clip selection) can proceed independently

## Self-Check: PASSED

All 5 created files verified present. All 4 commit hashes verified in git log.

---
*Phase: 15-opinionated-profiles-and-expressive-clips*
*Completed: 2026-03-09*
