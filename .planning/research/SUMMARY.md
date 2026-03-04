# Project Research Summary

**Project:** audio-book-plz
**Domain:** Local EPUB-to-multi-voice audiobook pipeline (Python, Ollama + Chatterbox TTS, Apple Silicon)
**Researched:** 2026-03-03
**Confidence:** MEDIUM-HIGH

## Executive Summary

This project is a sequential, phase-isolated batch pipeline that converts EPUB fiction into multi-voice audiobooks using fully local AI — no cloud services, no per-call costs, no internet dependency. Experts in this space build similar systems as five discrete phases: EPUB parsing, LLM-based speaker attribution, voice-character matching, TTS synthesis, and audio assembly. The defining constraint is a 16GB unified memory budget on an M4 Mac, which forces LLM and TTS models to be kept strictly separate in memory — they can never co-reside. This constraint shapes every architectural decision: sequential phases, explicit teardown between phases, and file-presence checkpointing so long overnight runs can safely resume after interruption.

The recommended approach is a Python 3.11 pipeline using Ollama with Qwen3 8B for local LLM work (character extraction and speaker attribution), Chatterbox TTS for zero-shot voice cloning against LibriTTS-P reference audio, and pydub + ffmpeg for audio assembly. The combination of EPUB parsing, fully local LLM attribution, LibriTTS-P voice matching, and per-segment checkpointing is genuinely novel — no existing open-source tool does all of these together. The pipeline delivers real competitive differentiation: automated per-line dialogue attribution across a full novel, character voices cloned from 2,443 real human recordings matched by trait descriptions, and a resumable overnight synthesis run.

The key risks are concentrated in two areas. First, Chatterbox MPS support on Apple Silicon is community-verified but not officially documented, meaning the synthesis phase requires careful environment setup (PyTorch installed before Chatterbox, `PYTORCH_ENABLE_MPS_FALLBACK=1` set, MPS health-checked before long runs). Second, LLM attribution quality degrades silently when Ollama's default context window is too small — the model processes only the first portion of a long chapter and returns plausible-looking but partially hallucinated results. Both risks have clear mitigations that must be treated as first-class design requirements, not optional checks.

## Key Findings

### Recommended Stack

The stack is well-defined by the project's constraints. Python 3.11 is required (Chatterbox pins sub-dependencies that break on 3.12+). The LLM layer is Ollama serving Qwen3 8B at Q4_K_M quantization, accessed via the official `ollama` Python client with Pydantic-structured JSON output — no LangChain or LlamaIndex needed. The TTS layer is Chatterbox TTS 0.1.6 with PyTorch 2.6.0, where torch must be installed first to prevent pip pulling a CUDA-only wheel. Audio assembly uses pydub 0.25.1 and ffmpeg (Homebrew). Voice matching uses sentence-transformers with the `all-MiniLM-L6-v2` model as a fast, 22MB CPU-resident fallback for large character casts.

See `.planning/research/STACK.md` for full version matrix, installation order, and Chatterbox MPS caveats.

**Core technologies:**
- **Python 3.11**: Runtime — required by Chatterbox's pinned sub-dependencies; 3.12+ breaks C-extensions
- **Ollama + Qwen3 8B (Q4_K_M)**: Local LLM — zero-config server, structured JSON output via Pydantic, ~4.5-6GB VRAM
- **Chatterbox TTS 0.1.6**: Voice synthesis — best open-source zero-shot voice cloning; MPS-accelerated on Apple Silicon with community workarounds
- **PyTorch 2.6.0**: Tensor backend — must install before Chatterbox; MPS available on macOS 12.3+ Apple Silicon
- **ebooklib + BeautifulSoup4 + lxml**: EPUB parsing — de-facto standard stack for EPUB2/EPUB3 extraction
- **pydub + ffmpeg**: Audio assembly — concatenation and MP3 encoding; ffmpeg via Homebrew for libmp3lame
- **sentence-transformers (all-MiniLM-L6-v2)**: Voice matching fallback — 22MB, CPU-resident, cosine similarity for large casts
- **pysbd**: Text chunking — rule-based sentence boundary detection, handles fiction punctuation edge cases
- **typer + rich**: CLI and progress — phase-level subcommands, progress bars for multi-hour synthesis runs

