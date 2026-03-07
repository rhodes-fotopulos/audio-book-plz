# Audio Book Plz

## What This Is

A local Python app that converts EPUB files into multi-voice audiobooks (.mp3). Uses a local LLM (Ollama + Qwen3 14B/8B) for speaker attribution, character analysis, and emotion tagging, Qwen3-TTS 1.7B via MLX for voice synthesis with voice cloning from real human recordings (LibriTTS-R dataset), and runs entirely on an M4 Mac with 16GB unified memory. A single command — `python main.py convert book.epub` — runs the full pipeline and delivers a professionally mastered audiobook with distinct character voices, speech-act-aware post-processing, voice consistency verification, and ACX-grade MP3 export.

## Core Value

Feed in an EPUB, get out a multi-voice audiobook where each character has a distinct, fitting voice cloned from a real human recording.

## Current Milestone: v1.2 Voice Expression

**Goal:** Unify voice data model, simplify pipeline by removing incompatible emotion system, optimize LLM usage with caching and optional flags, and improve synthesis performance.

**Target features:**
- Merge voice_qualities + voice_baseline into single voice_profile (eliminate duplication)
- Feed voice_profile description to Qwen3-TTS as style conditioning per character
- Use voice_profile attributes in voice matching (trait_matcher, embedding_matcher)
- Remove emotion system (incompatible with Base model voice cloning)
- Speech-act post-processing opt-in via --speech-act-fx flag
- LLM result caching for trait matcher to skip redundant calls on re-runs

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

### Validated (v1.1)

- ✓ Replace Chatterbox TTS with Qwen3-TTS 1.7B via MLX for better voice cloning and emotion control — Phase 7
- ✓ Increase TTS chunk size from ~280 to ~500-600 chars for fewer seams and better prosody — Phase 7
- ✓ Select 10-15s voice reference clips with SNR filtering for better cloning fidelity — Phase 7
- ✓ Upgrade LLM to qwen3:14b Q4_K_M or qwen3:8b Q8_0 for fewer attribution errors — Phase 8
- ✓ Three-layer emotion system: character voice baseline + scene mood + line-level overrides — Phase 8
- ✓ Hybrid regex+LLM dialogue detection with speech-act tagging (spoken/thought/shouted/whispered) — Phase 8
- ✓ Randomized Gaussian pause timing with context-aware ranges (5 boundary types) — Phase 9
- ✓ Post-processing pipeline: noise gate, compress, highpass EQ, limiter, crossfade, 44.1kHz 192kbps ACX export — Phase 9
- ✓ Voice consistency pass: Resemblyzer embedding comparison to detect and regenerate drifted segments — Phase 9

### Validated (v1.2)

- ✓ Unified voice_profile field replacing voice_qualities and voice_baseline — Phase 11
- ✓ Voice style conditioning passed to Qwen3-TTS per character — Phase 11
- ✓ Voice matching uses unified voice_profile for better speaker selection — Phase 11
- ✓ Emotion system removed (Base model cannot combine voice cloning with emotion instructions) — Phase 12
- ✓ Speech-act post-processing made opt-in via --speech-act-fx flag — Phase 12
- ✓ LLM result caching for trait matcher — Phase 12

### Active

None — all v1.2 requirements addressed. Phase 13 (Synthesis Performance) remains.

### Future

- [ ] Edit attribution JSON by hand and re-run synthesis from that point
- [ ] Custom pronunciation overrides via YAML for character names and proper nouns
- [ ] Dry-run that estimates segment count, synthesis time, and disk usage
- [ ] Preview each character's voice (3-second sample) before full synthesis
- [ ] Individual chapter MP3 files in addition to full audiobook
- [ ] M4B export with embedded chapter markers for audiobook player support

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

Shipped v1.0 with 9,515 LOC across 6 phases/17 plans, then v1.1 with 4 phases/12 plans.
Tech stack: Python 3.11, Ollama + Qwen3 14B/8B, Qwen3-TTS 1.7B via mlx-audio, LibriTTS-R, pedalboard, Resemblyzer, pydub + ffmpeg.
Architecture: Six sequential phases — EPUB parsing → LLM attribution → voice matching → TTS synthesis → voice consistency verification → audio assembly with mastering. Each phase produces intermediate JSON/WAV artifacts enabling checkpoint/resume.
Hardware: M4 Mac with 16GB unified memory. LLM and TTS run in separate phases with explicit Ollama teardown at the boundary.

**v1.1 shipped:** Swapped Chatterbox → Qwen3-TTS 1.7B (MLX), added 3-layer emotion system, hybrid dialogue detection with speech-act tagging, Gaussian pause timing, pedalboard mastering chain, Resemblyzer voice consistency verification, and ACX-grade MP3 export (44.1kHz 192kbps CBR).

**Known tech debt:**
- clear_cache exported but not exposed via CLI command
- VoiceMap(**data) on cache-hit path should use model_validate()
- Phases 2-5 (v1.0) never formally verified — code works per SUMMARY claims and Phase 6 integration testing

## Constraints

- **Hardware**: M4 Mac, 16GB unified memory — LLM and TTS cannot run simultaneously
- **TTS Engine**: Qwen3-TTS 1.7B via mlx-audio — ~500-600 char chunks, Apple Silicon native (MLX), with Chatterbox fallback
- **LLM Runtime**: Ollama — local only, `qwen3:14b` Q4_K_M (with 8B Q8_0 auto-fallback for <12GB RAM)
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
| 64k CBR mono MP3 | ACX/Audible standard for spoken word | Superseded by 192kbps CBR in v1.1 |
| Qwen3-TTS 1.7B via MLX over Chatterbox | Apple Silicon native, larger chunks, better cloning — v1.1 | ✓ Good — MLX inference stable |
| Resemblyzer for voice consistency | Speaker embeddings for drift detection, cosine 0.60 threshold | ✓ Good — catches voice drift reliably |
| Pedalboard for mastering chain | NoiseGate → Compressor → HighPass(80Hz) → Limiter, LUFS-validated | ✓ Good — measurable audio improvement |
| Gaussian pause timing | Natural-sounding variation vs fixed silence, 5 boundary types | ✓ Good — eliminates robotic pacing |
| Speech-act post-processing over TTS instruct | Base model ignores instruct prompts with cloned voices; post-process volume/speed instead | ✓ Good — reliable with any voice reference |
| Emotion system removal | Qwen3-TTS Base cannot combine voice cloning + emotion instructions | ✓ Good — pipeline simplified, no unused code |
| Speech-act FX opt-in (default OFF) | LUFS normalization undoes volume deltas; keep off until needed | ✓ Good — clean default behavior |
| Trait matcher LLM caching | Cache key includes profile + available candidates for proper invalidation | ✓ Good — saves N LLM calls on re-runs |
| Milestone restructure 5→3 phases | Emotion removal eliminates need for 2 planned phases | ✓ Good — focused scope |

---
*Last updated: 2026-03-07 after Phase 12*
