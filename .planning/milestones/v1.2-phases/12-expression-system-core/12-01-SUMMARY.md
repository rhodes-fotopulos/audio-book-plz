---
phase: 12-expression-system-core
plan: 01
subsystem: pipeline
tags: [emotion-removal, speech-act, feature-flags, qwen3-tts]

# Dependency graph
requires:
  - phase: 11-data-model-unification
    provides: VoiceProfile model and attribution pipeline
provides:
  - Pipeline without emotion annotation system
  - speech_act_fx feature flag (CLI -> SynthesisConfig -> synthesizer)
  - use_llm parameter on classify_speech_acts (default regex-only)
affects: [12-expression-system-core]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Feature flag pattern for optional post-processing (speech_act_fx)
    - use_llm parameter pattern for optional LLM refinement

key-files:
  created: []
  modified:
    - src/pipeline.py
    - src/cli.py
    - src/synthesis/models.py
    - src/synthesis/synthesizer.py
    - src/synthesis/post_processor.py
    - src/attribution/speech_acts.py
    - tests/test_post_processor.py
    - tests/test_speech_acts.py

key-decisions:
  - "Emotion system fully removed - Qwen3-TTS Base cannot combine voice cloning with emotion instructions"
  - "Speech-act post-processing OFF by default (speech_act_fx=False) because LUFS normalization undoes volume deltas"
  - "Speech-act LLM refinement OFF by default (use_llm=False) to save LLM calls - regex-only classification"

patterns-established:
  - "Feature flag wiring: CLI --flag -> pipeline param -> config dataclass -> gated code path"

requirements-completed: [EXPR-01, EXPR-02, EXPR-03]

# Metrics
duration: 12min
completed: 2026-03-07
---

# Phase 12 Plan 01: Emotion Removal and Speech-Act Feature Flags Summary

**Removed emotion annotation system (scene moods + line overrides) and made speech-act post-processing and LLM refinement opt-in via feature flags**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-07T07:01:06Z
- **Completed:** 2026-03-07T07:13:03Z
- **Tasks:** 2
- **Files modified:** 13 (7 deleted, 6 modified/created)

## Accomplishments
- Deleted entire emotion module (4 source files + 1 test file) and cleaned all pipeline references
- Added speech_act_fx=False to SynthesisConfig, gated all 3 post-processing call sites in synthesizer.py
- Added --speech-act-fx CLI flag to synthesize and convert commands, wired through pipeline
- Added use_llm=False parameter to classify_speech_acts, LLM pass skipped by default
- All 136 tests pass (excluding 3 pre-existing failures in unrelated modules)

## Task Commits

Each task was committed atomically:

1. **Task 1: Delete emotion module and clean all references** - `d340bc4` (feat)
2. **Task 2: Add speech-act-fx flag and make LLM refinement optional** - `b143ba4` (feat)

## Files Created/Modified
- `src/attribution/emotion/` - DELETED (4 files: __init__.py, models.py, scene_mood.py, overrides.py)
- `tests/test_emotion.py` - DELETED
- `src/pipeline.py` - Removed emotion annotation block, removed unused imports, added speech_act_fx wiring
- `src/cli.py` - Added --speech-act-fx flag to synthesize and convert commands
- `src/synthesis/models.py` - Added speech_act_fx=False field to SynthesisConfig
- `src/synthesis/synthesizer.py` - Gated all 3 apply_speech_act_adjustments calls behind config.speech_act_fx
- `src/synthesis/post_processor.py` - Updated docstring (removed scene mood references)
- `src/attribution/speech_acts.py` - Added use_llm=False parameter, gated LLM pass
- `tests/test_post_processor.py` - Added tests for speech_act_fx flag
- `tests/test_speech_acts.py` - Added tests for use_llm=False, updated existing test for use_llm=True

## Decisions Made
- Emotion system fully removed (not just disabled) since Qwen3-TTS Base model cannot use it
- Speech-act post-processing defaults to OFF because LUFS normalization undoes volume deltas
- Speech-act LLM refinement defaults to OFF (regex-only) to avoid unnecessary LLM calls
- Updated existing test_llm_overrides test to explicitly pass use_llm=True (behavioral change, not a bug)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test for use_llm default change**
- **Found during:** Task 2 (speech-act flag implementation)
- **Issue:** test_llm_overrides_low_confidence_regex called classify_speech_acts without use_llm=True, so LLM was never invoked with new default
- **Fix:** Added use_llm=True to the test call to match its intent
- **Files modified:** tests/test_speech_acts.py
- **Verification:** All 39 speech-act and post-processor tests pass
- **Committed in:** b143ba4 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary correction for test to match new default behavior. No scope creep.

## Issues Encountered
- Pre-existing test failures in test_llm_client.py (RAM-based model selection) and test_segmenter.py (dialogue block processing) are unrelated to this plan's changes

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline runs cleanly without emotion module
- Speech-act post-processing can be enabled with --speech-act-fx when needed
- Ready for Phase 12 Plan 02 (if applicable)

---
*Phase: 12-expression-system-core*
*Completed: 2026-03-07*
