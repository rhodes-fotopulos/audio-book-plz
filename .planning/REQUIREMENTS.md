# Requirements: Audio Book Plz

**Defined:** 2026-03-06
**Core Value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## v1.2 Requirements

Requirements for v1.2 Voice Expression milestone. Each maps to roadmap phases.

### Data Model

- [x] **MODEL-01**: VoiceProfile unifies VoiceQualities and VoiceBaseline into single model with all unique attributes (pitch, pace, tone, accent, energy, typical_emotion, description)
- [x] **MODEL-02**: Existing characters.json files load into new VoiceProfile schema without re-extraction (backward-compatible migration)

### Voice Matching

- [x] **MATCH-01**: trait_matcher uses unified VoiceProfile fields for richer character-to-speaker descriptions
- [x] **MATCH-02**: embedding_matcher uses unified VoiceProfile fields for better embedding-based matching

### Expression System

- [x] **EXPR-01**: ~~Expression resolver combines three layers (character baseline + scene mood + line override) into single ExpressionParams~~ SUPERSEDED -- Emotion system removed (Base model cannot combine voice cloning with emotion instructions). Replaced by emotion module deletion.
- [x] **EXPR-02**: ~~Emotion-category parameter tables map mood types to volume/speed/pitch deltas with intensity scaling~~ SUPERSEDED -- Emotion parameter tables not needed. Replaced by speech-act post-processing flag (--speech-act-fx, default OFF).
- [x] **EXPR-03**: ~~Clear precedence rules resolve conflicts between speech-act adjustments and emotion conditioning~~ SUPERSEDED -- Only speech-act layer remains (no emotion conflict to resolve). Replaced by optional speech-act LLM refinement + trait matcher caching.

### Synthesis Wiring

- [x] **SYNTH-01**: ~~Synthesis loop loads emotion.json and characters.json, builds per-segment lookups~~ DROPPED -- No emotion data to wire into synthesis.
- [x] **SYNTH-02**: ~~Expression resolver called per segment, results applied via extended post-processor~~ DROPPED -- No emotion data to wire into synthesis.
- [x] **SYNTH-03**: ~~Pitch shifting applied via pedalboard PitchShift as third post-processing dimension~~ DROPPED -- No emotion data to wire into synthesis.
- [x] **SYNTH-04**: ~~`--expression` flag enables/disables emotion conditioning with graceful fallback when emotion.json missing~~ DROPPED -- No emotion data to wire into synthesis.
- [ ] **SYNTH-05**: Precomputed reference encoding cached per character, reused across all segments for that character
- [ ] **SYNTH-06**: `--batch-by-character` flag for per-character synthesis ordering with post-hoc chapter stitching

### Text-Cue Injection

- [x] **CUE-01**: ~~Emotion-to-text-cue injection prepends natural-language cues to segment text before TTS~~ DROPPED -- Text-cue injection doesn't work with Base model.
- [x] **CUE-02**: ~~Feature flag to enable/disable text-cue injection independently of post-processing expression~~ DROPPED -- Text-cue injection doesn't work with Base model.

### Preview

- [x] **PREV-01**: ~~`--preview-segment N` flag generates A/B comparison of segment with and without expression~~ DROPPED -- A/B preview has less value without expression system.

## Future Requirements

### Performance

- **PERF-01**: Checkpoint metadata includes feature hash to detect when re-synthesis is needed after expression changes

### Advanced Expression

- **ADVX-01**: VoiceDesign-then-Clone pipeline generates styled reference clips per character
- **ADVX-02**: Emotion interpolation between scenes for smooth transitions

## Out of Scope

| Feature | Reason |
|---------|--------|
| VoiceDesign model integration | Loses real human voice cloning -- core value. Defer to future if post-processing proves insufficient. |
| Per-word emphasis marking | No mechanism in Base model for word-level control |
| CustomVoice model (9 preset speakers) | Loses arbitrary voice cloning from LibriTTS-R |
| Instruct parameter on Base model | Base model does not support instruct -- verified via official docs and source code |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MODEL-01 | Phase 11 | Complete |
| MODEL-02 | Phase 11 | Complete |
| MATCH-01 | Phase 11 | Complete |
| MATCH-02 | Phase 11 | Complete |
| EXPR-01 | Phase 12 | SUPERSEDED |
| EXPR-02 | Phase 12 | SUPERSEDED |
| EXPR-03 | Phase 12 | SUPERSEDED |
| SYNTH-01 | Phase 13 (removed) | DROPPED |
| SYNTH-02 | Phase 13 (removed) | DROPPED |
| SYNTH-03 | Phase 13 (removed) | DROPPED |
| SYNTH-04 | Phase 13 (removed) | DROPPED |
| SYNTH-05 | Phase 13 | Pending |
| SYNTH-06 | Phase 13 | Pending |
| CUE-01 | Phase 15 (removed) | DROPPED |
| CUE-02 | Phase 15 (removed) | DROPPED |
| PREV-01 | Phase 15 (removed) | DROPPED |

**Coverage:**
- v1.2 requirements: 16 total
- Complete: 4 (MODEL-01, MODEL-02, MATCH-01, MATCH-02)
- Superseded: 3 (EXPR-01, EXPR-02, EXPR-03)
- Dropped: 7 (SYNTH-01 through SYNTH-04, CUE-01, CUE-02, PREV-01)
- Remaining: 2 (SYNTH-05, SYNTH-06 in Phase 13)

---
*Requirements defined: 2026-03-06*
*Last updated: 2026-03-07 -- EXPR requirements superseded, SYNTH-01..04/CUE/PREV dropped after milestone restructure*
