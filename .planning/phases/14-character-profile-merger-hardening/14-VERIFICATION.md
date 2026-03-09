---
phase: 14-character-profile-merger-hardening
verified: 2026-03-09T21:00:00Z
status: passed
score: 7/7 must-haves verified
re_verification: false
human_verification:
  - test: "Run pipeline on Pride and Prejudice and verify Mrs. Bennet, Elizabeth, Jane are separate profiles"
    expected: "Each family member has their own profile with no cross-contamination of aliases"
    why_human: "End-to-end LLM behavior on real text cannot be verified programmatically"
  - test: "Check merge_audit.json output for a real book run and verify reject decisions for surname pairs"
    expected: "Mr. Bennet and Mrs. Bennet show as rejected with clear reasoning"
    why_human: "Requires running full pipeline with LLM against real book data"
  - test: "Verify co-occurring characters with different identities are not merged by the LLM arbiter"
    expected: "Characters appearing in same chapter dialogue scenes are kept separate when they are different people"
    why_human: "LLM arbiter behavior depends on model quality and prompt effectiveness -- cannot verify without running inference"
---

# Phase 14: Character Profile Merger Hardening Verification Report

**Phase Goal:** Characters are correctly deduplicated with no cross-contamination, and every merge decision is auditable
**Verified:** 2026-03-09T21:00:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Characters sharing only a surname but with different titles/first-names are never merged | VERIFIED | `_names_share_surname_only` blocks candidate generation in Stage 2; 6 tests in TestSurnameExclusion all pass |
| 2 | An alias that matches another profile's canonical name is blocked from being added | VERIFIED | `_merge_two_profiles` checks `all_canonical_names` and removes blocked aliases; TestCrossNameExclusion tests pass |
| 3 | Co-occurrence data is passed as a signal to the LLM arbiter, not used as a binary gate | VERIFIED | `_get_cooccurrence_chapters` output included in LLM prompt text; MERGE_ARBITER_PROMPT says "Co-occurrence in the same chapter does NOT automatically mean different people"; TestCooccurrenceSignal::test_cooccurrence_not_binary_gate passes |
| 4 | Traits are capped at 30 after any merge, with overflow logged as a warning | VERIFIED | `_merge_two_profiles` checks `len(all_traits) > TRAIT_CAP` and truncates; appends warning to audit; 3 tests in TestTraitCap pass |
| 5 | Post-merge validation flags profiles with >5 aliases, >50 traits, or alias-canonical cross-contamination | VERIFIED | `_validate_merged_profiles` checks all three thresholds and appends to `audit.warnings`; 4 tests in TestPostMergeValidation pass |
| 6 | merge_audit.json is written alongside characters.json after every pipeline run | VERIFIED | pipeline.py line 198-201 writes `merge_audit.json` from `merge_audit.model_dump()`; console output shows path |
| 7 | Every merge decision (accept and reject) is recorded with stage, reason, and confidence | VERIFIED | `_record_decision` called in all 4 stages (exact_name, candidate_generation, llm_arbiter, cross_name_exclusion); MergeDecision model has stage/reason/confidence fields; TestAuditTrail::test_merge_characters_records_exact_decisions passes |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/attribution/models.py` | MergeDecision and MergeAudit Pydantic models | VERIFIED | Lines 260-316; both models have all required fields with docstrings |
| `src/attribution/merger.py` | Restructured 4-stage pipeline with LLM arbiter and full audit trail | VERIFIED | 959 lines; contains `MERGE_ARBITER_PROMPT`, `_generate_candidate_pairs`, `_arbitrate_with_llm`, `_validate_merged_profiles`, union-find merge groups |
| `src/attribution/extractor.py` | Hardened extraction prompt with WRONG/RIGHT negative examples | VERIFIED | Lines 71-88; WRONG examples cover daughters, sisters, mothers, unconfirmed aliases, letter recipients; RIGHT examples show correct usage |
| `tests/test_merger.py` | Test scaffold covering MERGE-01 through MERGE-08 | VERIFIED | 30 tests across 8 test classes; all 30 passing, 0 skipped |
| `src/pipeline.py` | Pipeline writes merge_audit.json | VERIFIED | Lines 197-208; writes JSON, shows path, displays warning count |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_merger.py` | `src/attribution/models.py` | `from src.attribution.models import MergeDecision, MergeAudit` | WIRED | Line 23-28 imports both models and uses them extensively |
| `tests/test_merger.py` | `src/attribution/merger.py` | `from src.attribution.merger import merge_characters` | WIRED | Line 29-36 imports merge_characters and helper functions |
| `src/attribution/merger.py` | `src/attribution/models.py` | `from src.attribution.models import MergeDecision, MergeAudit` | WIRED | Line 24-29 imports both; used throughout all stages |
| `src/attribution/merger.py` | `src/attribution/llm_client.py` | `call_llm_structured` for merge arbitration | WIRED | Line 22 import; line 687-691 calls `call_llm_structured` with `MergeArbiterResult` schema |
| `src/pipeline.py` | `src/attribution/merger.py` | `merge_characters` returns profiles + audit | WIRED | Line 183 unpacks tuple: `characters, merge_audit = merge_characters(...)` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MERGE-01 | 14-01, 14-02 | Per-stage logging of every merge decision | SATISFIED | `_record_decision` helper records MergeDecision at every stage; audit returned from merge_characters |
| MERGE-02 | 14-02 | Post-merge validation flags >5 aliases, >50 traits, alias-canonical cross | SATISFIED | `_validate_merged_profiles` function with 3 checks; TestPostMergeValidation passes |
| MERGE-03 | 14-01, 14-02 | Write merge_audit.json alongside characters.json | SATISFIED | pipeline.py writes `merge_audit.json` at line 198; TestAuditOutput verifies serialization |
| MERGE-04 | 14-02 | Cross-name exclusion on aliases | SATISFIED | `_merge_two_profiles` blocks aliases matching canonical names; TestCrossNameExclusion passes |
| MERGE-05 | 14-02 | Co-occurrence as signal (not binary gate) | SATISFIED | `_get_cooccurrence_chapters` feeds into LLM prompt; prompt explicitly says co-occurrence != different; TestCooccurrenceSignal passes |
| MERGE-06 | 14-02 | Trait cap at 30 | SATISFIED | `_merge_two_profiles` caps at `TRAIT_CAP=30`; logs warning; TestTraitCap passes |
| MERGE-07 | 14-02 | Surname-only exclusion | SATISFIED | `_names_share_surname_only` blocks candidate generation; 6 edge case tests pass |
| MERGE-08 | 14-01 | Extraction prompt hardening with negative examples | SATISFIED | EXTRACTION_SYSTEM_PROMPT contains WRONG/RIGHT sections with family confusion examples; cache key bumped to `extraction_v3`; TestExtractionPrompt passes |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | - | - | - | No TODO/FIXME/PLACEHOLDER/HACK found in any modified file |