### Expected Features

The pipeline delivers capabilities no existing open-source tool provides as a complete package. All listed tools (epub2tts, ebook2audiobook, epub_to_audiobook, Alexandria, audiobook-creator) do subsets; none combines local EPUB parsing + local LLM attribution + LibriTTS-P voice cloning + CLI + checkpoint/resume.

See `.planning/research/FEATURES.md` for competitor analysis table and full MVP definition.

**Must have (table stakes):**
- EPUB parsing with chapter extraction and front matter filtering — the entry point; every comparable tool requires this
- Speech-ready text segmentation — raw EPUB HTML cannot reach LLM or TTS; cleaning is mandatory
- Single narrator TTS synthesis — baseline capability required before multi-voice adds value
- Chapter-level audio output — listener expectation; one file per chapter minimum
- Full-book assembled audio — consolidated MP3 output expected by any audiobook tool
- Checkpoint/resume for long runs — a novel takes 3-11 hours; crash recovery is non-negotiable
- CLI phase-level invocation — batch operation requires headless, phase-addressable commands
- Basic progress reporting — silent tools feel broken during multi-hour synthesis runs
- Audio metadata (ID3 tags) — required for Audiobookshelf/Plex library organisation

**Should have (competitive differentiators):**
- LLM-based character extraction — no existing EPUB tool does this automatically from fiction text
- LLM-based per-line dialogue attribution — the core feature; local, on EPUB, at book scale
- Voice cloning from LibriTTS-P reference audio — 2,443 real human recordings, not synthetic presets
- LLM + embedding-based voice-character trait matching — novelty; no existing tool does this
- Narrator vs. dialogue tagging — stable narrator voice across entire book, distinct character voices
- Per-segment WAV intermediates with speaker identity — enables targeted re-synthesis and debugging
- Sequential LLM/TTS memory phase isolation — hardware constraint made explicit as architecture

**Defer (v2+):**
- M4B output with embedded chapter markers — functional MP3 output is sufficient for v1
- Emotion/prosody annotation per character — risk of quality degradation without extensive listening tests
- Larger LLM swap (post-validation) — defer until v1 attribution errors are understood
- Batch library processing — single-book pipeline must be stable first
- GUI/web interface — anti-feature for this personal-use CLI tool

### Architecture Approach

The architecture is a five-phase sequential pipeline with file-presence checkpointing between phases. Each phase writes a typed JSON artifact to disk; the pipeline orchestrator checks artifact presence before running a phase, enabling trivial resume. Phase 4 (TTS synthesis) adds per-segment WAV checkpointing within the phase because it is the longest-running step (3-11 hours). Memory isolation is enforced at the Phase 2/3 → Phase 4 boundary: Ollama is explicitly stopped and Python memory is freed before Chatterbox loads. Pydantic models define the contract between every phase — raw dict passing is explicitly rejected. See `.planning/research/ARCHITECTURE.md` for data flow diagrams and anti-patterns.

**Major components:**
1. **CLI Layer (typer)** — parses subcommands (`parse`, `attribute`, `match`, `synthesize`, `assemble`, `run`), routes to pipeline orchestrator
2. **Pipeline Orchestrator** — sequences phases, checks artifact presence for resume, enforces memory budget at phase boundaries
3. **Phase 1: EPUB Parser** — ebooklib + BeautifulSoup4 → `segments.json` (spine-ordered, HTML-cleaned, type-tagged segments)
4. **Phase 2: LLM Attributor** — Ollama/Qwen3 8B with Pydantic structured output → `attributed.json` + `characters.json` (per-line speaker labels, character profiles)
5. **Phase 3: Voice Matcher** — LLM trait comparison + sentence-transformers fallback → `voice_map.json` (character-to-LibriTTS-P speaker mapping)
6. **Phase 4: TTS Synthesizer** — Chatterbox on MPS, 280-char chunking, per-segment WAV checkpointing → `wavs/` directory
7. **Phase 5: Audio Assembler** — pydub chapter-by-chapter concatenation + ffmpeg MP3 encoding → `chapters/*.mp3` + `audiobook.mp3`
8. **Pydantic Models** — shared schemas (Segment, AttributedSegment, VoiceMap) enforce inter-phase contracts and catch schema drift at boundaries

