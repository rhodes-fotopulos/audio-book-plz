---
phase: 04-tts-synthesis-with-checkpoint-resume
plan: 03
subsystem: cli
tags: [cli, pipeline, dry-run, typer, rich, chatterbox-tts]

requires:
  - phase: 04-tts-synthesis-with-checkpoint-resume
    plan: 01
    provides: SynthesisConfig, TTSEngine, checkpoint system, models

provides:
  - synthesize CLI command with --chapter, --dry-run, -v/--verbose, --cpu flags
  - run_synthesize() pipeline orchestrator with dry-run estimates and KeyboardInterrupt handling
  - chatterbox-tts>=0.1.6 dependency in pyproject.toml
affects: [04-tts-synthesis-with-checkpoint-resume]

tech-stack:
  added: [chatterbox-tts]
  patterns:
    - "Dry-run Rich table with time/space estimates before committing to synthesis"
    - "KeyboardInterrupt -> checkpoint save message for overnight resume"
    - "CLI prerequisite validation (voice_map.json, attributed.json) with clear error messages"

key-files:
  created:
    - tests/test_cli_synthesize.py
  modified:
    - main.py
    - src/pipeline.py
    - pyproject.toml

key-decisions:
  - "Dry-run estimates use 3s avg audio/segment, 1.5x real-time factor, 48KB/s WAV size"
  - "run_synthesis() imported inside run_synthesize() to defer torch/chatterbox import until needed"
  - "run_full_pipeline() defers synthesis to separate command (requires voice_map.json from interactive match phase)"
  - "CLI validates prerequisites before calling pipeline to give clear error messages"

patterns-established:
  - "run_synthesize() as pipeline-level orchestrator, run_synthesis() as engine-level loop"
  - "Dry-run mode for all resource-intensive commands"
  - "KeyboardInterrupt handling with checkpoint resume messaging"

requirements-completed: [SYNTH-01, CLI-03, CLI-04]

duration: 4min
completed: 2026-03-03
---

# Plan 04-03: CLI Synthesize Command and Pipeline Integration Summary

**Wire synthesis engine into CLI and pipeline with dry-run estimates, prerequisite validation, and resume support**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Replaced stub synthesize CLI command with real implementation supporting --chapter N, --dry-run, -v/--verbose, --cpu flags
- Added run_synthesize() to pipeline.py with input validation, data loading, dry-run Rich table, synthesis execution, and KeyboardInterrupt handling
- Dry-run mode shows Rich table with chapter count, segment count, estimated audio duration, estimated wall time, and estimated disk space
- CLI validates voice_map.json and attributed.json exist before proceeding, with clear "Run 'match/attribute' first" error messages
- Added chatterbox-tts>=0.1.6 to pyproject.toml dependencies
- Updated run_full_pipeline() to show synthesize instructions instead of "not yet implemented"
- 5 CLI tests covering: missing voice_map, missing attributed, dry-run output, chapter filtering, help text

## Task Commits

1. **Task 1: CLI synthesize command and pipeline integration** - `ddc92cc` (feat)
2. **Task 2: CLI tests and dry-run validation** - `ddc92cc` (feat)

## Files Created/Modified
- `main.py` - Replaced stub synthesize with full CLI command (--chapter, --dry-run, -v, --cpu)
- `src/pipeline.py` - Added run_synthesize() orchestrator with dry-run estimates and KeyboardInterrupt handling
- `pyproject.toml` - Added chatterbox-tts>=0.1.6 dependency
- `tests/test_cli_synthesize.py` - 5 CLI integration tests with typer.testing.CliRunner

## Decisions Made
- Deferred torch/chatterbox import inside run_synthesize() to keep module import fast
- Dry-run estimates based on empirical Chatterbox performance: ~3s audio per segment, 1.5x real-time generation factor
- run_full_pipeline() cannot auto-chain synthesis because it requires voice_map.json from the interactive match phase

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
None.

## User Setup Required
- `pip install chatterbox-tts>=0.1.6` (or reinstall package) to get Chatterbox TTS and its transitive dependencies (torch, torchaudio, etc.)

## Next Phase Readiness
- All Phase 4 plans (04-01, 04-02, 04-03) complete
- Full synthesis pipeline accessible via `python main.py synthesize <book-dir>`
- Ready for Phase 5 (audio assembly) or Phase 4 verification

---
*Phase: 04-tts-synthesis-with-checkpoint-resume*
*Completed: 2026-03-03*
