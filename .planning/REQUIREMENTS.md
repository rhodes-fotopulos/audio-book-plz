# Requirements: Audio Book Plz

**Defined:** 2026-03-09
**Core Value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## v1.3 Requirements

Requirements for Voice Quality milestone. Each maps to roadmap phases.

### Merger Hardening

- [x] **MERGE-01**: Per-stage logging of every merge decision (which profiles, why, accepted/rejected)
- [x] **MERGE-02**: Post-merge validation flags profiles with >5 aliases, >50 traits, or aliases matching other characters' canonical names
- [x] **MERGE-03**: Write merge_audit.json alongside characters.json for debugging
- [x] **MERGE-04**: Cross-name exclusion — before adding an alias, check it against canonical names of all other profiles
- [x] **MERGE-05**: Co-occurrence guard on all merge stages (not just stage 4) — reject merge if both characters appear in same chapter
- [x] **MERGE-06**: Trait count cap at 30 — if exceeded after merge, keep only primary profile's traits
- [x] **MERGE-07**: Surname-only exclusion — block merges where shared token is a surname but profiles have different titles/first-names
- [x] **MERGE-08**: Extraction prompt hardening with explicit negative examples ("WRONG: Mrs. Bennet aliases=[Elizabeth, Jane]")

### Opinionated Voice Profiles

- [ ] **PROF-01**: --opinionated flag modifies extraction prompt to push for extreme distinctive descriptions, never use "moderate"/"medium"
- [ ] **PROF-02**: Post-extraction distinctiveness pass — review all voice profiles together and push similar-sounding characters apart
- [ ] **PROF-03**: voice_overrides.yaml — user can manually set voice profile fields per character, applied last in pipeline

### Expressive Reference Clips

- [ ] **CLIP-01**: Score clips by expressiveness composite (0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match) not just duration
- [ ] **CLIP-02**: Rate-match reference clips to character profile — fast-paced character gets a fast-talking speaker's clip

## Future Requirements

### Expressive Reference Clips

- **CLIP-03**: Multiple reference clips per character for different speech-act types (excited clip for shouted, calm for narration)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Qwen3-TTS Instruct model | Base model stays — expressiveness is fixed upstream |
| Gender-aware pitch normalization | Optimization for v1.4+ if scoring weights need tuning |
| Precomputed expressiveness cache per speaker | Premature optimization — compute on demand first |
| Rule-based vs LLM distinctiveness pass | Implementation choice, not a requirement — resolved during planning |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MERGE-01 | Phase 14 | Complete |
| MERGE-02 | Phase 14 | Complete |
| MERGE-03 | Phase 14 | Complete |
| MERGE-04 | Phase 14 | Complete |
| MERGE-05 | Phase 14 | Complete |
| MERGE-06 | Phase 14 | Complete |
| MERGE-07 | Phase 14 | Complete |
| MERGE-08 | Phase 14 | Complete |
| PROF-01 | Phase 15 | Pending |
| PROF-02 | Phase 15 | Pending |
| PROF-03 | Phase 15 | Pending |
| CLIP-01 | Phase 15 | Pending |
| CLIP-02 | Phase 15 | Pending |

**Coverage:**
- v1.3 requirements: 13 total
- Mapped to phases: 13
- Unmapped: 0

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 after roadmap creation*
