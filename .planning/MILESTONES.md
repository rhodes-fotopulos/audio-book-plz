# Milestones

## v1.0 MVP (Shipped: 2026-03-04)

**Phases completed:** 6 phases, 17 plans
**Lines of code:** 9,515 Python
**Timeline:** 2 days (2026-03-03 → 2026-03-04)

**Delivered:** A fully local EPUB-to-audiobook pipeline that parses any EPUB, extracts characters via Qwen3 8B, matches them to real human voices from LibriTTS-P, synthesizes multi-voice audio via Chatterbox TTS on Apple Silicon MPS, and assembles the final audiobook.mp3 with chapter markers and ID3 metadata.

**Key accomplishments:**
1. EPUB parsing with hybrid front/back matter detection, dialogue tagging, and speech-ready JSON segments
2. LLM character extraction and speaker attribution using Qwen3 8B with chapter-level caching
3. Voice-character matching against 2,443 LibriTTS-P speakers via LLM trait comparison + embedding fallback
4. Chatterbox TTS synthesis on Apple Silicon MPS with checkpoint/resume for overnight runs
5. Audio assembly with LUFS normalization, chapter announcements, and ID3 metadata with chapter markers
6. Full end-to-end pipeline: `python main.py convert book.epub` delivers audiobook.mp3

**Known gaps at audit (all resolved by Phase 6):**
- WAV path mismatch between synthesizer and assembler — fixed in Phase 6
- CharacterProfile strict mode bug — fixed with model_validate()
- Announcer placeholder crash — fixed with graceful degradation
- Pipeline only ran phases 1-2 — fully wired in Phase 6

---


## v1.1 Pipeline Quality Improvements (Shipped: 2026-03-04)

**Phases completed:** 4 phases, 12 plans
**Lines of code:** 14,621 Python (total project, ~5,100 added in v1.1)
**Timeline:** 1 day (2026-03-04)

**Delivered:** Upgraded the audiobook pipeline from working prototype to professional quality — swapped TTS engine to Qwen3-TTS 1.7B (MLX native), added 14B LLM with emotion-aware dialogue detection, and built a full mastering pipeline with voice consistency verification and ACX-grade export.

**Key accomplishments:**
1. Qwen3-TTS 1.7B via mlx-audio — Apple Silicon native, 500-600 char chunks, SNR-filtered voice references with transcripts
2. 14B LLM upgrade with hybrid regex+LLM dialogue detection and speech-act tagging (spoken/thought/shouted/whispered)
3. Three-layer emotion system — character voice baselines, scene mood annotation, line-level overrides feeding post-processing
4. Professional mastering — pedalboard effects chain (noise gate, compressor, 80Hz highpass, limiter), Gaussian pauses, 8ms crossfades
5. Voice consistency verification — Resemblyzer speaker embeddings detect drift, regenerate outliers (cosine 0.60 threshold, 3 attempts)
6. ACX-grade export — 44.1kHz 192kbps CBR MP3 with proper loudness and peak specifications

**All audit gaps resolved by Phase 10:**
- CLI wiring bugs fixed (assemble --voice-threshold, synthesize --libritts-audio)
- Phase 8 and 9 VERIFICATION.md created with code evidence
- Phase 9 SUMMARY frontmatter added
- Pipeline docstring updated for v1.1

---

