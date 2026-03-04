# Stack Research

**Domain:** Local EPUB-to-audiobook converter with multi-voice TTS and LLM speaker attribution
**Researched:** 2026-03-03
**Confidence:** MEDIUM-HIGH (core libraries verified via PyPI; Chatterbox MPS support partially verified via community sources)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11 | Runtime | Chatterbox is developed and tested on Python 3.11; avoids edge-case incompatibilities with pinned TTS dependencies. 3.12+ may break pinned Chatterbox sub-dependencies. |
| Ollama (runtime) | latest | Local LLM server | Zero-config local LLM serving; manages model weights, quantization, and GPU scheduling. The only viable local option that works out of the box on Apple Silicon without CUDA. |
| `ollama` (Python client) | 0.6.1 | Ollama API client | Official Python client; supports structured JSON output via format parameter. Use `ollama.chat()` with Pydantic schemas for reliable structured extraction. |
| `chatterbox-tts` | 0.1.6 | TTS voice synthesis | Best open-source zero-shot voice cloning quality in its class (Resemble AI, 2025). Supports MPS via community-verified workaround — requires torch installed before chatterbox to avoid version conflicts. |
| PyTorch | 2.6.0 | Tensor backend for TTS | Must be installed BEFORE chatterbox-tts to avoid pip resolving to a CUDA-only wheel. MPS is available on macOS 12.3+ with Apple Silicon. Use `torch.backends.mps.is_available()` to confirm. |

### EPUB Parsing

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `ebooklib` | 0.20 | EPUB2/EPUB3 reading | De-facto standard Python EPUB library. Handles spine ordering, metadata, and chapter iteration. Has not been updated recently but is stable and covers all needed EPUB structures. |
| `beautifulsoup4` | 4.14.3 | HTML-to-text extraction from EPUB chapters | EPUB chapters are XHTML; bs4 strips tags and preserves reading order. Use `lxml` parser for speed. |
| `lxml` | 6.0.2 | Parser backend for bs4 | Fastest XML/HTML parser available for bs4. Required for reliable XHTML handling in EPUB chapter content. |

### LLM Interaction

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `pydantic` | 2.12.5 | Structured output validation | Ollama's format parameter accepts a Pydantic-generated JSON schema. Use BaseModel subclasses to define expected LLM output shapes (character lists, dialogue attributions). Eliminates manual JSON parsing. |

### Audio Processing

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `soundfile` | 0.13.1 | WAV file reading/writing | Chatterbox TTS outputs raw numpy arrays; soundfile writes them to disk as WAV segments. Apple Silicon ARM64 wheel available. Simpler API than scipy.io.wavfile for this use case. |
| `pydub` | 0.25.1 | Audio assembly and MP3 export | Concatenates WAV segments into chapter MP3s. Has not had a PyPI release since 2021 but is functionally complete for this use case (concat + export). Requires ffmpeg as a system dependency. |
| ffmpeg | system dep | MP3 encoding, audio normalization | Required by pydub for all non-WAV formats. Install via Homebrew: `brew install ffmpeg`. The standard Homebrew build includes libmp3lame (MP3 support). |

### Voice Matching

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `sentence-transformers` | 5.2.3 | Embedding-based voice matching fallback | Encodes character trait descriptions and LibriTTS-P speaker annotations into vectors for cosine similarity matching. `all-MiniLM-L6-v2` (22MB, 384-dim) is fast enough to run on CPU after TTS teardown. |

### CLI and Developer Experience

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `typer` | 0.24.1 | CLI interface | Type-hint-driven CLI with subcommand support. Each pipeline phase becomes a typer command; `python main.py parse`, `python main.py attribute`, etc. Requires Python 3.10+, aligned with project requirement. |
| `rich` | 14.3.3 | Terminal output formatting and progress | Progress bars, per-segment status, colored logging. Works alongside typer natively; both from the Textualize ecosystem. Use `rich.progress.track()` for synthesis loops. |
| `tqdm` | 4.67.3 | Inner-loop progress meters | Lightweight alternative to rich.progress for tight synthesis loops where rich's overhead may interfere. Use tqdm for segment-level loops inside rich panels. |

### Text Segmentation

| Library | Version | Purpose | Why Recommended |
|---------|---------|---------|-----------------|
| `pysbd` | latest | Sentence boundary detection | Rule-based sentence boundary disambiguation. Handles edge cases (abbreviations, ellipses, dialogue punctuation) better than naive split-on-period. Used to chunk segments at ≤280 characters for Chatterbox's ~300 char limit. Available via `pip install pysbd`. |

---

## Installation

