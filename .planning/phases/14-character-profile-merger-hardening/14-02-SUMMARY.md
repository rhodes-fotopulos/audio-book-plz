---
phase: 14-character-profile-merger-hardening
plan: 02
subsystem: attribution
tags: [merger, llm-arbiter, audit-trail, pydantic, union-find]

# Dependency graph
requires:
  - phase: 14-01
    provides: MergeDecision and MergeAudit Pydantic models, test scaffold
provides:
  - 4-stage merge pipeline with LLM arbiter and full audit trail
  - merge_audit.json written alongside characters.json
  - Cross-name exclusion, trait cap, post-merge validation
affects: [15-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: [llm-arbiter, union-find-merge-groups, candidate-generation-pattern]

key-files:
  created: []
  modified:
    - src/attribution/merger.py
    - src/pipeline.py
    - tests/test_merger.py

key-decisions:
  - "LLM confidence threshold 0.7 -- below means skip (better duplicates than wrong merges)"
  - "Co-occurrence passed as signal text to LLM, not used as binary gate"
  - "Union-find for transitive merge group resolution in LLM arbiter stage"
  - "Cache namespace merge_arbiter_v1 for LLM arbiter results"

patterns-established:
  - "LLM arbiter pattern: heuristics generate candidates, LLM accepts/rejects with confidence"
  - "Candidate generation pattern: collect match reasons without auto-merging"
  - "Union-find merge groups: handle transitive pairs from LLM accept decisions"

requirements-completed: [MERGE-02, MERGE-04, MERGE-05, MERGE-06, MERGE-07]

# Metrics
duration: 5min
completed: 2026-03-09
---

# Phase 14 Plan 02: Merge Pipeline Restructure Summary

**4-stage LLM-arbitrated merge pipeline with candidate generation, cross-name exclusion, trait cap, co-occurrence signals, and merge_audit.json output**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-09T20:25:09Z
- **Completed:** 2026-03-09T20:30:31Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Restructured merger.py from 4-stage auto-merge to 4-stage LLM-arbitrated pipeline (exact match -> candidate generation -> LLM arbiter -> validation)
- Heuristic stages now generate candidates but never auto-merge; LLM makes all ambiguous decisions
- Cross-name exclusion blocks aliases matching other canonical names (MERGE-04)
- Co-occurrence chapters passed as signal in LLM prompt, not binary gate (MERGE-05)
- Trait cap at 30 enforced after every merge with overflow logging (MERGE-06)
- Post-merge validation flags >5 aliases, >50 traits, alias-canonical cross-contamination (MERGE-02)
- merge_characters returns (profiles, MergeAudit) tuple with full audit trail
- pipeline.py writes merge_audit.json and shows warnings in console
- All 30 tests passing (0 skipped)

## Task Commits

Each task was committed atomically:

1. **Task 1: Restructure merger.py** - `9c2d761` (test RED) + `5d970f1` (feat GREEN)
2. **Task 2: Wire pipeline.py to write merge_audit.json** - `47168b4` (feat)

## Files Created/Modified
- `src/attribution/merger.py` - Restructured 4-stage pipeline with LLM arbiter, candidate generation, cross-name exclusion, trait cap, validation
- `src/pipeline.py` - Unpacks merge_characters tuple, writes merge_audit.json, displays warnings
- `tests/test_merger.py` - 30 tests covering all MERGE requirements (unskipped Plan 02 tests + new additions)

## Decisions Made
- LLM confidence threshold set at 0.7 (below = skip merge, per user principle "better duplicates than wrong merges")
- Union-find used for transitive merge group resolution (handles A-B and B-C accepted = merge all three)
- Cache namespace "merge_arbiter_v1" distinguishes from old "consolidation" cache entries
- MERGE_ARBITER_PROMPT defaults to DIFFERENT and includes co-occurrence context as signal

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Full test suite cannot run in this environment due to missing optional dependencies (pydub, ebooklib) -- pre-existing environment issue, not caused by changes

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- merge_audit.json provides full visibility into every merge decision for debugging
- LLM arbiter threshold (0.7) may need tuning after real book runs -- audit trail enables this
- Phase 15 can use merge_audit.json as input for merge_overrides.yaml design

---
*Phase: 14-character-profile-merger-hardening*
*Completed: 2026-03-09*
