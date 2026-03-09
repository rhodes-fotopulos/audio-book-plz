---
phase: 15-opinionated-profiles-and-expressive-clips
plan: 02
subsystem: matching
tags: [audio-analysis, snr, pitch-variance, energy-variance, syllable-rate, expressiveness, clip-selection]

# Dependency graph
requires:
  - phase: 14-character-profile-merger-hardening
    provides: "Merged character profiles with voice_profile fields"
provides:
  - "audio_analyzer.py: SNR, pitch variance, energy variance, syllable rate from WAV files"
  - "Expressiveness composite scoring (0.4*SNR + 0.3*pitch + 0.2*energy + 0.1*rate)"
  - "Pace-to-rate mapping from VoiceProfile to target syllable rate"
  - "select_reference_clip with voice_profile parameter for rate matching"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "numpy+soundfile audio signal analysis (no librosa)"
    - "Composite scoring with normalized weighted components"
    - "Autocorrelation-based pitch estimation"
    - "Energy-envelope syllable rate estimation"

key-files:
  created:
    - src/matching/audio_analyzer.py
    - tests/test_audio_analyzer.py
    - tests/test_clip_selector.py
  modified:
    - src/matching/clip_selector.py
    - src/matching/orchestrator.py

key-decisions:
  - "Hardcoded weights 0.4/0.3/0.2/0.1 as constants (not configurable) -- per RESEARCH.md recommendation"
  - "80% expressiveness + 20% duration proximity for final clip score -- keeps duration as tiebreaker"
  - "PACE_TO_RATE maps pace_style first, pace second -- more specific descriptor takes precedence"

patterns-established:
  - "Audio analysis via numpy autocorrelation and RMS envelope -- no heavy deps like librosa"
  - "Composite scoring pattern: normalize each component to 0-1, apply fixed weights"

requirements-completed: [CLIP-01, CLIP-02]

# Metrics
duration: 4min
completed: 2026-03-09
---

# Phase 15 Plan 02: Expressiveness-Aware Clip Selection Summary

**Composite expressiveness scoring (SNR + pitch + energy + rate) replaces duration-only clip selection, with pace-matched rate targeting from character voice profiles**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-09T22:01:49Z
- **Completed:** 2026-03-09T22:06:11Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- audio_analyzer.py computes 5 metrics (SNR, pitch variance, energy variance, syllable rate, duration) from WAV files using numpy+soundfile
- Clip selection now uses 80% expressiveness composite + 20% duration proximity instead of duration-only scoring
- Orchestrator passes character voice_profile to clip selector for pace-based rate matching
- Full backward compatibility maintained -- callers without voice_profile still work with neutral rate score

## Task Commits

Each task was committed atomically:

1. **Task 1: Audio analyzer and expressiveness scoring** - `dc55249` (feat, TDD)
2. **Task 2: Rework clip selector and wire into orchestrator** - `fa07798` (feat)

## Files Created/Modified
- `src/matching/audio_analyzer.py` - NEW: SNR, pitch variance, energy variance, syllable rate estimation, composite scoring, pace-to-rate mapping
- `src/matching/clip_selector.py` - Reworked scoring from duration-only to expressiveness composite; added voice_profile parameter
- `src/matching/orchestrator.py` - Step 9 now passes character voice_profile to select_reference_clip
- `tests/test_audio_analyzer.py` - NEW: 15 tests covering all analysis functions and scoring
- `tests/test_clip_selector.py` - NEW: 5 tests for backward compat, expressiveness selection, and fallback

## Decisions Made
- Hardcoded weights (0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match) as constants rather than configurable -- premature configuration adds complexity per RESEARCH.md
- Final clip score is 80% expressiveness + 20% duration proximity -- keeps duration as useful tiebreaker without dominating
- pace_style takes precedence over pace in rate mapping -- more specific descriptors like "rapid" or "languid" are more informative than coarse "fast"/"slow"

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Expressiveness scoring weights are unvalidated against real LibriTTS-R data -- may need tuning after first full pipeline run
- audio_analyzer normalization ranges (SNR 0-40 dB, pitch_var 0-5000, energy_var 0-0.01) are estimates that should be checked against actual distributions

---
*Phase: 15-opinionated-profiles-and-expressive-clips*
*Completed: 2026-03-09*
