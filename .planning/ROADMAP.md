# Roadmap: Audio Book Plz

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-6 (shipped 2026-03-04) -- [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Pipeline Quality Improvements** -- Phases 7-10 (shipped 2026-03-04) -- [archive](milestones/v1.1-ROADMAP.md)
- ✅ **v1.2 Voice Expression** -- Phases 11-13 (shipped 2026-03-07) -- [archive](milestones/v1.2-ROADMAP.md)
- 🚧 **v1.3 Voice Quality** -- Phases 14-15 (in progress)

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

<details>
<summary>v1.2 Voice Expression (Phases 11-13) -- SHIPPED 2026-03-07</summary>

- [x] Phase 11: Data Model Unification and Voice Matching (2/2 plans) -- completed 2026-03-07
- [x] Phase 12: Emotion Removal and LLM Optimization (2/2 plans) -- completed 2026-03-07
- [x] Phase 13: Synthesis Performance (2/2 plans) -- completed 2026-03-07

</details>

### v1.3 Voice Quality (In Progress)

- [x] **Phase 14: Character Profile Merger Hardening** - Eliminate false-positive merges with cross-name exclusion, co-occurrence guards, and full audit trail (completed 2026-03-09)
- [x] **Phase 15: Opinionated Profiles and Expressive Clips** - Push characters apart with distinctive voice profiles and select reference clips by expressiveness (completed 2026-03-09)

## Phase Details

### Phase 14: Character Profile Merger Hardening
**Goal**: Characters are correctly deduplicated with no cross-contamination, and every merge decision is auditable
**Depends on**: Phase 13 (v1.2 complete)
**Requirements**: MERGE-01, MERGE-02, MERGE-03, MERGE-04, MERGE-05, MERGE-06, MERGE-07, MERGE-08
**Success Criteria** (what must be TRUE):
  1. Running the pipeline on a multi-family novel (e.g., Pride and Prejudice) produces separate profiles for characters who share a surname -- no "Mrs. Bennet" absorbing "Elizabeth" or "Jane"
  2. merge_audit.json is written alongside characters.json and contains per-stage accept/reject decisions with reasons for every merge candidate
  3. Post-merge validation flags any profile with aliases matching another character's canonical name, and the user sees a warning in the console output
  4. Characters who co-occur in dialogue within the same chapter are never merged, regardless of name similarity
  5. No profile exceeds 30 traits after merging -- overflow traits are discarded with a logged warning
**Plans**: 2 plans

Plans:
- [ ] 14-01-PLAN.md -- Data models, test scaffold, and extraction prompt hardening
- [ ] 14-02-PLAN.md -- Merger pipeline restructure with LLM arbiter and audit trail

### Phase 15: Opinionated Profiles and Expressive Clips
**Goal**: Each character gets a polarized, distinctive voice profile and a reference clip selected for expressiveness and pace alignment
**Depends on**: Phase 14
**Requirements**: PROF-01, PROF-02, PROF-03, CLIP-01, CLIP-02
**Success Criteria** (what must be TRUE):
  1. Running with --opinionated produces voice profiles that never use words like "moderate", "medium", or "average" -- every trait is pushed to a distinctive extreme
  2. When two characters have similar extracted profiles, the post-extraction distinctiveness pass modifies at least one to create audible separation (verifiable by diffing characters.json before/after)
  3. A voice_overrides.yaml file in the book directory is loaded and applied as the final step, overriding any automated profile fields for specified characters
  4. Reference clip selection scores clips using a composite of SNR, pitch variance, energy variance, and rate match -- not just duration -- and a fast-paced character gets a faster-talking speaker's clip
**Plans**: 2 plans

Plans:
- [ ] 15-01-PLAN.md -- Opinionated extraction, LLM distinctiveness pass, and voice overrides
- [ ] 15-02-PLAN.md -- Expressiveness-aware clip selection with rate matching

## Progress

**Execution Order:**
Phases execute in numeric order: 14 -> 15

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
| 12. Emotion Removal and LLM Optimization | v1.2 | 2/2 | Complete | 2026-03-07 |
| 13. Synthesis Performance | v1.2 | 2/2 | Complete | 2026-03-07 |
| 14. Character Profile Merger Hardening | v1.3 | 2/2 | Complete | 2026-03-09 |
| 15. Opinionated Profiles and Expressive Clips | 2/2 | Complete   | 2026-03-09 | - |

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-03-09 -- Phase 15 plans created*
