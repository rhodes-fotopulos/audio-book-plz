---
phase: 13-synthesis-performance
plan: 02
subsystem: synthesis
tags: [mlx, batch-processing, voice-cloning, qwen3-tts, performance, cli]

# Dependency graph
requires:
  - phase: 13-synthesis-performance
    plan: 01
    provides: "Per-character voice reference caching and character_name passthrough"
provides:
  - "--batch-by-character CLI flag for synthesize and convert commands"
  - "Batch-by-character iteration path in run_synthesis"
  - "Character-mode progress display (update_character/complete_character)"
  - "_process_segment helper eliminating duplication between chapter and batch paths"
affects: [synthesis-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: ["batch-by-character iteration: group by speaker, sort by segment count descending", "_process_segment extracted helper for shared retry/checkpoint logic"]

key-files:
  created: []
  modified:
    - src/synthesis/models.py
    - src/cli.py
    - src/pipeline.py
    - src/synthesis/synthesizer.py
    - src/synthesis/progress.py
    - tests/test_synthesizer.py
    - tests/test_synthesis_models.py

key-decisions:
  - "Speakers sorted by segment count descending to keep longest-running voice warm longest"
  - "Extracted _process_segment helper to share retry/checkpoint/speech-act logic between chapter and batch paths"
  - "WAV paths remain chapter-based in batch mode -- only iteration order changes, assembly unaffected"

patterns-established:
  - "_process_segment() as single-segment processing unit callable by both iteration strategies"
  - "update_character/complete_character on SynthesisProgress for character-mode display"

requirements-completed: [SYNTH-06]

# Metrics
duration: 5min
completed: 2026-03-07
---

# Phase 13 Plan 02: Batch-by-Character Synthesis Summary

**--batch-by-character CLI flag that reorders synthesis to process all segments per character consecutively, with _process_segment helper eliminating code duplication**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-07T07:38:50Z
- **Completed:** 2026-03-07T07:43:40Z
- **Tasks:** 2 (both TDD: RED + GREEN)
- **Files modified:** 7

## Accomplishments
- Added batch_by_character field to SynthesisConfig, wired through CLI (synthesize + convert) and pipeline (run_synthesize + run_full_pipeline)
- Extracted _process_segment helper from the chapter loop, eliminating ~150 lines of duplicated retry/checkpoint/speech-act logic
- Implemented batch-by-character iteration path: groups pending segments by speaker, sorts speakers by segment count descending, processes all segments for each speaker consecutively
- Added update_character/complete_character methods to SynthesisProgress for character-mode display
- 6 new tests: 2 config tests + 4 batch behavior tests (grouping, WAV paths, checkpoint resume, progress display)

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing config tests** - `54361f7` (test)
2. **Task 1 (GREEN): Config field, CLI flag, pipeline wiring** - `5d31b3a` (feat)
3. **Task 2 (RED): Failing batch behavior tests** - `30d093b` (test)
4. **Task 2 (GREEN): Batch loop, _process_segment helper, progress display** - `c917971` (feat)

_TDD tasks: RED then GREEN commits for each task._

## Files Created/Modified
- `src/synthesis/models.py` - Added batch_by_character: bool = False field
- `src/cli.py` - Added --batch-by-character flag to synthesize and convert commands
- `src/pipeline.py` - Wired batch_by_character through run_synthesize and run_full_pipeline
- `src/synthesis/synthesizer.py` - Extracted _process_segment helper, added batch-by-character iteration path
- `src/synthesis/progress.py` - Added update_character and complete_character methods
- `tests/test_synthesis_models.py` - 2 new config tests
- `tests/test_synthesizer.py` - 4 new batch behavior tests + multi-speaker helpers

## Decisions Made
- Speakers sorted by segment count descending -- keeps the longest-running voice warm longest for maximum cache benefit
- Extracted _process_segment() to avoid duplicating the retry loop, speech-act post-processing, and checkpoint save logic between chapter and batch paths
- WAV paths remain chapter-based (wavs/chNN/seg_NNNN.wav) in batch mode -- only the iteration order changes, so assembly is completely unaffected
- Used _run_segment() inner function (closure) to share mutable counter state between both iteration paths

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing test failures in test_llm_client.py and test_segmenter.py (unrelated to this plan's changes -- mock configuration issues)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 13 complete: reference caching (Plan 01) + batch-by-character synthesis (Plan 02) provide full synthesis performance optimization
- All synthesis-related tests pass without modification
- Milestone v1.2 (Voice Expression) synthesis pipeline complete

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 13-synthesis-performance*
*Completed: 2026-03-07*
