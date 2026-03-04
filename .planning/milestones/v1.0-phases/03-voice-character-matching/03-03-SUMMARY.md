---
phase: 03-voice-character-matching
plan: 03
subsystem: matching
tags: [orchestrator, cli, pipeline, voice-map, rich-table, clip-selector]

requires:
  - phase: 03-voice-character-matching
    plan: 01
    provides: Speaker index, models, cast classification
  - phase: 03-voice-character-matching
    plan: 02
    provides: LLM trait matcher, embedding fallback, dedup enforcement
provides:
  - Full matching orchestrator (run_matching)
  - CLI match command with input validation and env var support
  - Rich table display of voice assignments with confirmation prompt
  - voice_map.json persistence with re-run caching
  - Reference clip selector for LibriTTS-R audio
affects: [03-voice-character-matching, 04-tts-synthesis]

tech-stack:
  added: []
  patterns:
    - "Rich table display with yellow-highlighted warnings"
    - "typer.confirm for user approval before writing output"
    - "Environment variable fallback for data directory paths"
    - "Re-run caching via existing voice_map.json detection"

key-files:
  created:
    - src/matching/clip_selector.py
    - src/matching/orchestrator.py
    - tests/test_matching_orchestrator.py
  modified:
    - src/matching/__init__.py
    - src/pipeline.py
    - main.py

key-decisions:
  - "Largest WAV file used as reference clip proxy for longest duration (24kHz proportional)"
  - "Minimum clip size warning at 120KB (~5 seconds at 24kHz mono 16-bit)"
  - "Embedding pre-ranking when >50 candidates: top 30 sent to LLM for final selection"
  - "Minor characters exclude only major-character speaker IDs from assigned_ids"
  - "User rejection exits with code 0 and prints edit-and-rerun instructions"
  - "Ollama model unloaded after matching to free GPU memory"

patterns-established:
  - "VoiceMap as single-source-of-truth output consumed by Phase 4 synthesis"
  - "Pipeline phases return file paths for chaining"
  - "CLI commands validate prerequisites before running (characters.json, attributed.json, df1_en.csv)"

requirements-completed: [VOICE-01, VOICE-02, VOICE-05]

duration: 5min
completed: 2026-03-03
---

# Plan 03-03: Orchestrator, CLI, and Pipeline Integration Summary

**Full matching pipeline wired end-to-end: orchestrator, clip selector, CLI match command with Rich table display, user confirmation, and voice_map.json persistence**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 3 (2 auto + 1 checkpoint auto-approved)
- **Files modified:** 6

## Accomplishments
- Clip selector finds longest WAV per speaker across LibriTTS-R splits with size-based duration proxy
- Orchestrator runs 10-step pipeline: cache check, load, classify, embed, match narrator, match major (LLM), match minor (embedding), dedup, clip select, return VoiceMap
- CLI match command with --libritts-data and --libritts-audio options, env var support, input path validation
- Rich table displays character name, speaker ID, method, confidence, reasoning with yellow-highlighted warnings
- User confirmation prompt: y writes voice_map.json, n exits with edit-and-rerun instructions
- Re-run caching: existing voice_map.json returned immediately without LLM calls
- Pipeline integration: run_match() added to pipeline.py, run_full_pipeline updated with informative message
- 7 orchestrator tests covering caching, pipeline stages, LLM fallback, and CLI validation

## Task Commits

1. **Task 1: Clip selector and matching orchestrator** - `c90164b` (feat)
2. **Task 2: Pipeline integration, CLI command, and display/confirmation** - `d7e0d00` (feat)
3. **Task 3: Verify voice matching end-to-end** - auto-approved (checkpoint)

## Files Created/Modified
- `src/matching/clip_selector.py` - select_reference_clip with WAV size-based selection
- `src/matching/orchestrator.py` - run_matching with full 10-step pipeline
- `src/matching/__init__.py` - Added run_matching and select_reference_clip exports
- `src/pipeline.py` - Added run_match() with Rich table, confirmation, and voice_map.json write
- `main.py` - Real match command replacing stub, with --libritts-data/--libritts-audio options
- `tests/test_matching_orchestrator.py` - 7 tests for caching, pipeline order, fallback, CLI validation

## Decisions Made
- Embedding pre-ranking limits >50 candidates to top 30 before LLM evaluation
- Minor characters only exclude major-character speaker IDs from consideration (can share with other minors)
- Placeholder clip paths used when --libritts-audio not provided: "AUDIO_DIR/{speaker_id}/longest.wav"
- Book slug derived from book_dir.name for VoiceMap metadata

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
None.

## User Setup Required
- LibriTTS-P data (df1_en.csv, df2_en.csv, df3_en.csv) required at --libritts-data path
- LibriTTS-R audio optional for reference clip selection

## Next Phase Readiness
- voice_map.json ready for Phase 4 TTS synthesis to consume
- Each VoiceAssignment includes speaker_id, clip_path, and confidence for synthesis decisions
- Narrator assignment separate from character assignments for different TTS handling

---
*Phase: 03-voice-character-matching*
*Completed: 2026-03-03*
