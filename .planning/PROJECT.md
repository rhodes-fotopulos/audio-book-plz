# Audio Book Plz

## What This Is

A local Python app that converts EPUB files into multi-voice audiobooks (.mp3). Uses a local LLM (Ollama + Qwen 3 8B) for speaker attribution and character analysis, Chatterbox TTS for voice synthesis with voice cloning from real human recordings (LibriTTS-P dataset), and runs entirely on an M4 Mac with 16GB unified memory. A single command — `python main.py convert book.epub` — runs the full five-phase pipeline and delivers a finished audiobook with distinct character voices, chapter markers, and ID3 metadata.

## Core Value

Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## Requirements

### Validated

- ✓ Parse EPUB files into ordered, speech-ready text segments with dialogue/narration tagging — v1.0
- ✓ Extract character profiles from novel text using local LLM — v1.0
- ✓ Attribute each dialogue line to the correct speaker using local LLM — v1.0
- ✓ Match characters to real human voices from LibriTTS-P based on voice traits — v1.0
- ✓ Synthesize audio for each text segment using Chatterbox TTS with per-character voice cloning — v1.0
- ✓ Assemble segment audio into a full audiobook MP3 with chapter markers — v1.0
- ✓ CLI interface for running full pipeline or individual phases — v1.0
- ✓ Checkpoint/resume support for long-running synthesis — v1.0
- ✓ Sequential LLM/TTS phases to stay within 16GB memory budget — v1.0

### Active

- [ ] Edit attribution JSON by hand and re-run synthesis from that point
- [ ] Custom pronunciation overrides via YAML for character names and proper nouns
- [ ] Dry-run that estimates segment count, synthesis time, and disk usage
- [ ] Preview each character's voice (3-second sample) before full synthesis
- [ ] Individual chapter MP3 files in addition to full audiobook
- [ ] M4B export with embedded chapter markers for audiobook player support
- [ ] Emotion/prosody controls per character type

### Out of Scope

- GUI or web interface — CLI only for personal use
- Real-time streaming — batch processing is fine
- Non-fiction / reference book optimization — optimizing for dialogue-heavy fiction
- Multi-language support — English only (Qwen 3 8B, Chatterbox, LibriTTS-P are English-optimized)
- Cloud/API-based TTS — fully local, no external services
- Mobile app — desktop only
- Offline mode — real-time is not relevant to batch pipeline
- Per-chapter voice style variation — creates voice inconsistency

## Context

Shipped v1.0 with 9,515 LOC Python across 6 phases and 17 plans.
Tech stack: Python 3.11, Ollama + Qwen3 8B, Chatterbox TTS, LibriTTS-P (2,443 speakers), pydub + ffmpeg, sentence-transformers.
Architecture: Five sequential phases — EPUB parsing → LLM attribution → voice matching → TTS synthesis → audio assembly. Each phase produces intermediate JSON/WAV artifacts enabling checkpoint/resume.
Hardware: M4 Mac with 16GB unified memory. LLM and TTS run in separate phases with explicit Ollama teardown at the boundary.

**Known tech debt from v1.0:**
- clear_cache exported but not exposed via CLI command
- VoiceMap(**data) on cache-hit path should use model_validate()
- Phases 2-5 never formally verified (VERIFICATION.md missing) — code works per SUMMARY claims and Phase 6 integration testing

## Constraints

- **Hardware**: M4 Mac, 16GB unified memory — LLM and TTS cannot run simultaneously
- **TTS Engine**: Chatterbox TTS — ~300 char limit per call, MPS-accelerated with FFT CPU fallback
- **LLM Runtime**: Ollama — local only, `qwen3:8b` Q4_K_M quantization for 16GB budget
- **Voice Dataset**: LibriTTS-P — requires ~28GB disk for train-clean-100 subset, one-time download
- **Audio Backend**: ffmpeg required as system dependency for MP3 encoding

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Chatterbox TTS over other TTS engines | Best open-source voice cloning quality, runs on Apple Silicon with MPS | ✓ Good — MPS works with CPU fallback for FFT |
| LibriTTS-P for voice references | 2,443 real human voices with annotated traits, CC BY 4.0, clean 24kHz audio | ✓ Good — sufficient speaker variety |
| Ollama + Qwen 3 8B for LLM | Best instruction-following 8B model for 16GB systems, simple local setup | ✓ Good — structured output reliable with /no_think |
| Sequential phases (not concurrent) | Memory safety — never exceed 16GB by running LLM and TTS separately | ✓ Good — essential architecture constraint |
| Per-segment WAV intermediates | Enables checkpoint/resume and per-segment debugging at cost of disk space | ✓ Good — overnight runs survive crashes |
| LLM-based voice matching with embedding fallback | LLM understands nuanced character traits better; embeddings handle large casts | ✓ Good — two-tier approach covers all cast sizes |
| Python 3.11 required | Chatterbox pins sub-dependencies that break on 3.12+ | ✓ Good — avoids compatibility issues |
| Chatterbox standard 500M model only | Turbo variant has Float64 MPS error | ⚠️ Revisit — check if turbo fixed in future versions |
| LUFS -19.0 normalization target | Audiobook standard -23 to -18, slightly louder for personal listening | ✓ Good — pending real listening test |
| 64k CBR mono MP3 | ACX/Audible standard for spoken word | ✓ Good |

---
*Last updated: 2026-03-04 after v1.0 milestone*
