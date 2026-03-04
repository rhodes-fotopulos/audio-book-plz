---
phase: 08-llm-intelligence-and-emotion
plan: 02
subsystem: attribution
tags: [speech-acts, regex, hybrid-detection, voice-baseline, dialogue]

requires:
  - phase: 08-01
    provides: "LLM model lifecycle (call_llm_structured with active model)"
provides:
  - "Hybrid regex+LLM speech-act classification (spoken/thought/shouted/whispered)"
  - "VoiceBaseline model on CharacterProfile (pace, tone, energy, typical_emotion)"
  - "SpeechActTag and SpeechActResult LLM schemas"
  - "Internal monologue tagged as 'thought' with character as speaker"
affects: [08-03, synthesis, emotion-system]

tech-stack:
  added: []
  patterns: [hybrid-regex-llm, two-pass-classification, confidence-thresholding]

key-files:
  created: [src/attribution/speech_acts.py, tests/test_speech_acts.py]
  modified: [src/attribution/models.py, src/attribution/extractor.py, src/attribution/attributor.py, src/attribution/__init__.py]

key-decisions:
  - "Regex narration context checked before text patterns (priority order)"
  - "ALL-CAPS exclusion list for common abbreviations (FBI, CEO, etc.)"
  - "Regex confidence 0.9 for narration tags, 0.7 for text patterns, 0.5 default"
  - "LLM called for segments with regex confidence < 0.8"
  - "LLM always wins over regex when it returns a result"

patterns-established:
  - "Two-pass classification: fast regex pass, then LLM refinement for ambiguous cases"
  - "Context window for regex: 2 segments before and after with 200-char truncation"

requirements-completed: [LLM-02, EMO-01]

duration: 12min
completed: 2026-03-04
---

# Plan 08-02: Hybrid Dialogue Detection Summary

**Regex+LLM speech-act classification (spoken/thought/shouted/whispered) with voice baselines for character profiles**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3
- **Files modified:** 6
- **Tests added:** 19

## Accomplishments
- VoiceBaseline model with 5 fields added to CharacterProfile (backward compatible)
- speech_act field added to SegmentAttribution and AttributedSegment (defaults to 'spoken')
- Regex detects shouted (narration tags, ALL-CAPS, !!), whispered (murmur/whisper), thought (thought verbs, 'to herself')
- LLM refines ambiguous segments (regex confidence < 0.8)
- Internal monologue attributed to thinking character, not narrator
- 19 speech-act tests covering all regex patterns and integration flow

## Task Commits

1. **Task 1: Extend data models** - `7fa41f9` (feat)
2. **Task 2: Create speech-act classification module** - `e7ba6a3` (feat)
3. **Task 3: Integration + voice baseline + tests** - `8b9014f` (feat)

## Files Created/Modified
- `src/attribution/models.py` - Added VoiceBaseline, speech_act fields, SpeechActTag/SpeechActResult schemas
- `src/attribution/speech_acts.py` - New hybrid regex+LLM classification module
- `src/attribution/extractor.py` - Updated extraction prompt for voice_baseline
- `src/attribution/attributor.py` - Integrated classify_speech_acts, updated internal monologue rule
- `src/attribution/__init__.py` - Added classify_speech_acts export
- `tests/test_speech_acts.py` - 19 tests for regex and integration

## Decisions Made
- Regex priority: narration context > text patterns > default spoken
- ALL-CAPS exclusion list prevents false positives for abbreviations
- LLM threshold at 0.8 confidence balances accuracy vs API cost

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Speech-act tags available for Plan 08-03 emotion system
- Post-processor will read speech_act field to apply volume/speed adjustments
- voice_baseline ready for emotion layer 1 (character defaults)

---
*Phase: 08-llm-intelligence-and-emotion*
*Completed: 2026-03-04*
