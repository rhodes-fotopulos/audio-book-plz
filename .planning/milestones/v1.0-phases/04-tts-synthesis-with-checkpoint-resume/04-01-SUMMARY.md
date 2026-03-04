---
phase: 04-tts-synthesis-with-checkpoint-resume
plan: 01
subsystem: synthesis
tags: [chatterbox, tts, mps, apple-silicon, checkpoint, dataclass]

requires:
  - phase: 03-voice-character-matching
    plan: 03
    provides: VoiceMap with speaker_id, clip_path per character
provides:
  - SynthesisConfig with audiobook-tuned defaults (exag 0.25/0.45, cfg 0.3)
  - TTSEngine wrapping Chatterbox load/generate/cleanup lifecycle
  - Atomic WAV write with duration validation
  - Checkpoint create/save/load/validate with missing-WAV re-queuing
  - SegmentResult and SynthesisStats data models
affects: [04-tts-synthesis-with-checkpoint-resume]

tech-stack:
  added: []
  patterns:
    - "CPU-first model loading with component-wise MPS migration"
    - "Atomic file write: .tmp then os.rename"
    - "Late imports inside methods to avoid module-level torch loading"
    - "JSON checkpoint with atomic save for crash recovery"

key-files:
  created:
    - src/synthesis/__init__.py
    - src/synthesis/models.py
    - src/synthesis/tts_engine.py
    - src/synthesis/checkpoint.py
    - tests/test_synthesis_models.py
  modified: []

key-decisions:
  - "narration_exaggeration=0.25, dialogue_exaggeration=0.45 — low for narration, moderate for dialogue"
  - "cfg_weight=0.3 — lean natural per user decision"
  - "failure_threshold=0.15 — stop run if >15% segments fail"
  - "cleanup_interval=15 — gc.collect + MPS cache clear every 15 segments"
  - "Checkpoint stored as book_dir/checkpoint.json with atomic .tmp writes"
  - "WAV validation: min 0.1s duration, file size > 0 bytes"
  - "Ollama unload checks both default model and ollama.list() for any loaded models"

patterns-established:
  - "TTSEngine as single entry point for all Chatterbox operations"
  - "Late import pattern: torch/torchaudio/chatterbox imported inside methods only"
  - "Checkpoint dict tracks completed/failed segments with WAV paths and timing"
  - "validate_checkpoint re-queues missing WAVs for re-synthesis on resume"

requirements-completed: [SYNTH-01, SYNTH-02, SYNTH-03, SYNTH-05, SYNTH-06]

duration: 3min
completed: 2026-03-03
---

# Plan 04-01: Data Models, TTS Engine, and Checkpoint System Summary

**Chatterbox TTS engine with CPU-first MPS loading, atomic WAV writes, and JSON checkpoint system for crash-recoverable overnight synthesis**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- SynthesisConfig dataclass with audiobook-optimised defaults (narration exag 0.25, dialogue exag 0.45, cfg_weight 0.3)
- TTSEngine class wrapping full Chatterbox lifecycle: Ollama unload, CPU load, MPS migration, generate, atomic save, memory cleanup
- Checkpoint system with create/save/load/validate and missing-WAV re-queuing for crash recovery
- 6 tests covering config defaults, checkpoint round-trip, validation, and segment state transitions

## Task Commits

1. **Task 1: Data models and TTS engine with MPS support** - `427a69f` (feat)
2. **Task 2: Checkpoint system with resume and corruption detection** - `427a69f` (feat)

## Files Created/Modified
- `src/synthesis/models.py` - SynthesisConfig, SegmentResult, SynthesisStats dataclasses
- `src/synthesis/tts_engine.py` - TTSEngine with MPS-safe loading, generate, atomic WAV save
- `src/synthesis/checkpoint.py` - Checkpoint CRUD with atomic save and WAV validation
- `src/synthesis/__init__.py` - Public API exports
- `tests/test_synthesis_models.py` - 6 tests for models and checkpoint system

## Decisions Made
- narration_exaggeration=0.25 and dialogue_exaggeration=0.45 chosen for natural audiobook delivery
- cfg_weight=0.3 (low) prioritises natural pacing per user decision
- failure_threshold=0.15 balances between catching broken runs and allowing occasional failures
- cleanup_interval=15 based on research showing ~70MB leak per generation
- Checkpoint uses string keys for segment IDs (JSON compatibility)

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- TTSEngine ready for Plan 04-02 synthesizer loop to consume
- Checkpoint system ready for Plan 04-02 resume logic
- Models ready for Plan 04-03 CLI integration

---
*Phase: 04-tts-synthesis-with-checkpoint-resume*
*Completed: 2026-03-03*
