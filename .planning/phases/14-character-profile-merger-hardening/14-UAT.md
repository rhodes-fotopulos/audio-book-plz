---
status: complete
phase: 14-character-profile-merger-hardening
source: 14-01-SUMMARY.md, 14-02-SUMMARY.md
started: 2026-03-09T21:00:00Z
updated: 2026-03-09T21:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. All Merger Tests Pass
expected: Run `python -m pytest tests/test_merger.py -v`. All 30 tests pass with 0 skipped, 0 failures.
result: pass

### 2. merge_audit.json Written by Pipeline
expected: After running the pipeline on a book, a `merge_audit.json` file is written alongside `characters.json` in the output directory. The audit file contains merge decisions with fields like candidates evaluated, accept/reject status, and confidence scores.
result: pass

### 3. Post-Merge Validation Warnings Display
expected: If any merged character has >5 aliases, >50 traits, or alias-canonical cross-contamination, warnings are printed to the console during pipeline execution.
result: pass

### 4. Trait Cap Enforcement
expected: After merging, no character profile has more than 30 traits. Overflow traits are logged but discarded. Verify by inspecting `characters.json` output — every character's traits list should have ≤30 entries.
result: pass

### 5. Cross-Name Exclusion
expected: Aliases that match another character's canonical name are blocked from merging. For example, if "Elizabeth" is a canonical name and also appears as an alias on a different character, the merger does not incorrectly merge those characters.
result: pass

### 6. Hardened Extraction Prompt
expected: The extraction prompt in `src/attribution/extractor.py` includes explicit WRONG/RIGHT examples demonstrating family-name confusion patterns. The cache key is `extraction_v3` (not v2), ensuring stale extractions from the old prompt are invalidated.
result: pass

### 7. LLM Arbiter Decision Flow
expected: The merge pipeline uses a 4-stage flow: exact match → candidate generation → LLM arbiter → validation. Heuristic stages generate candidates but never auto-merge; the LLM makes all ambiguous merge decisions with a confidence threshold of 0.7.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
