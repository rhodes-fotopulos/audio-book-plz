---
phase: 03-voice-character-matching
plan: 01
subsystem: matching
tags: [pydantic, libritts-p, csv, voice-matching]

requires:
  - phase: 02-llm-character-extraction-and-speaker-attribution
    provides: CharacterProfile model with voice_qualities, attribution segments with speaker field
provides:
  - Pydantic models for voice matching (VoiceAssignment, VoiceMap, SpeakerAnnotation, CastClassification)
  - LibriTTS-P speaker index loader merging 3 annotator CSVs
  - Gender/age pre-filtering for candidate selection
  - Cast classification (major/minor by dialogue count)
  - Narrator mode detection (first-person vs third-person)
affects: [03-voice-character-matching]

tech-stack:
  added: []
  patterns:
    - "Pipe-delimited CSV parsing for LibriTTS-P annotations"
    - "Gender inference from perception trait keywords"
    - "Soft age filtering with fallback to gender-only"
    - "First-person detection via pronoun regex sampling"

key-files:
  created:
    - src/matching/__init__.py
    - src/matching/models.py
    - src/matching/speaker_index.py
    - tests/test_matching_models.py
  modified: []

key-decisions:
  - "Gender inferred from any trait containing 'masculine' or 'feminine' (including 'very masculine')"
  - "Age filter is soft — falls back to gender-only if no age keywords match"
  - "First-person narrator detected by >30% pronoun ratio in sampled narration segments"
  - "Large cast threshold adjusts: max(default, total_dialogue // 20) for >20 characters"

patterns-established:
  - "Speaker index keyed by string speaker_id for consistency with LibriTTS path format"
  - "Annotator agreement tracked as dict[str, int] for downstream confidence weighting"
  - "CastClassification includes narrator_mode to drive narrator voice selection strategy"

requirements-completed: [VOICE-01, VOICE-05]

duration: 3min
completed: 2026-03-03
---

# Plan 03-01: Voice Matching Foundation Summary

**Pydantic data models defining voice_map.json schema, LibriTTS-P speaker index with 3-annotator merge and gender/age filtering, cast classification by dialogue count**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Four Pydantic models (SpeakerAnnotation, VoiceAssignment, VoiceMap, CastClassification) with strict/non-strict modes matching Phase 2 conventions
- Speaker index loader merging df1/df2/df3 annotator CSVs with annotator agreement tracking
- Candidate filtering by gender (mandatory) and age (soft fallback) narrowing 2,443 speakers to manageable candidate pools
- Cast classification with adaptive threshold for large casts and first-person narrator detection
- 27 tests covering all models, loading, filtering, and classification

## Task Commits

1. **Task 1: Data models for voice matching** - `e5cc53e` (feat)
2. **Task 2: Speaker index loader with filtering and cast classification** - `984a7cc` (test)

## Files Created/Modified
- `src/matching/__init__.py` - Public API exports (load_speaker_index, filter_candidates, classify_cast)
- `src/matching/models.py` - VoiceAssignment, VoiceMap, SpeakerAnnotation, CastClassification
- `src/matching/speaker_index.py` - Speaker index loading, gender/age filtering, cast classification
- `tests/test_matching_models.py` - 27 tests covering all models and functions

## Decisions Made
- Gender inferred from any trait containing "masculine" or "feminine" (including modifiers like "very")
- Age filter is soft — falls back to all gender-matched speakers if no age keywords match
- First-person narrator detected by >30% first-person pronoun ratio in sampled narration (20 segments)
- Large cast threshold auto-adjusts: max(default, total_dialogue_lines // 20)

## Deviations from Plan
None - plan executed as specified.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Models ready for trait_matcher.py and embedding_matcher.py (Plan 03-02)
- Speaker index loader ready for orchestrator (Plan 03-03)
- CastClassification drives major/minor matching strategy

---
*Phase: 03-voice-character-matching*
*Completed: 2026-03-03*
