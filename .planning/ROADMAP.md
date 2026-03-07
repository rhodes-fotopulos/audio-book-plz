# Roadmap: Audio Book Plz

## Milestones

- ✅ **v1.0 MVP** -- Phases 1-6 (shipped 2026-03-04) -- [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Pipeline Quality Improvements** -- Phases 7-10 (shipped 2026-03-04) -- [archive](milestones/v1.1-ROADMAP.md)
- **v1.2 Voice Expression** -- Phases 11-15 (in progress)

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

**Milestone Goal:** Wire extracted voice and emotion data into TTS synthesis so each character sounds consistently styled, scenes carry emotional weight, and duplicated voice fields are unified.

- [x] **Phase 11: Data Model Unification and Voice Matching** - Unified VoiceProfile replaces duplicated fields; matchers consume richer voice data (completed 2026-03-07)
- [ ] **Phase 12: Expression System Core** - Three-layer expression resolver produces concrete audio parameters from emotion data
- [ ] **Phase 13: Synthesis Wiring and Post-Processing** - Expression system connected to synthesis loop with pitch shifting and feature flag
- [ ] **Phase 14: Synthesis Performance** - Reference caching and batch-by-character ordering for faster synthesis runs
- [ ] **Phase 15: Experimental Expression and Preview** - Text-cue injection experiment and A/B preview tooling

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

### Phase 12: Expression System Core
**Goal**: Emotion data from attribution phase resolves into concrete, conflict-free audio parameters
**Depends on**: Phase 11
**Requirements**: EXPR-01, EXPR-02, EXPR-03
**Success Criteria** (what must be TRUE):
  1. Given a character baseline, scene mood, and line-level override, the resolver produces a single ExpressionParams with volume, speed, and pitch deltas
  2. Emotion categories (angry, sad, joyful, fearful, etc.) map to distinct parameter profiles with intensity scaling
  3. When a speech-act adjustment (e.g., whispered) conflicts with an emotion override, the precedence rules produce a deterministic, sensible result
  4. Neutral/missing emotion data produces identity parameters (no audio modification)
**Plans:** 2 plans

Plans:
- [ ] 12-01-PLAN.md -- Emotion removal and speech-act flags
- [ ] 12-02-PLAN.md -- Trait matcher caching and doc updates

### Phase 13: Synthesis Wiring and Post-Processing
**Goal**: Running synthesis with --expression produces audibly different output driven by scene mood and line emotion
**Depends on**: Phase 12
**Requirements**: SYNTH-01, SYNTH-02, SYNTH-03, SYNTH-04
**Success Criteria** (what must be TRUE):
  1. The synthesis loop loads emotion.json and characters.json, and logs which expression parameters are applied per segment
  2. A segment in an angry scene sounds audibly different from the same text in a calm scene (volume, speed, pitch differ)
  3. Pitch shifting via pedalboard applies as a third post-processing dimension alongside volume and speed
  4. Running without --expression flag (or without emotion.json) produces identical output to v1.1 (graceful fallback)
**Plans**: TBD

### Phase 14: Synthesis Performance
**Goal**: Synthesis runs faster by caching voice references and enabling per-character batch ordering
**Depends on**: Phase 13
**Requirements**: SYNTH-05, SYNTH-06
**Success Criteria** (what must be TRUE):
  1. Voice reference encoding is computed once per character and reused across all that character's segments (visible in logs, measurable time reduction)
  2. Running with --batch-by-character synthesizes all segments for each character consecutively, then stitches output back into chapter order
  3. Final audiobook output is identical regardless of whether --batch-by-character is used (ordering is a synthesis optimization, not an output change)
**Plans**: TBD

### Phase 15: Experimental Expression and Preview
**Goal**: Users can experiment with text-cue injection and preview expression effects before committing to full synthesis
**Depends on**: Phase 13
**Requirements**: CUE-01, CUE-02, PREV-01
**Success Criteria** (what must be TRUE):
  1. With text-cue injection enabled, emotion cues are prepended to segment text before TTS and do not appear as spoken words in the output
  2. Text-cue injection can be enabled/disabled independently of post-processing expression via its own feature flag
  3. Running --preview-segment N generates two audio files (with and without expression) for side-by-side comparison
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 11 -> 12 -> 13 -> 14 -> 15
Note: Phase 14 and 15 both depend on Phase 13 and could execute in either order.

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
| 12. Expression System Core | v1.2 | 0/2 | Not started | - |
| 13. Synthesis Wiring and Post-Processing | v1.2 | 0/? | Not started | - |
| 14. Synthesis Performance | v1.2 | 0/? | Not started | - |
| 15. Experimental Expression and Preview | v1.2 | 0/? | Not started | - |

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-03-06 -- Phase 12 plans created*
