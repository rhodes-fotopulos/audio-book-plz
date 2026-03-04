# Requirements: Audio Book Plz

**Defined:** 2026-03-04
**Core Value:** Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## v1.1 Requirements

Requirements for pipeline quality improvement milestone. Each maps to roadmap phases.

### TTS Engine

- [x] **TTS-01**: Pipeline synthesizes audio using Qwen3-TTS 1.7B via mlx-audio instead of Chatterbox TTS
- [x] **TTS-02**: TTS engine manages MLX Metal cache to remain memory-stable across full-book synthesis runs
- [x] **TTS-03**: Pipeline pre-splits text into 500-600 char chunks at paragraph/sentence boundaries before TTS generation
- [x] **TTS-04**: Voice references use 10-15 second SNR-filtered clips from LibriTTS-R with bundled transcripts
- [x] **TTS-05**: Chatterbox preserved as fallback behind config flag during migration
- [x] **TTS-06**: Existing checkpoint files are versioned — old Chatterbox checkpoints are gracefully invalidated, not silently reused

### LLM Intelligence

- [ ] **LLM-01**: Attribution uses qwen3:14b Q4_K_M with KV cache quantization, falling back to 8B Q8_0 if 14B exceeds 16GB memory budget
- [ ] **LLM-02**: Dialogue detection uses hybrid regex + LLM to tag lines as spoken/thought/shouted/whispered
- [ ] **LLM-03**: Ollama model loads once at pipeline start and stays resident across all LLM phases, with explicit unload before TTS

### Emotion System

- [ ] **EMO-01**: Character extraction generates a voice_baseline field describing each character's default speaking style
- [ ] **EMO-02**: Scene mood analysis produces one mood + intensity per scene via LLM pass
- [ ] **EMO-03**: Line-level emotion overrides flag only lines where speaker emotion sharply breaks from scene mood
- [ ] **EMO-04**: Emotion data flows to synthesis as post-processing parameters (volume/speed adjustments for speech-act tags), not as TTS instruct prompts

### Production Polish

- [ ] **POL-01**: Pause timing uses Gaussian-randomized durations within context-aware ranges (scene breaks, speaker changes, chapter breaks)
- [ ] **POL-02**: Post-processing applies pedalboard effects chain incrementally: trim silence, noise gate, compress, high-pass EQ at 80Hz, limit
- [ ] **POL-03**: Final export is 44.1kHz 192kbps CBR MP3 (ACX spec)
- [ ] **POL-04**: Voice consistency pass compares same-speaker segment embeddings and regenerates outliers (max 3 attempts, cosine threshold starting at 0.60)
- [ ] **POL-05**: Segments use 5-10ms fade-in/fade-out crossfades instead of hard silence insertion

## Future Requirements

Deferred from v1.1. Tracked but not in current roadmap.

### User Workflow

- **UX-01**: User can edit attribution JSON by hand and re-run synthesis from that point
- **UX-02**: Custom pronunciation overrides via YAML for character names and proper nouns
- **UX-03**: Dry-run that estimates segment count, synthesis time, and disk usage
- **UX-04**: Preview each character's voice (3-second sample) before full synthesis

### Export Formats

- **EXP-01**: Individual chapter MP3 files in addition to full audiobook
- **EXP-02**: M4B export with embedded chapter markers for audiobook player support

### Emotion (Deferred)

- **EMO-05**: Explicit per-line emotion instructions with cloned voices (blocked — Qwen3-TTS Base model ignores `instruct` parameter with cloned voices; requires upstream fix or fine-tuning)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Explicit emotion prompts to cloned voices | Qwen3-TTS Base model ignores `instruct` param — confirmed via GitHub #231, #238 |
| Multiple TTS engines per character | Memory constraints and voice consistency issues from stitching |
| De-essing in post-processing | ACX warns against it for synthetic speech |
| Ultra-long reference clips (30+ sec) | Quality degrades, generation hangs above ~30s |
| Real-time emotion slider controls | Impractical at 3000+ segments per book |
| Per-sentence inline emotion markup | Qwen3-TTS does not support this |
| GUI or web interface | CLI only for personal use |
| Non-English support | English-only pipeline (Qwen3-TTS, LibriTTS, Ollama models) |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TTS-01 | Phase 7 | Complete |
| TTS-02 | Phase 7 | Complete |
| TTS-03 | Phase 7 | Complete |
| TTS-04 | Phase 7 | Complete |
| TTS-05 | Phase 7 | Complete |
| TTS-06 | Phase 7 | Complete |
| LLM-01 | Phase 8 | Pending |
| LLM-02 | Phase 8 | Pending |
| LLM-03 | Phase 8 | Pending |
| EMO-01 | Phase 8 | Pending |
| EMO-02 | Phase 8 | Pending |
| EMO-03 | Phase 8 | Pending |
| EMO-04 | Phase 8 | Pending |
| POL-01 | Phase 9 | Pending |
| POL-02 | Phase 9 | Pending |
| POL-03 | Phase 9 | Pending |
| POL-04 | Phase 9 | Pending |
| POL-05 | Phase 9 | Pending |

**Coverage:**
- v1.1 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0

---
*Requirements defined: 2026-03-04*
*Last updated: 2026-03-04 after roadmap creation — all 18 requirements mapped to phases*
