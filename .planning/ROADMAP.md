# Roadmap: Audio Book Plz

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-6 (shipped 2026-03-04) -- [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Pipeline Quality Improvements** -- Phases 7-10 (shipped 2026-03-04) -- [archive](milestones/v1.1-ROADMAP.md)
- **v1.2 Voice Expression** -- Phases 11-13 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-6) -- SHIPPED 2026-03-04</summary>

- [x] Phase 1: EPUB Parsing and CLI Skeleton (3/3 plans) -- completed 2026-03-04
- [x] Phase 2: LLM Character Extraction and Speaker Attribution (3/3 plans) -- completed 2026-03-04
- [x] Phase 3: Voice-Character Matching (3/3 plans) -- completed 2026-03-03
- [x] Phase 4: TTS Synthesis with Checkpoint/Resume (3/3 plans) -- completed 2026-03-03
- [x] Phase 5: Audio Assembly and Final Output (3/3 plans) -- completed 2026-03-04
- [x] Phase 6: Integration Fixes and Full Pipeline Wiring (2/2 plans) -- completed 2026-03-04

</details>

<details>
<summary>v1.1 Pipeline Quality Improvements (Phases 7-10) -- SHIPPED 2026-03-04</summary>

- [x] Phase 7: TTS Engine Swap (3/3 plans) -- completed 2026-03-04
- [x] Phase 8: LLM Intelligence and Emotion (3/3 plans) -- completed 2026-03-04
- [x] Phase 9: Production Polish (3/3 plans) -- completed 2026-03-04
- [x] Phase 10: Verification & CLI Wiring Fixes (3/3 plans) -- completed 2026-03-04

</details>

### v1.2 Voice Expression

**Milestone Goal:** Unify voice data model, remove unused emotion system, cache LLM matching results, and optimize synthesis performance.

- [x] **Phase 11: Data Model Unification and Voice Matching** - Unified VoiceProfile replaces duplicated fields; matchers consume richer voice data (completed 2026-03-07)
- [x] **Phase 12: Emotion Removal and LLM Optimization** - Pipeline simplified by removing unused emotion system; speech-act post-processing and LLM refinement made opt-in; trait matcher results cached (completed 2026-03-07)
- [ ] **Phase 13: Synthesis Performance** - Reference caching and batch-by-character ordering for faster synthesis runs

## Phase Details

### Phase 11: Data Model Unification and Voice Matching
**Goal**: Characters have a single, complete voice description that drives better speaker selection
**Depends on**: Phase 10 (v1.1 complete)
**Requirements**: MODEL-01, MODEL-02, MATCH-01, MATCH-02
**Success Criteria** (what must be TRUE):
  1. Running the pipeline on a previously-processed book produces a characters.json with unified voice_profile fields instead of separate voice_qualities and voice_baseline
  2. Existing characters.json files from v1.1 load without errors or re-extraction (backward compatibility)
  3. Voice matching produces speaker assignments using the richer unified profile data (visible in matching logs)
  4. No regression in speaker selection quality compared to v1.1 output
**Plans:** 2/2 plans complete

Plans:
- [ ] 11-01-PLAN.md -- VoiceProfile model, extraction prompt, and merger redesign
- [ ] 11-02-PLAN.md -- Matcher updates and test fixture migration

### Phase 12: Emotion Removal and LLM Optimization
**Goal**: Pipeline simplified by removing unused emotion system; speech-act post-processing and LLM refinement made opt-in; trait matcher results cached
**Depends on**: Phase 11
**Requirements**: EXPR-01 (superseded), EXPR-02 (superseded), EXPR-03 (superseded)
**Success Criteria** (what must be TRUE):
  1. Emotion module removed from codebase (Base model cannot combine voice cloning with emotion instructions)
  2. Speech-act post-processing available via --speech-act-fx flag (default OFF)
  3. LLM refinement available via --refine-llm flag (default OFF)
  4. Trait matcher caches LLM results and skips LLM on re-runs with unchanged inputs
  5. ROADMAP and REQUIREMENTS reflect 3-phase structure (11-13)
**Plans:** 2/2 plans complete

Plans:
- [x] 12-01-PLAN.md -- Emotion removal and speech-act flags
- [x] 12-02-PLAN.md -- Trait matcher caching and doc updates

### Phase 13: Synthesis Performance
**Goal**: Synthesis runs faster by caching voice references and enabling per-character batch ordering
**Depends on**: Phase 12
**Requirements**: SYNTH-05, SYNTH-06
**Success Criteria** (what must be TRUE):
  1. Voice reference encoding is computed once per character and reused across all that character's segments (visible in logs, measurable time reduction)
  2. Running with --batch-by-character synthesizes all segments for each character consecutively, then stitches output back into chapter order
  3. Final audiobook output is identical regardless of whether --batch-by-character is used (ordering is a synthesis optimization, not an output change)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 11 -> 12 -> 13

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. EPUB Parsing and CLI Skeleton | v1.0 | 3/3 | Complete | 2026-03-04 |
| 2. LLM Character Extraction | v1.0 | 3/3 | Complete | 2026-03-04 |
| 3. Voice-Character Matching | v1.0 | 3/3 | Complete | 2026-03-03 |
| 4. TTS Synthesis | v1.0 | 3/3 | Complete | 2026-03-03 |
| 5. Audio Assembly | v1.0 | 3/3 | Complete | 2026-03-04 |
| 6. Integration Fixes | v1.0 | 2/2 | Complete | 2026-03-04 |
| 7. TTS Engine Swap | v1.1 | 3/3 | Complete | 2026-03-04 |
| 8. LLM Intelligence and Emotion | v1.1 | 3/3 | Complete | 2026-03-04 |
| 9. Production Polish | v1.1 | 3/3 | Complete | 2026-03-04 |
| 10. Verification & CLI Wiring Fixes | v1.1 | 3/3 | Complete | 2026-03-04 |
| 11. Data Model Unification and Voice Matching | v1.2 | 2/2 | Complete | 2026-03-07 |
| 12. Emotion Removal and LLM Optimization | v1.2 | Complete    | 2026-03-07 | 2026-03-07 |
| 13. Synthesis Performance | v1.2 | 0/? | Not started | - |

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-03-07 -- Milestone restructured from 5 phases to 3 (11-13), removed dropped phases*