### Critical Pitfalls

1. **Chatterbox 40-second audio cutoff** — enforce ≤280 character chunks at sentence boundaries; validate chunk sizes before any synthesis call; this is a hard architectural limit, not advisory
2. **Chatterbox MPS instability on Apple Silicon** — install PyTorch before Chatterbox; set `PYTORCH_ENABLE_MPS_FALLBACK=1`; run a 10-segment health check before any long run; keep CPU fallback codepath
3. **Ollama context window silently truncating chapters** — explicitly set `num_ctx=32768` per attribution request; chunk chapters to 2,000-3,000 words maximum before LLM calls; log token estimates per request
4. **LLM attribution hallucination and cascade misattribution** — include full character registry in every attribution prompt; flag "Unknown" attributions explicitly; validate all attribution results against the character registry; post-attribution sanity check for unregistered character names
5. **Simultaneous model memory pressure (OOM crash)** — explicitly call `ollama stop` + verify with `ollama ps` before loading Chatterbox; add `gc.collect()` + `torch.mps.empty_cache()` at every phase boundary

**Moderate pitfalls to address per phase:**
- EPUB structure chaos: use spine order only; word-count filter (skip < 100 words); structure preview before any LLM work
- Quotation mark edge cases: normalise all quote variants to ASCII; handle multi-paragraph dialogue continuation
- Checkpoint corruption: atomic WAV write (`.tmp` rename); validate all "complete" segments on resume
- Disk space exhaustion: estimate storage upfront; chapter-level WAV cleanup after assembly
- Voice reference quality mismatch: make voice-character assignments human-reviewable with preview before synthesis

## Implications for Roadmap

Based on research, the natural phase structure follows the feature dependency graph from FEATURES.md and the memory isolation requirements from ARCHITECTURE.md. The pipeline is linear and each phase's output is the next phase's input — this maps cleanly to development phases that can each be validated independently.

### Phase 1: Foundation and EPUB Parsing

**Rationale:** EPUB parsing is the mandatory entry point for everything downstream. It is also where EPUB structure chaos (Pitfall 6) and quotation mark edge cases (Pitfall 7) must be solved permanently. Getting clean, typed, speech-ready segments out of arbitrary EPUB files is the hardest parsing challenge — solve it first, validate it on multiple EPUBs, and everything downstream becomes deterministic.

**Delivers:** Working CLI skeleton (`typer`), EPUB parsing pipeline producing `segments.json`, HTML cleaning and text normalisation, sentence boundary segmentation (`pysbd`) with ≤280 char enforcement, narration/dialogue type tagging, front matter filtering, structure preview command, per-book output directory with book slug namespacing.

**Addresses:** EPUB parsing, speech-ready text output, narration/dialogue tagging, CLI phase-level invocation (partial), basic progress reporting (partial).

**Avoids:** EPUB structure chaos (Pitfall 6), quotation mark edge cases (Pitfall 7), Chatterbox chunk size cutoff (Pitfall 1 — prevention happens here).

**Research flag:** Standard patterns; no deeper research needed for this phase.

---

### Phase 2: LLM Character Extraction and Speaker Attribution

**Rationale:** Attribution depends on parsing output (Phase 1). Character extraction must precede attribution — you cannot attribute to characters you have not identified. This phase contains the highest intellectual complexity (LLM prompting, structured output, character registry with alias resolution) and the most subtle failure modes (context truncation, hallucination, cascade misattribution). It should be validated independently before any TTS work begins, because attribution errors discovered late require re-synthesis of entire character voice tracks.

