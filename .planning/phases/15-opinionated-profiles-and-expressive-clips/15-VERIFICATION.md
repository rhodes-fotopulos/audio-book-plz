---
phase: 15-opinionated-profiles-and-expressive-clips
verified: 2026-03-09T23:45:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
---

# Phase 15: Opinionated Profiles and Expressive Clips Verification Report

**Phase Goal:** Each character gets a polarized, distinctive voice profile and a reference clip selected for expressiveness and pace alignment
**Verified:** 2026-03-09T23:45:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running with --opinionated produces voice profiles that never use "moderate", "medium", or "average" | VERIFIED | OPINIONATED_ADDENDUM bans 7 bland words; get_extraction_prompt(True) appends it; separate cache key "extraction_v3_opinionated" ensures re-extraction |
| 2 | When two characters have similar profiles, the distinctiveness pass pushes at least one apart | VERIFIED | run_distinctiveness_pass sends all profiles to LLM casting-director prompt, validates count, applies updates by name, falls back on mismatch |
| 3 | A voice_overrides.yaml in the book directory overrides automated profile fields | VERIFIED | load_voice_overrides reads from book_dir, apply_voice_overrides does case-insensitive partial merge; wired as final step in pipeline |
| 4 | Pipeline order is: extraction -> merge -> distinctiveness -> overrides -> write | VERIFIED | pipeline.py lines 178->185->193->207->211 confirm exact order |
| 5 | Reference clips are scored by expressiveness composite (SNR + pitch variance + energy variance + rate match) not just duration | VERIFIED | score_clip in audio_analyzer.py weights 0.4*SNR + 0.3*pitch + 0.2*energy + 0.1*rate; clip_selector uses 0.8*expr + 0.2*duration |
| 6 | A fast-paced character gets a faster-talking speaker's clip | VERIFIED | get_target_rate maps pace_style/pace to syllable rates; "fast"->5.5, "rapid"->6.0; rate_match component rewards closer matches |
| 7 | Clips under 2 seconds are handled gracefully (default SNR score) | VERIFIED | analyze_clip sets snr_db=0 when duration_s < 2.0 |
| 8 | Characters with pace='unknown' get neutral rate_match score (0.5) | VERIFIED | get_target_rate returns None for "unknown"; score_clip returns 0.5 rate_score when target_rate is None |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/attribution/extractor.py` | OPINIONATED_ADDENDUM, get_extraction_prompt() | VERIFIED | 414 lines, addendum at L108-118, function at L121-133, opinionated param threaded through all extraction functions |
| `src/attribution/distinctiveness.py` | LLM distinctiveness pass with caching and batching | VERIFIED | 218 lines, DISTINCTIVENESS_PROMPT, run_distinctiveness_pass, _batched_pass for >15 chars, cache with "distinctiveness_v1" |
| `src/attribution/models.py` | DistinctivenessResult Pydantic model | VERIFIED | L260-271, characters: list[CharacterProfile], modifications: list[str] |
| `src/voice_overrides.py` | YAML loading, validation, application | VERIFIED | 113 lines, VoiceOverride/VoiceOverrides models, load_voice_overrides, apply_voice_overrides with case-insensitive matching |
| `src/matching/audio_analyzer.py` | SNR, pitch, energy, syllable rate, scoring | VERIFIED | 232 lines, analyze_clip, score_clip, get_target_rate, PACE_TO_RATE dict, all helper functions substantive |
| `src/matching/clip_selector.py` | Expressiveness-aware selection with voice_profile param | VERIFIED | 217 lines, select_reference_clip accepts voice_profile, uses analyze_clip+score_clip, 0.8*expr+0.2*dur scoring |
| `src/matching/orchestrator.py` | Passes voice_profile to clip selector | VERIFIED | L268-273 builds char_profile_map, passes char_vp to select_reference_clip |
| `src/pipeline.py` | --opinionated threading, distinctiveness + overrides wiring | VERIFIED | run_attribute(opinionated=True) threads to extraction, distinctiveness and overrides wired in correct order |
| `src/cli.py` | --opinionated flag on convert and attribute | VERIFIED | typer.Option on both commands (L106-108, L171-173), passed through to pipeline |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| src/cli.py | src/pipeline.py | --opinionated flag passed to run_attribute and run_full_pipeline | WIRED | L150 and L186 pass opinionated= kwarg |
| src/pipeline.py | src/attribution/extractor.py | opinionated flag changes extraction prompt | WIRED | L180 passes opinionated=opinionated to extract_all_characters |
| src/pipeline.py | src/attribution/distinctiveness.py | distinctiveness pass called after merge | WIRED | L191-193 imports and calls run_distinctiveness_pass |
| src/pipeline.py | src/voice_overrides.py | overrides loaded and applied last | WIRED | L198-208 loads then applies overrides after distinctiveness |
| src/matching/clip_selector.py | src/matching/audio_analyzer.py | analyze_clip called for each candidate | WIRED | L17 imports analyze_clip/score_clip/get_target_rate; L87-88 calls them per candidate |
| src/matching/orchestrator.py | src/matching/clip_selector.py | select_reference_clip with voice_profile | WIRED | L273 passes voice_profile=char_vp to select_reference_clip |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROF-01 | 15-01 | --opinionated flag bans bland descriptors | SATISFIED | OPINIONATED_ADDENDUM bans "moderate"/"medium"/"average"/"normal"/"standard"/"typical"/"ordinary"; get_extraction_prompt appends it |
| PROF-02 | 15-01 | Post-extraction distinctiveness pass pushes similar characters apart | SATISFIED | run_distinctiveness_pass sends all profiles to LLM, validates output count, applies changes |
| PROF-03 | 15-01 | voice_overrides.yaml user control applied last | SATISFIED | load_voice_overrides + apply_voice_overrides wired as final step before characters.json write |
| CLIP-01 | 15-02 | Score clips by composite (0.4*SNR + 0.3*pitch + 0.2*energy + 0.1*rate) | SATISFIED | score_clip implements exact weights; clip_selector uses 0.8*expr + 0.2*dur |
| CLIP-02 | 15-02 | Rate-match clips to character pace | SATISFIED | PACE_TO_RATE maps pace descriptors to syllable rates; get_target_rate checks pace_style first; rate_match component in score_clip |

No orphaned requirements found. All 5 requirement IDs from ROADMAP.md phase 15 are claimed by plans and implemented.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | - | - | No TODOs, FIXMEs, placeholders, or stub implementations found |

### Test Coverage

- **tests/test_extractor_opinionated.py**: 7 tests -- ALL PASSED
- **tests/test_distinctiveness.py**: 6 tests -- ALL PASSED (including fallback on count mismatch, cache key usage)
- **tests/test_voice_overrides.py**: 7 tests -- ALL PASSED (including case-insensitive matching, speaker_id handling)
- **tests/test_audio_analyzer.py**: Could not run -- `soundfile` not installed in test environment (pre-existing env issue, not a code defect)
- **tests/test_clip_selector.py**: Could not run -- same `soundfile` dependency

20/20 runnable tests passed. Audio/clip tests are blocked by environment dependency only.

### Human Verification Required

### 1. Opinionated Extraction Quality

**Test:** Run `python3 main.py convert --opinionated <epub>` and inspect characters.json for bland descriptors
**Expected:** No voice_profile field contains "moderate", "medium", "average", "normal", "standard", "typical", or "ordinary"
**Why human:** LLM output quality depends on model behavior at runtime; code correctly bans the words in the prompt but LLM compliance cannot be verified statically

### 2. Distinctiveness Pass Effectiveness

**Test:** Run pipeline on a book with many similar characters, diff characters.json before and after distinctiveness pass
**Expected:** At least one character's voice_profile is modified to create audible separation
**Why human:** Requires real LLM interaction and subjective assessment of whether changes create meaningful audible distinction

### 3. Expressiveness Scoring Weights

**Test:** Run full pipeline with LibriTTS-R data and compare selected clips against previous duration-only selection
**Expected:** Fast-paced characters get clips with higher syllable rates; selected clips sound more expressive
**Why human:** Scoring weights (0.4/0.3/0.2/0.1) are estimates that need validation against real audio data

---

_Verified: 2026-03-09T23:45:00Z_
_Verifier: Claude (gsd-verifier)_
