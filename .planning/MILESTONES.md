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