**Delivers:** Character extraction producing `characters.json` (with full alias lists), per-chapter dialogue attribution producing `attributed.json`, Ollama integration with Pydantic structured output, explicit `num_ctx=32768` configuration, character registry with alias resolution, chapter-level chunking for LLM context management, "Unknown" attribution flagging and logging, post-attribution sanity check against registry.

**Uses:** Ollama 0.6.1, Qwen3 8B Q4_K_M, Pydantic 2.12.5, ollama Python client with `format=` JSON schema.

**Implements:** Phase 2 (LLM Attributor) + character registry in `characters.json`.

**Avoids:** Ollama context truncation (Pitfall 3), LLM hallucination/cascade misattribution (Pitfall 4), one-LLM-call-per-segment anti-pattern (send full chapter per call).

**Research flag:** May benefit from research during planning — Qwen3 8B structured output reliability and optimal prompt structure for fiction attribution are not fully characterised. Recommend testing on a sample chapter before building the full phase.

---

### Phase 3: Voice-Character Matching

**Rationale:** Matching depends on character profiles from Phase 2. Voice assignments must be confirmed by a human before synthesis begins — wrong assignments discovered after a 10-hour synthesis run are very expensive to fix. This phase is architecturally simple (reads CSVs, runs embeddings, writes JSON) but requires a human review step that should be designed in from the start, not retrofitted.

**Delivers:** LibriTTS-P metadata indexing (pre-filtered CSV), LLM-based trait matching for primary characters, sentence-transformers cosine similarity fallback for large casts, `voice_map.json` with `confirmed` flag per assignment, voice preview tool (10-second test clip per candidate), 3 candidate references per character before locking.

**Uses:** sentence-transformers 5.2.3 (all-MiniLM-L6-v2), Ollama for semantic matching, LibriTTS-P train-clean-360 subset.

**Implements:** Phase 3 (Voice Matcher) component.

**Avoids:** Voice reference quality mismatch (Pitfall 8) — interactive review step; simultaneous model memory pressure (Pitfall 5) — sentence-transformers runs on CPU, Ollama used for matching only.

**Research flag:** LibriTTS-P dataset structure and download scope (full dataset is 100GB+; only train-clean-360 subset needed) should be confirmed during planning. Pre-filtering strategy for the voice index needs validation.

---

### Phase 4: TTS Synthesis

**Rationale:** Synthesis is the longest phase (3-11 hours per novel) and the highest-stakes in terms of failure recovery. It depends on all three prior phases. The critical constraints — MPS health check, sequential memory isolation (Ollama unloaded before Chatterbox loads), per-segment WAV checkpointing, atomic write, RMS silence detection — are all non-negotiable and must be designed in from the start, not added when problems surface.

**Delivers:** Chatterbox TTS integration with MPS acceleration, per-segment WAV synthesis with 280-char chunks, per-segment WAV checkpointing (file-presence resume), atomic `.tmp`-rename write pattern, MPS health check before long runs, `PYTORCH_ENABLE_MPS_FALLBACK=1` environment setup, RMS silence check per segment with auto-regeneration, Ollama teardown verification before model load, storage estimation at startup, chapter-level WAV cleanup after assembly, sample rate normalisation to 24kHz, progress reporting (rich + tqdm).

**Uses:** Chatterbox TTS 0.1.6, PyTorch 2.6.0 (MPS), torchaudio, soundfile, rich, tqdm.

**Implements:** Phase 4 (TTS Synthesizer) component, memory.py utilities, text_chunker.py validation.

**Avoids:** Chatterbox 40-second cutoff (Pitfall 1), MPS instability (Pitfall 2), memory pressure OOM (Pitfall 5), checkpoint corruption (Pitfall 9), disk exhaustion (Pitfall 10), silent WAV generation (Pitfall 13), FFT MPS fallback performance trap (Pitfall 14).

