# Audio Book Plz

## What This Is

A local Python app that converts EPUB files into multi-voice audiobooks (.mp3). Uses a local LLM (Ollama + Qwen 3 8B) for speaker attribution and character analysis, Chatterbox TTS for voice synthesis with voice cloning from real human recordings (LibriTTS-P dataset), and runs entirely on an M4 Mac with 16GB unified memory. Built for personal use — converting a collection of dialogue-heavy fiction (fantasy, thriller, literary) into listenable audiobooks with distinct character voices.

## Core Value

Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Parse EPUB files into ordered, speech-ready text segments with dialogue/narration tagging
- [ ] Extract character profiles from novel text using local LLM
- [ ] Attribute each dialogue line to the correct speaker using local LLM
- [ ] Match characters to real human voices from LibriTTS-P based on voice traits
- [ ] Synthesize audio for each text segment using Chatterbox TTS with per-character voice cloning
- [ ] Assemble segment audio into chapter MP3s and a full audiobook MP3
- [ ] CLI interface for running full pipeline or individual phases
- [ ] Checkpoint/resume support for long-running synthesis
- [ ] Sequential LLM/TTS phases to stay within 16GB memory budget

### Out of Scope

- GUI or web interface — CLI only for personal use
- Real-time streaming — batch processing is fine
- Non-fiction / reference book optimization — optimizing for dialogue-heavy fiction
- Multi-language support — English only for v1
- Cloud/API-based TTS — fully local, no external services
- Mobile app — desktop only
- User documentation beyond basic README — personal tool

## Context

**Hardware**: M4 Mac with 16GB unified memory. Apple Silicon's unified architecture means GPU (MPS) shares all 16GB — no separate VRAM. Strategy is to run LLM and TTS in separate phases, never simultaneously, keeping peak usage under ~10GB.

**Key libraries**:
- `ebooklib` + `beautifulsoup4` for EPUB parsing
- Ollama with `qwen3:8b` (Q4_K_M) for LLM tasks (~5-6GB GPU)
- Chatterbox TTS for voice synthesis (~4GB MPS) with MPS acceleration and CPU fallback for FFT ops
- LibriTTS-P dataset (2,443 speakers with human-annotated voice descriptions) for voice references
- `pydub` + `ffmpeg` for audio assembly and MP3 encoding
- `sentence-transformers` (`all-MiniLM-L6-v2`) as fallback for voice matching

**Architecture**: Five sequential phases — EPUB parsing, LLM speaker attribution, voice matching, TTS synthesis, audio assembly. Each phase produces intermediate artifacts (JSON, WAV files) enabling checkpoint/resume and debugging individual steps.

**Performance expectations**: ~3-10 seconds per segment with MPS GPU. A typical novel (~80K words, ~4K segments) takes ~3-11 hours of generation. Designed for overnight processing with checkpoint/resume.

**Voice cloning approach**: Chatterbox clones from a ~10-second reference clip of a real human voice. LibriTTS-P provides clean 24kHz audiobook recordings from LibriVox volunteers, each annotated with voice traits (gender, pitch, warmth, etc.). Characters are matched to speakers via LLM trait comparison with embedding similarity as fallback.

**TTS chunking**: Chatterbox has a ~300 character limit per generation call. Segments exceeding this are split at sentence boundaries, keeping chunks under 280 chars.

## Constraints

- **Hardware**: M4 Mac, 16GB unified memory — LLM and TTS cannot run simultaneously
- **TTS Engine**: Chatterbox TTS — ~300 char limit per call, MPS-accelerated with FFT CPU fallback
- **LLM Runtime**: Ollama — local only, `qwen3:8b` Q4_K_M quantization for 16GB budget
- **Voice Dataset**: LibriTTS-P — requires ~28GB disk for train-clean-100 subset, one-time download
- **Audio Backend**: ffmpeg required as system dependency for MP3 encoding

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Chatterbox TTS over other TTS engines | Best open-source voice cloning quality, runs on Apple Silicon with MPS | — Pending |
| LibriTTS-P for voice references | 2,443 real human voices with annotated traits, CC BY 4.0, clean 24kHz audio | — Pending |
| Ollama + Qwen 3 8B for LLM | Best instruction-following 8B model for 16GB systems, simple local setup | — Pending |
| Sequential phases (not concurrent) | Memory safety — never exceed 16GB by running LLM and TTS separately | — Pending |
| Per-segment WAV intermediates | Enables checkpoint/resume and per-segment debugging at cost of disk space | — Pending |
| LLM-based voice matching with embedding fallback | LLM understands nuanced character traits better; embeddings handle large casts | — Pending |

---
*Last updated: 2026-03-03 after initialization*
