---
phase: 13-synthesis-performance
plan: 01
subsystem: synthesis
tags: [mlx, caching, voice-cloning, qwen3-tts, performance]

# Dependency graph
requires:
  - phase: 04-synthesis
    provides: "QwenTTSEngine and synthesis pipeline"
provides:
  - "Per-character voice reference caching in QwenTTSEngine"
  - "speech_tokenizer.encode identity-based cache"
  - "character_name passthrough from synthesizer to engine"
affects: [13-02, synthesis-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: ["two-layer cache: load_audio + encode wrapping", "id()-based cache for mx.array identity"]

key-files:
  created: []
  modified:
    - src/synthesis/qwen_engine.py
    - src/synthesis/synthesizer.py
    - tests/test_synthesizer.py

key-decisions:
  - "Cache keyed by character_name (falls back to ref_clip_path when no name provided)"
  - "encode cache uses id() of mx.array since same object is reused per character from _ref_cache"
  - "Caches preserved through cleanup_memory() but cleared on unload() -- ref arrays are small (~100KB)"

patterns-established:
  - "character_name kwarg on engine.generate() for cache keying (non-abstract, QwenTTSEngine-only)"
  - "_generate_segment_audio passes character_name through all 3 call sites"

requirements-completed: [SYNTH-05]

# Metrics
duration: 4min
completed: 2026-03-07
---

# Phase 13 Plan 01: Reference Cache Summary

**Per-character voice reference caching via two-layer cache (load_audio + encode) eliminating redundant I/O and codec encoding per segment**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-07T07:32:32Z
- **Completed:** 2026-03-07T07:36:27Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 3

## Accomplishments
- Added `_ref_cache` dict to QwenTTSEngine that stores loaded mx.array per character, loaded once via `load_audio()` and reused for all segments
- Wrapped `speech_tokenizer.encode` with id()-based cache after model load for Layer 2 encoding cache
- Wired `character_name` through `_generate_segment_audio` at all 3 call sites in `run_synthesis`
- 5 new tests covering cache reuse, log messages, multi-character isolation, and cleanup on unload

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for reference cache** - `76a9960` (test)
2. **Task 1 (GREEN): Implement reference cache and wire character_name** - `67a5366` (feat)

_TDD task: RED then GREEN commits._

## Files Created/Modified
- `src/synthesis/qwen_engine.py` - Added _ref_cache, _encode_cache, character_name kwarg, two-layer cache logic, cache clearing on unload
- `src/synthesis/synthesizer.py` - Added character_name parameter to _generate_segment_audio, passed at all 3 call sites
- `tests/test_synthesizer.py` - 5 new tests for cache behavior

## Decisions Made
- Cache keyed by character_name with fallback to ref_clip_path for backward compatibility
- encode cache uses Python id() since the same mx.array object is reused per character from _ref_cache
- Caches survive cleanup_memory() but clear on unload() -- ref arrays are small (~100KB each)
- Did not modify TTSEngineBase abstract interface; character_name is QwenTTSEngine-only kwarg

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Test patches needed to target `mlx_audio.utils.load_audio` instead of module-level attribute since the import happens inside the generate() method at call time

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Reference cache complete, ready for plan 02 (batch/streaming optimizations)
- All existing tests pass without modification

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 13-synthesis-performance*
*Completed: 2026-03-07*