**Research flag:** High — Chatterbox MPS behavior on Apple Silicon is community-verified but not officially documented. Recommend a focused MPS validation sprint at the start of this phase before writing production synthesis logic.

---

### Phase 5: Audio Assembly and Polish

**Rationale:** Assembly is the simplest phase technically but is where the output quality becomes tangible. Audio metadata (ID3 tags) and chapter-level concatenation strategy (chapter-by-chapter to avoid OOM) are both mandatory for a usable result. This phase also includes the v1.x polish features (human-editable attribution JSON, dry-run preview, per-character voice preview) that are cheap to add once the baseline pipeline works.

**Delivers:** Chapter-by-chapter WAV concatenation (avoiding full-book memory load), ffmpeg MP3 encoding at 128kbps, full-book `audiobook.mp3` assembly via ffmpeg concat (not in-memory), ID3 metadata embedding (title, author, chapter number, chapter name), chapter MP3 output with correct sequence naming, human-editable `attributed.json` with clear schema, dry-run/preview mode (segment count, synthesis time estimate, disk usage), per-character voice sample preview (3-second clips before full synthesis).

**Uses:** pydub 0.25.1, ffmpeg (Homebrew), mutagen or eyeD3 for ID3 tagging.

**Implements:** Phase 5 (Audio Assembler) component, full pipeline `run` command.

**Avoids:** In-memory full-book concatenation OOM (anti-pattern from ARCHITECTURE.md — concatenate chapter-by-chapter, use ffmpeg for final join), sample rate mismatch (Pitfall 11 — normalised in Phase 4).

**Research flag:** Standard patterns; ID3 tagging with mutagen is well-documented. No deeper research needed.

---

### Phase Ordering Rationale

- **Dependency chain is strict**: each phase produces the artifact the next consumes; no reordering is possible
- **Validate before synthesising**: attribution errors are far cheaper to fix before a 10-hour synthesis run; Phases 1-3 are fast (minutes to hours), Phase 4 is slow (overnight)
- **Human review at Phase 3**: voice-character assignments require a review step before synthesis; building this into Phase 3 prevents the most expensive failure mode (wrong voice for a major character across thousands of segments)
- **Memory isolation is architecture**: the Phase 2/3 → Phase 4 boundary is where LLM teardown is enforced; both phases must be complete before the TTS model loads
- **Assembly last, polish bundled**: Phase 5 is the natural home for v1.x polish features; they all depend on a working synthesis pipeline and are cheap once the pipeline is validated

### Research Flags

Phases needing deeper research during planning:
- **Phase 2 (LLM Attribution):** Qwen3 8B structured output reliability for fiction dialogue attribution, optimal prompt engineering for speaker identification across large casts, and alias resolution prompt design are not fully characterised. Test on a sample chapter before building the full phase.
- **Phase 4 (TTS Synthesis):** Chatterbox MPS stability on Apple Silicon requires a focused validation sprint. Community sources confirm it works with workarounds, but the failure modes are specific and must be characterised before production synthesis logic is written.
- **Phase 3 (Voice Matching):** LibriTTS-P dataset download scope and pre-filtering strategy for the voice index need validation. Full dataset is 100GB+; only a subset is needed, and the right subset depends on the voice demographics required.

