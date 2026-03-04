---
phase: 04-tts-synthesis-with-checkpoint-resume
plan: 02
subsystem: synthesis
tags: [synthesizer, progress, rich, retry, checkpoint, memory-management]

requires:
  - phase: 04-tts-synthesis-with-checkpoint-resume
    plan: 01
    provides: TTSEngine, SynthesisConfig, checkpoint system, models
provides:
  - run_synthesis() main loop with chapter iteration, retry, failure threshold, end-of-run retry pass
  - SynthesisProgress with Rich progress bars, ETA, stats table, synthesis.log
  - Oversized segment splitting at NLTK sentence boundaries
  - Chatterbox crash recovery with one restart attempt
affects: [04-tts-synthesis-with-checkpoint-resume]

tech-stack:
  added: []
  patterns:
    - "Rich Progress with chapter and segment tasks, rolling ETA"
    - "synthesis.log with timestamped pipe-delimited entries"
    - "End-of-run retry pass for failed segments"
    - "Failure threshold gate (stop if >15% fail after 20 segments)"

key-files:
  created:
    - src/synthesis/progress.py
    - src/synthesis/synthesizer.py
    - tests/test_synthesizer.py
  modified:
    - src/synthesis/__init__.py

key-decisions:
  - "Retry pass only runs if failure rate is below threshold (prevents retrying when run is fundamentally broken)"
  - "Memory cleanup every 15 segments via config.cleanup_interval"
  - "Threshold check requires minimum 20 segments before evaluating (avoids false positives on early failures)"
  - "FakeTensor test helper avoids torch dependency in unit tests"

patterns-established:
  - "run_synthesis() as single entry point for all synthesis operations"
  - "SynthesisProgress wraps all user-facing output during synthesis"
  - "synthesis.log always written regardless of verbose mode"
  - "_split_long_text() uses NLTK for safety net on oversized segments"

requirements-completed: [SYNTH-01, SYNTH-04, SYNTH-05, SYNTH-06, CLI-04]

duration: 4min
completed: 2026-03-03
---

# Plan 04-02: Core Synthesis Loop, Progress Display, and synthesis.log Summary

**Chapter-by-chapter synthesis loop with Rich progress, retry logic, failure threshold, end-of-run retry pass, and synthesis.log for overnight debugging**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- run_synthesis() processes segments chapter-by-chapter with voice lookup, retry logic (up to max_retries), and end-of-run retry pass
- SynthesisProgress provides Rich chapter/segment progress bars with rolling ETA, verbose per-segment logging, and Rich stats table on completion
- synthesis.log written alongside WAVs with timestamped entries for every event (START, CHAPTER, OK, FAIL, RETRY, DONE)
- Failure threshold stops run if >15% segments fail after minimum 20 processed
- Chatterbox crash recovery: unload and reload model once, exit cleanly on second crash
- Oversized segments (>280 chars) split at NLTK sentence boundaries and concatenated
- 5 tests covering checkpoint resume, retry, threshold, chapter filter, and end-of-run retry pass

## Task Commits

1. **Task 1: Progress display and synthesis.log writer** - `2d1e73b` (feat)
2. **Task 2: Core synthesis loop with retry, failure threshold, and resume** - `2d1e73b` (feat)

## Files Created/Modified
- `src/synthesis/progress.py` - SynthesisProgress with Rich bars, ETA, stats table, synthesis.log
- `src/synthesis/synthesizer.py` - run_synthesis() main loop with all modes
- `src/synthesis/__init__.py` - Added run_synthesis export
- `tests/test_synthesizer.py` - 5 tests with mocked TTSEngine

## Decisions Made
- Retry pass gated by failure threshold to avoid retrying when run is fundamentally broken
- Minimum 20 segments before evaluating failure threshold (avoids false positives)
- FakeTensor helper avoids torch dependency in tests (shape property returns tuple)

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
- End-of-run retry test initially failed because test's failure_threshold (0.15 default) was too low for 1-in-5 failure rate (20%) — fixed by setting threshold to 0.5 in test

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- run_synthesis() ready for Plan 04-03 CLI integration
- All synthesis features (retry, threshold, progress, checkpoint) tested with mocked engine

---
*Phase: 04-tts-synthesis-with-checkpoint-resume*
*Completed: 2026-03-03*
