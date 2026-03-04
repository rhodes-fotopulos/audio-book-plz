# Roadmap: Audio Book Plz

## Milestones

- ✅ **v1.0 MVP** — Phases 1-6 (shipped 2026-03-04) — [archive](milestones/v1.0-ROADMAP.md)
- 🚧 **v1.1 Pipeline Quality Improvements** — Phases 7-9 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-6) — SHIPPED 2026-03-04</summary>

- [x] Phase 1: EPUB Parsing and CLI Skeleton (3/3 plans) — completed 2026-03-04
- [x] Phase 2: LLM Character Extraction and Speaker Attribution (3/3 plans) — completed 2026-03-04
- [x] Phase 3: Voice-Character Matching (3/3 plans) — completed 2026-03-03
- [x] Phase 4: TTS Synthesis with Checkpoint/Resume (3/3 plans) — completed 2026-03-03
- [x] Phase 5: Audio Assembly and Final Output (3/3 plans) — completed 2026-03-04
- [x] Phase 6: Integration Fixes and Full Pipeline Wiring (2/2 plans) — completed 2026-03-04

</details>

### 🚧 v1.1 Pipeline Quality Improvements (In Progress)

**Milestone Goal:** Upgrade the audiobook pipeline with Qwen3-TTS (MLX native), emotional narration control, improved dialogue detection, and professional post-processing to close the gap between "working prototype" and "listenable audiobook."

- [x] **Phase 7: TTS Engine Swap** — Replace Chatterbox with Qwen3-TTS 1.7B via mlx-audio for better voice cloning, larger chunks, and Apple Silicon native inference
- [ ] **Phase 8: LLM Intelligence and Emotion** — Upgrade LLM to 14B, add hybrid dialogue detection with speech-act tagging, and build three-layer emotion system
- [ ] **Phase 9: Production Polish** — Randomized pauses, professional post-processing chain, voice consistency verification, and ACX-grade export

## Phase Details

### Phase 7: TTS Engine Swap
**Goal**: Pipeline produces audiobooks using Qwen3-TTS 1.7B via MLX instead of Chatterbox, with larger text chunks, better voice references, and memory-stable full-book synthesis
**Depends on**: Phase 6 (v1.0 complete pipeline)
**Requirements**: TTS-01, TTS-02, TTS-03, TTS-04, TTS-05, TTS-06
**Success Criteria** (what must be TRUE):
  1. User runs `convert` and the pipeline synthesizes all segments using Qwen3-TTS via mlx-audio, producing audibly clearer speech than Chatterbox output
  2. A full-book synthesis run (3000+ segments) completes without memory growth causing slowdown or crash — MLX Metal cache stays bounded
  3. Text segments sent to TTS are 500-600 characters each, split at paragraph/sentence boundaries, producing noticeably fewer segment-boundary seams
  4. Voice references are 10-15 second SNR-filtered clips with bundled transcripts, and cloned voices sound closer to the reference than v1.0 Chatterbox output
  5. User can set a config flag to fall back to Chatterbox TTS, and old checkpoint files from v1.0 runs are detected and skipped (not silently reused with wrong engine)
**Plans**: 3 plans

Plans:
- [x] 07-01-PLAN.md — Engine abstraction + Qwen3-TTS integration + Chatterbox refactor (Wave 1)
- [x] 07-02-PLAN.md — Text chunker (500-600 chars) + voice reference prep with SNR/transcripts (Wave 1)
- [x] 07-03-PLAN.md — Checkpoint versioning + synthesizer integration + fallback wiring (Wave 2)

### Phase 8: LLM Intelligence and Emotion
**Goal**: Attribution uses a stronger LLM model, dialogue detection distinguishes speech acts (spoken/thought/shouted/whispered), and a three-layer emotion system feeds post-processing parameters into synthesis
**Depends on**: Phase 7
**Requirements**: LLM-01, LLM-02, LLM-03, EMO-01, EMO-02, EMO-03, EMO-04
**Success Criteria** (what must be TRUE):
  1. Attribution runs use qwen3:14b Q4_K_M by default, with automatic fallback to 8B Q8_0 if the 14B model exceeds memory — and the Ollama model loads once at pipeline start and stays resident across all LLM phases
  2. Every dialogue line in the output JSON is tagged with a speech-act subtype (spoken, thought, shouted, or whispered), and hybrid regex+LLM detection catches cases that v1.0 regex missed (e.g., indirect dialogue, internal monologue)
  3. Each character in the extraction output has a voice_baseline field describing their default speaking style, each scene has a mood+intensity annotation, and only lines where emotion sharply breaks from scene mood get line-level overrides
  4. Emotion data reaches synthesis as post-processing parameters (volume and speed adjustments keyed to speech-act tags), not as TTS instruct prompts — whispered lines are quieter, shouted lines are louder
**Plans**: 3 plans

Plans:
- [ ] 08-01-PLAN.md — LLM model upgrade (14B/8B) + keep-alive management + model lifecycle (Wave 1)
- [ ] 08-02-PLAN.md — Hybrid dialogue detection with speech-act tagging + voice baseline extraction (Wave 1)
- [ ] 08-03-PLAN.md — Three-layer emotion system (scene mood + line overrides) + post-processing integration (Wave 2)

### Phase 9: Production Polish
**Goal**: Assembled audiobooks sound professionally mastered with natural pause timing, clean audio processing, verified voice consistency, and ACX-compliant export format
**Depends on**: Phase 8
**Requirements**: POL-01, POL-02, POL-03, POL-04, POL-05
**Success Criteria** (what must be TRUE):
  1. Pauses between segments vary naturally — scene breaks are longer than speaker changes, chapter breaks are longest — and timing uses Gaussian-randomized durations within context-aware ranges (not fixed silence values)
  2. Post-processing applies a pedalboard effects chain (trim silence, noise gate, compress, high-pass EQ at 80Hz, limit) and every step is A/B validated to confirm it improves rather than degrades audio quality
  3. Final export is 44.1kHz 192kbps CBR MP3 meeting ACX loudness and peak specifications
  4. Same-speaker segments are compared via speaker embeddings, and outliers beyond cosine threshold (starting at 0.60) are regenerated up to 3 times — the best attempt is kept, preventing voice drift within a character
  5. Segment boundaries use 5-10ms fade-in/fade-out crossfades instead of hard silence cuts, eliminating audible clicks at joins
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 7 -> 8 -> 9

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. EPUB Parsing and CLI Skeleton | v1.0 | 3/3 | Complete | 2026-03-04 |
| 2. LLM Character Extraction | v1.0 | 3/3 | Complete | 2026-03-04 |
| 3. Voice-Character Matching | v1.0 | 3/3 | Complete | 2026-03-03 |
| 4. TTS Synthesis | v1.0 | 3/3 | Complete | 2026-03-03 |
| 5. Audio Assembly | v1.0 | 3/3 | Complete | 2026-03-04 |
| 6. Integration Fixes | v1.0 | 2/2 | Complete | 2026-03-04 |
| 7. TTS Engine Swap | v1.1 | 3/3 | Complete | 2026-03-04 |
| 8. LLM Intelligence and Emotion | v1.1 | 0/3 | Planned | - |
| 9. Production Polish | v1.1 | 0/? | Not started | - |

---
*Roadmap created: 2026-03-03*
*Last updated: 2026-03-04 after Phase 7 execution*