Phases with standard patterns (skip research-phase):
- **Phase 1 (EPUB Parsing):** ebooklib + BeautifulSoup4 + pysbd is well-documented; patterns are established in comparable tools.
- **Phase 5 (Audio Assembly):** pydub + ffmpeg + mutagen are all mature, well-documented libraries with established patterns for audiobook output.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Core libraries verified via PyPI with exact versions. Chatterbox MPS support is MEDIUM — community-verified via GitHub issues, not official docs. PyTorch/Chatterbox install ordering is verified. |
| Features | MEDIUM-HIGH | Competitor analysis is HIGH confidence (direct GitHub repo inspection). Multi-voice LLM attribution as a feature is MEDIUM — emerging space, few mature reference implementations. |
| Architecture | HIGH | Architecture derives directly from confirmed project constraints (16GB memory budget, sequential phases, file-presence checkpointing). Patterns are verified against comparable pipeline implementations. |
| Pitfalls | MEDIUM | Core pitfalls (Chatterbox cutoff, Ollama context, MPS instability, memory pressure) verified via GitHub issues and official docs. Some pitfalls (silent WAV generation, cascade misattribution at scale) are inferred from analogous pipeline experience where direct sources were sparse. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Chatterbox MPS production reliability:** Community sources confirm it works, but the specific failure conditions (SDPA sequence length, FFT ops that fall back to CPU, memory pressure thresholds) are not fully documented. Address with a MPS validation sprint at the start of Phase 4 planning.
- **Ollama structured output with Qwen3 8B for fiction attribution:** The structured output format parameter works in principle, but prompt engineering for complex fiction dialogue (multi-speaker scenes, interior monologue, ambiguous attribution) is not characterised. Address with a prompt validation step at the start of Phase 2 planning.
- **LibriTTS-P subset scope:** The full dataset is 100GB+. The right download strategy (train-clean-360 only? filtered by quality?) and pre-indexing approach need validation before Phase 3 planning. Address during Phase 3 research-phase.
- **Chatterbox Turbo model exclusion:** Research confirms the Turbo variant has a known Float64 MPS error. The standard 500M model must be used. This must be explicitly documented in environment setup to prevent future confusion.
- **pydub maintenance status:** pydub 0.25.1 has not had a PyPI release since 2021. It is functionally complete for this use case, but if bugs surface in concatenation or MP3 export, `pydub-ng` (unofficial fork) or direct ffmpeg subprocess calls are the fallback. Monitor for issues during Phase 5.

## Sources

### Primary (HIGH confidence)
- PyPI package pages (EbookLib, chatterbox-tts, ollama, beautifulsoup4, lxml, pydub, soundfile, sentence-transformers, pydantic, typer, rich, tqdm) — verified 2026-03-03
- GitHub: epub_to_audiobook, epub2tts, ebook2audiobook, Alexandria, audiobook-creator — feature analysis via direct repo inspection
- Ollama structured outputs documentation — https://docs.ollama.com/capabilities/structured-outputs
- LibriTTS-P GitHub — https://github.com/line/LibriTTS-P
- W3C EPUB TTS spec — https://www.w3.org/TR/epub-tts-10/

### Secondary (MEDIUM confidence)
- Chatterbox MPS: GitHub Issue #336 — https://github.com/resemble-ai/chatterbox/issues/336
- Chatterbox Turbo Float64 bug: GitHub Issue #93 — https://github.com/devnen/Chatterbox-TTS-Server/issues/93
- Chatterbox 40-second cutoff: GitHub Issue #76 — https://github.com/resemble-ai/chatterbox/issues/76
- Chatterbox MPS Apple Silicon: Hugging Face — https://huggingface.co/Jimmi42/chatterbox-tts-apple-silicon-code
- Ollama context window configuration — https://www.arsturn.com/blog/how-to-increase-ollama-context-window-size
- Ollama large context degradation: GitHub Issue #9890 — https://github.com/ollama/ollama/issues/9890
- Context rot research 2025 — https://research.trychroma.com/context-rot
- LangGraph TTS Architecture (checkpointing patterns) — https://vadim.blog/2026/01/18/langgraph-tts-therapeutic-audio-architecture
- PyTorch MPS memory management — https://docs.pytorch.org/docs/stable/notes/mps.html
- MultiActor-Audiobook paper (ISCA 2025) — https://www.isca-archive.org/interspeech_2025/park25e_interspeech.pdf

### Tertiary (LOW confidence)
- Audiobook narration user expectations — https://www.spoken.press/ai-audiobook-faq
- ElevenLabs audiobook guide 2026 (marketing) — https://elevenlabs.io/blog/how-to-make-an-audiobook
- LibriTTS paper (speaker quality variance) — https://arxiv.org/abs/1904.02882

---
*Research completed: 2026-03-03*
*Ready for roadmap: yes*
