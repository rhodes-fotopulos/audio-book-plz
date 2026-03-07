# Requirements: Audio Book Plz

**Defined:** 2026-03-06
**Core Value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## v1.2 Requirements

Requirements for v1.2 Voice Expression milestone. Each maps to roadmap phases.

### Data Model

- [ ] **MODEL-01**: VoiceProfile unifies VoiceQualities and VoiceBaseline into single model with all unique attributes (pitch, pace, tone, accent, energy, typical_emotion, description)
- [ ] **MODEL-02**: Existing characters.json files load into new VoiceProfile schema without re-extraction (backward-compatible migration)

### Voice Matching

- [ ] **MATCH-01**: trait_matcher uses unified VoiceProfile fields for richer character-to-speaker descriptions
- [ ] **MATCH-02**: embedding_matcher uses unified VoiceProfile fields for better embedding-based matching

### Expression System

- [ ] **EXPR-01**: Expression resolver combines three layers (character baseline + scene mood + line override) into single ExpressionParams
- [ ] **EXPR-02**: Emotion-category parameter tables map mood types to volume/speed/pitch deltas with intensity scaling
- [ ] **EXPR-03**: Clear precedence rules resolve conflicts between speech-act adjustments and emotion conditioning

### Synthesis Wiring

- [ ] **SYNTH-01**: Synthesis loop loads emotion.json and characters.json, builds per-segment lookups
- [ ] **SYNTH-02**: Expression resolver called per segment, results applied via extended post-processor
- [ ] **SYNTH-03**: Pitch shifting applied via pedalboard PitchShift as third post-processing dimension
- [ ] **SYNTH-04**: `--expression` flag enables/disables emotion conditioning with graceful fallback when emotion.json missing
- [ ] **SYNTH-05**: Precomputed reference encoding cached per character, reused across all segments for that character
- [ ] **SYNTH-06**: `--batch-by-character` flag for per-character synthesis ordering with post-hoc chapter stitching

### Text-Cue Injection

- [ ] **CUE-01**: Emotion-to-text-cue injection prepends natural-language cues to segment text before TTS
- [ ] **CUE-02**: Feature flag to enable/disable text-cue injection independently of post-processing expression

### Preview

- [ ] **PREV-01**: `--preview-segment N` flag generates A/B comparison of segment with and without expression

## Future Requirements

### Performance

- **PERF-01**: Checkpoint metadata includes feature hash to detect when re-synthesis is needed after expression changes

### Advanced Expression

- **ADVX-01**: VoiceDesign-then-Clone pipeline generates styled reference clips per character
- **ADVX-02**: Emotion interpolation between scenes for smooth transitions

## Out of Scope

| Feature | Reason |
|---------|--------|
| VoiceDesign model integration | Loses real human voice cloning — core value. Defer to future if post-processing proves insufficient. |
| Per-word emphasis marking | No mechanism in Base model for word-level control |
| CustomVoice model (9 preset speakers) | Loses arbitrary voice cloning from LibriTTS-R |
| Instruct parameter on Base model | Base model does not support instruct — verified via official docs and source code |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MODEL-01 | — | Pending |
| MODEL-02 | — | Pending |
| MATCH-01 | — | Pending |
| MATCH-02 | — | Pending |
| EXPR-01 | — | Pending |
| EXPR-02 | — | Pending |
| EXPR-03 | — | Pending |
| SYNTH-01 | — | Pending |
| SYNTH-02 | — | Pending |
| SYNTH-03 | — | Pending |
| SYNTH-04 | — | Pending |
| SYNTH-05 | — | Pending |
| SYNTH-06 | — | Pending |
| CUE-01 | — | Pending |
| CUE-02 | — | Pending |
| PREV-01 | — | Pending |

**Coverage:**
- v1.2 requirements: 16 total
- Mapped to phases: 0
- Unmapped: 16

---
*Requirements defined: 2026-03-06*
*Last updated: 2026-03-06 after initial definition*