### Human Verification Required

### 1. End-to-End Multi-Family Novel Test

**Test:** Run the full pipeline on Pride and Prejudice (or similar multi-family novel) and inspect characters.json
**Expected:** Mrs. Bennet, Elizabeth Bennet, Jane Bennet, Mr. Bennet each have separate profiles with no cross-contamination of aliases
**Why human:** LLM extraction and merge quality depends on model behavior with real text

### 2. Merge Audit Review

**Test:** Inspect merge_audit.json from a real book run for surname-pair rejection decisions
**Expected:** Mr. Bennet/Mrs. Bennet pair appears as rejected in candidate_generation stage with "surname-only match" reason
**Why human:** Requires running full pipeline with LLM against real data

### 3. Co-Occurrence LLM Arbiter Behavior

**Test:** Verify that the LLM arbiter correctly handles characters who share names but co-occur (e.g., spelling variants that appear together in scenes)
**Expected:** LLM uses co-occurrence as one signal among many, not as automatic rejection
**Why human:** LLM inference behavior cannot be verified without running the model

### Note on MERGE-05 / ROADMAP Success Criterion #4

The ROADMAP success criterion states "Characters who co-occur in dialogue within the same chapter are never merged, regardless of name similarity." The REQUIREMENTS.md for MERGE-05 originally said "reject merge if both characters appear in same chapter." However, the 14-RESEARCH.md (line 9, 25-26, 91-92) explicitly documents that the user identified the co-occurrence guard as "too blunt" because aliases like Lizzy/Elizabeth co-occur in the same chapter but SHOULD merge. The research recommendation, approved by the user, changed this to "co-occurrence as signal to LLM, not binary gate." The implementation follows the research recommendation. This is a deliberate, documented design improvement over the original requirement text.

### Gaps Summary

No gaps found. All 8 MERGE requirements are satisfied with substantive implementations backed by 30 passing tests. All key links are wired. No anti-patterns detected. The only items requiring human verification are end-to-end pipeline runs with real book data, which cannot be tested programmatically.

---

_Verified: 2026-03-09T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