```bash
# System dependencies (macOS)
brew install ffmpeg python@3.11

# Create virtual environment with Python 3.11 specifically
python3.11 -m venv .venv
source .venv/bin/activate

# CRITICAL: Install PyTorch FIRST with MPS support before chatterbox-tts
# This prevents pip from pulling a CUDA-only torch wheel as a transitive dependency
pip install torch==2.6.0 torchaudio==2.6.0

# Core pipeline
pip install chatterbox-tts==0.1.6
pip install ebooklib==0.20
pip install beautifulsoup4==4.14.3
pip install lxml==6.0.2
pip install pydantic==2.12.5

# Audio processing
pip install soundfile==0.13.1
pip install pydub==0.25.1

# LLM client
pip install ollama==0.6.1

# Voice matching
pip install sentence-transformers==5.2.3

# CLI and DX
pip install typer==0.24.1
pip install rich==14.3.3
pip install tqdm==4.67.3

# Text segmentation
pip install pysbd

# Ollama model (run separately, not pip)
ollama pull qwen3:8b-q4_K_M
```

**MPS verification:**
```python
import torch
print(torch.backends.mps.is_available())  # Must be True before synthesis
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `chatterbox-tts` | Kokoro TTS, F5-TTS, XTTS v2 | Kokoro has lighter memory footprint (~1GB); choose it if Chatterbox's 4GB MPS usage proves unstable. F5-TTS has better multilingual support. XTTS v2 (Coqui) is a proven alternative but the project is abandoned. |
| `ollama` (client) | `httpx` + direct REST | Direct REST is viable; ollama client adds structured format support and streaming. Use httpx only if ollama client introduces blocking issues. |
| `pydantic` | Manual JSON parsing | Only if Ollama's structured output format causes incompatibilities; manual parsing is fragile with LLM outputs. |
| `sentence-transformers` (all-MiniLM-L6-v2) | LLM-only voice matching, Ollama embeddings | All-MiniLM-L6-v2 is 22MB and fast on CPU. Ollama embeddings require a running Ollama server (memory cost). Use sentence-transformers as the fallback when LLM-based matching is too slow for large casts. |
| `typer` | `click`, `argparse` | Click is lower-level but more configurable; argparse needs no dependencies. Use typer unless Python 3.10 compatibility is removed as a requirement. |
| `pysbd` | spaCy sentencizer, NLTK PunktTokenizer | spaCy requires downloading language models (~50MB). NLTK is less accurate on dialogue-heavy fiction (abbreviations, em-dashes). pysbd is rule-based, zero-download, accurate on fiction. |
| `soundfile` | `scipy.io.wavfile`, `wave` (stdlib) | scipy adds a large dependency. wave (stdlib) lacks float32 support needed for Chatterbox output. soundfile handles all required formats. |
| `pydub` | `pydub-ng`, `ffmpeg-python` (direct) | pydub-ng is a maintained fork but introduces risk as a non-official package. ffmpeg-python (subprocess wrapper) is lower-level but more control over encoding parameters. Stick with pydub 0.25.1 unless bugs surface. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Coqui TTS / XTTS | Project abandoned in 2024; no maintenance, breaking Python version incompatibilities | `chatterbox-tts` |
| `openai` TTS, ElevenLabs API | Cloud/paid; violates fully-local requirement | `chatterbox-tts` |
| BookNLP | Java dependency, heavyweight NLP pipeline designed for quote attribution; overkill when Qwen3 8B can do attribution via prompting | Ollama + Qwen3 prompt |
| LangChain / LlamaIndex | Adds 50+ transitive dependencies for functionality Ollama client covers directly | `ollama` Python client directly |
| `spacy` en_core_web_sm | 50MB download just for sentence tokenization; spaCy's dependency parse is overkill for chunking at sentence boundaries | `pysbd` |
| Python 3.12+ | Chatterbox 0.1.6 pins dependencies (s3tokenizer, pkuseg) that have C-extension build failures on 3.12+ in community reports | Python 3.11 |
| `pydub-ng` / `pozalabs-pydub` | Unofficial forks; introduce maintenance risk; pydub 0.25.1 is functionally complete for concatenation + MP3 export | `pydub` 0.25.1 |
| Running LLM and TTS simultaneously | Exceeds 16GB unified memory budget (~5-6GB for qwen3:8b + ~4GB for chatterbox = ~10GB; overhead pushes system into swap) | Sequential phase architecture; teardown Ollama before loading Chatterbox |

---

## Stack Patterns by Variant

**For the synthesis phase (TTS active):**
- Unload Ollama first: `ollama stop qwen3:8b-q4_K_M` or kill the Ollama process
- Load Chatterbox with `device="mps"` if `torch.backends.mps.is_available()` else `"cpu"`
- Process segments in batches; persist WAV files to disk after each segment (enables checkpoint/resume)
- Set env var `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` to disable MPS memory caching and free memory aggressively

**For the LLM phases (character extraction, speaker attribution):**
- Ensure Chatterbox is not loaded in memory
- Use `ollama.chat()` with `format=CharacterList.model_json_schema()` for reliable structured output
- Use `temperature=0` for speaker attribution (deterministic); allow higher temperature for character trait description

**For voice matching:**
- Run sentence-transformers on CPU; it uses ~200MB and does not need MPS
- Load the model once, encode all speaker descriptions and LibriTTS-P annotations in batch, then do all cosine similarity in numpy

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `torch==2.6.0` + `chatterbox-tts==0.1.6` | Python 3.11, macOS 14+ ARM64 | Must install torch first. Community-verified via Issue #336 on resemble-ai/chatterbox. |
| `ebooklib==0.20` + `beautifulsoup4==4.14.3` | Python 3.9+ | ebooklib uses bs4 internally; both must be present. |
| `pydub==0.25.1` + ffmpeg (Homebrew) | macOS 14+ | Homebrew ffmpeg includes libmp3lame. Verify with `ffmpeg -codecs | grep mp3`. |
| `sentence-transformers==5.2.3` | Python 3.10+, torch 2.x | Requires Python 3.10+; aligns with typer and chatterbox-tts floor. |
| `typer==0.24.1` | Python 3.10+ | Requires Python 3.10+; enforces consistent floor across dev tooling. |
| `pydantic==2.12.5` + `ollama==0.6.1` | Python 3.9+ | Ollama client accepts Pydantic v2 model_json_schema() output directly in format parameter. |

---

## Chatterbox MPS Installation Warning

Chatterbox does not officially document MPS support, but community testing (GitHub Issue #336, Hugging Face spaces) confirms MPS works on macOS 14+ with the following constraints:

1. Install `torch==2.6.0` and `torchaudio==2.6.0` BEFORE `pip install chatterbox-tts`
2. Some FFT operations in Chatterbox fall back to CPU even when the model is on MPS — this is expected behavior and is not an error
3. The Turbo model variant has a known Float64-not-supported MPS error (Issue #93 on devnen/Chatterbox-TTS-Server); use the standard 500M model (`resemble-ai/chatterbox`)
4. Verify MPS is active: `torch.backends.mps.is_available()` must return `True`

**Confidence: MEDIUM** — Verified via community sources and GitHub issues, not official Resemble AI documentation.

---

## Sources

- PyPI: EbookLib 0.20 — https://pypi.org/project/EbookLib/ (verified 2026-03-03)
- PyPI: chatterbox-tts 0.1.6 — https://pypi.org/project/chatterbox-tts/ (verified 2026-03-03)
- PyPI: ollama 0.6.1 — https://pypi.org/project/ollama/ (verified 2026-03-03)
- PyPI: beautifulsoup4 4.14.3 — https://pypi.org/project/beautifulsoup4/ (verified 2026-03-03)
- PyPI: lxml 6.0.2 — https://pypi.org/project/lxml/ (verified 2026-03-03)
- PyPI: pydub 0.25.1 — https://pypi.org/project/pydub/ (verified 2026-03-03, last updated 2021)
- PyPI: soundfile 0.13.1 — https://pypi.org/project/soundfile/ (verified 2026-03-03)
- PyPI: sentence-transformers 5.2.3 — https://pypi.org/project/sentence-transformers/ (verified 2026-03-03)
- PyPI: pydantic 2.12.5 — https://pypi.org/project/pydantic/ (verified 2026-03-03)
- PyPI: typer 0.24.1 — https://pypi.org/project/typer/ (verified 2026-03-03)
- PyPI: rich 14.3.3 — https://pypi.org/project/rich/ (verified 2026-03-03)
- PyPI: tqdm 4.67.3 — https://pypi.org/project/tqdm/ (verified 2026-03-03)
- Chatterbox MPS: GitHub Issue #336 — https://github.com/resemble-ai/chatterbox/issues/336 (MEDIUM confidence)
- Chatterbox MPS: GitHub Issue #93 Turbo float64 bug — https://github.com/devnen/Chatterbox-TTS-Server/issues/93 (MEDIUM confidence)
- Ollama model: qwen3:8b-q4_K_M — https://ollama.com/library/qwen3:8b-q4_K_M (verified 2026-03-03)
- LibriTTS-P: GitHub line/LibriTTS-P — https://github.com/line/LibriTTS-P (CC BY 4.0)
- Ollama structured output with Qwen3: https://www.glukhov.org/post/2025/09/llm-structured-output-with-ollama-in-python-and-go/ (MEDIUM confidence)

---
*Stack research for: local EPUB-to-audiobook converter, M4 Mac, multi-voice TTS, LLM speaker attribution*
*Researched: 2026-03-03*
