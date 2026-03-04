# Technology Stack: v1.1 Audiobook Pipeline Improvements

**Project:** audio-book-plz v1.1
**Researched:** 2026-03-04
**Scope:** Stack ADDITIONS and CHANGES for 9 new features. Does NOT re-document existing v1.0 stack.
**Overall Confidence:** MEDIUM — Qwen3-TTS via MLX is new (Jan 2026), mlx-audio has active bugs; audio post-processing libraries are mature and well-verified.

---

## Existing Stack (Unchanged)

These remain from v1.0 — no changes needed:

| Technology | Version | Status |
|------------|---------|--------|
| Python | 3.11 | Keep (`>=3.11,<3.12`). MLX and mlx-audio require `>=3.10`, fully compatible. |
| EbookLib | 0.20 | Keep |
| beautifulsoup4 | 4.14.3 | Keep |
| lxml | 5.0+ | Keep |
| nltk | 3.8+ | Keep |
| typer | 0.24+ | Keep |
| rich | 13.0+ | Keep |
| ollama (client) | 0.6+ | Keep |
| pydantic | 2.0+ | Keep |
| sentence-transformers | 3.0+ | Keep |
| pydub | 0.25.1 | Keep — gains new crossfade usage |
| pyloudnorm | 0.2.0 | Keep — already a dependency |
| mutagen | 1.47.0 | Keep |
| ffmpeg | system | Keep |

---

## Stack REMOVALS

### Remove: chatterbox-tts

| Package | Action | Reason |
|---------|--------|--------|
| `chatterbox-tts` | **REMOVE** | Replaced by Qwen3-TTS via mlx-audio. Chatterbox requires PyTorch+MPS (~4GB VRAM), has a known memory leak requiring periodic cleanup, limited to ~280 char chunks, and lacks native emotion control. Qwen3-TTS via MLX uses Apple's unified memory more efficiently with no memory leak pattern, supports 500+ char chunks, and has built-in emotion/style instruction via natural language. |
| `torch` / `torchaudio` | **REMOVE from core deps** | No longer needed for TTS. MLX replaces PyTorch for inference. PyTorch remains as a transitive dependency of `sentence-transformers` but is no longer directly imported for TTS. This frees ~2GB of VRAM that PyTorch was reserving for MPS. |

**Migration note:** The `TTSEngine` class in `src/synthesis/tts_engine.py` must be rewritten. The current implementation wraps `ChatterboxTTS.from_pretrained()` with MPS migration — the new implementation will use `mlx_audio.tts.utils.load_model()` instead.

---

## Stack ADDITIONS

### 1. TTS Engine: mlx-audio (Qwen3-TTS)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `mlx` | >=0.31.0 | Apple Silicon ML framework | Apple's native array framework for M-series chips. Uses unified memory architecture (no CPU-to-GPU copy overhead). Supports Python 3.10-3.14, macOS 14+. Actively maintained by Apple ML Research. **HIGH confidence** — verified via PyPI (0.31.0 released 2026-02-27). |
| `mlx-audio[tts]` | >=0.3.1 | TTS inference wrapper for Qwen3-TTS | Provides `load_model()` and `generate_audio()` / `generate_custom_voice()` APIs for Qwen3-TTS models. Built on MLX framework. Requires ffmpeg for non-WAV output. **MEDIUM confidence** — v0.3.1 has known issues with audio dropout on long text (GitHub Issue #464) and chunking bugs on non-Base models. |

**Model selection:**

| Model | HuggingFace ID | Storage | Memory | Features | Recommendation |
|-------|---------------|---------|--------|----------|----------------|
| 1.7B CustomVoice 8-bit | `mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit` | 0.8 GB | ~3 GB | Voice cloning + emotion control via `instruct` param | **PRIMARY** — Use for all TTS. Supports both voice cloning from reference audio AND emotion/style instructions. 8-bit quantization fits comfortably in 16GB alongside Ollama teardown. |
| 1.7B Base bf16 | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | 2 GB | ~4 GB | Voice cloning only, best chunk handling | FALLBACK — Only if CustomVoice emotion control proves unreliable. Base model has more robust text chunking (`split_pattern` works correctly). No 8-bit quant available yet; bf16 uses more memory. |
| 0.6B CustomVoice 8-bit | `mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit` | 0.5 GB | ~1.5 GB | Voice cloning + emotion (weaker) | EMERGENCY FALLBACK — Use only if 16GB memory is too tight for 1.7B + post-processing. Emotion control is noticeably weaker than 1.7B. |

**Critical: Memory budget on 16GB M4 Mac:**

```
Qwen3-TTS 1.7B 8-bit:  ~3 GB
Post-processing (numpy): ~0.5 GB
Python + OS overhead:    ~3 GB
                         --------
Total during TTS phase:  ~6.5 GB (comfortable)

Ollama qwen3:8b Q4_K_M:  ~5 GB
Python + OS overhead:     ~3 GB
                          --------
Total during LLM phase:   ~8 GB (comfortable)
```

Sequential phase architecture remains correct — never run TTS and LLM simultaneously.

**Voice cloning with Qwen3-TTS:**
- Optimal reference audio: **10-15 seconds** of clean speech (quality scales linearly from 3s to 15s, then plateaus)
- Reference audio MUST include a text transcript for best quality
- Supports `ref_audio_max_seconds=30` as a safety trim
- The `generate_custom_voice()` method accepts an `instruct` parameter for natural language emotion/style control (e.g., "Speak in a deep, gravelly voice with quiet menace")

**API pattern (replaces Chatterbox API):**

```python
from mlx_audio.tts.utils import load_model

# Load once per session
model = load_model("mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit")

# Generate with voice cloning + emotion
results = list(model.generate_custom_voice(
    text="The door creaked open slowly.",
    speaker="Ryan",            # Predefined base speaker
    language="English",
    instruct="Tense and fearful, speaking in a hushed whisper.",
    ref_audio="path/to/reference.wav",  # Voice clone source
    ref_text="Transcript of the reference audio.",
))
audio = results[0].audio  # mlx array, not torch tensor
```

**Known issues (MEDIUM confidence — from GitHub issues, Jan-Feb 2026):**
1. Audio dropout in middle of long generations (Issue #464) — mitigate by keeping chunks under 600 chars
2. `split_pattern` ignored for CustomVoice/VoiceDesign models — may need manual chunking
3. Voice accent can shift after streaming changes (Issue #439) — pin to v0.3.1, test before upgrading
4. Performance: ~1000 chars/minute on M2; M4 should be faster but no published benchmarks yet

### 2. Audio Post-Processing: pedalboard

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pedalboard` | >=0.9.22 | Professional audio effects chain | Spotify's C++/JUCE-backed Python audio library. Provides Compressor, NoiseGate, HighpassFilter, LowpassFilter, Gain, Limiter as native C++ implementations (100-1000x faster than pure Python). Tested on Python 3.10-3.14, Apple Silicon ARM64 wheels available. **HIGH confidence** — verified via PyPI, released 2026-02-02. |

**Why pedalboard over alternatives:**
- **vs scipy.signal:** pedalboard provides studio-quality effects as one-liners. scipy requires manually designing filter coefficients, windowing, and chaining — verbose and error-prone for audio effects.
- **vs noisereduce:** noisereduce is spectral gating (good for background noise), NOT de-clicking. Pedalboard's NoiseGate handles transient clicks better. noisereduce is still useful as a supplement if needed.
- **vs pydub effects:** pydub's compressor and EQ are primitive (dBFS-based). Pedalboard uses JUCE's professional-grade implementations.
- **vs ffmpeg filters:** ffmpeg can do this via subprocess but is hard to debug, has no Python-native API, and error handling is poor.

**License warning: pedalboard is GPLv3.** This project is a local personal tool, not distributed as a library, so GPLv3 does not impose meaningful constraints. If distribution becomes a goal, the GPLv3 copyleft would require open-sourcing. This is acceptable for the current use case.

**Post-processing pipeline (maps to Feature #8):**

```python
import pedalboard
from pedalboard import (
    Compressor, Gain, HighpassFilter, LowpassFilter,
    Limiter, NoiseGate,
)

board = pedalboard.Pedalboard([
    # 1. Trim silence — use pydub.silence.detect_leading_silence() (already have pydub)
    # 2. De-click — NoiseGate removes low-level transient artifacts
    NoiseGate(threshold_db=-40, ratio=2.0, release_ms=50),
    # 3. High-pass filter — remove rumble below 80Hz
    HighpassFilter(cutoff_frequency_hz=80),
    # 4. Low-pass filter — remove harsh frequencies above 12kHz
    LowpassFilter(cutoff_frequency_hz=12000),
    # 5. Compress — even out volume; audiobook standard
    Compressor(threshold_db=-20, ratio=3.0, attack_ms=10, release_ms=100),
    # 6. Limiter — hard ceiling to prevent clipping
    Limiter(threshold_db=-1.0, release_ms=100),
    # 7. Gain — adjust overall level
    Gain(gain_db=0),  # Adjusted after LUFS measurement
])

# Apply to audio (numpy array)
processed = board(audio_array, sample_rate=24000)
```

**Integration with existing normalizer.py:** The existing `assembly/normalizer.py` uses pyloudnorm for LUFS measurement and normalization. The new post-processing pipeline runs BEFORE LUFS normalization. Order: raw TTS output -> pedalboard chain -> pyloudnorm LUFS normalize -> crossfade assembly.

### 3. Speaker Embedding for Voice Consistency: Resemblyzer

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `resemblyzer` | >=0.1.3 | Speaker embedding extraction for voice drift detection | Produces 256-dimensional speaker embeddings from audio. Lightweight (~17MB model), runs on CPU, ~1000x realtime on CPU. Use to compare each synthesized segment's embedding against the character's reference embedding — flag drift above a cosine similarity threshold. **MEDIUM confidence** — library is functionally stable but maintenance is inactive (no new PyPI releases in 12+ months). |

**Why Resemblyzer over SpeechBrain:**
- **SpeechBrain** (ECAPA-TDNN, 192-dim) is a better model (0.69% EER vs Resemblyzer's ~5% EER on VoxCeleb) but pulls in the full SpeechBrain toolkit (864KB package + hundreds of MB in PyTorch dependencies, many sub-packages). It is designed for research pipelines, not lightweight embedding extraction.
- **Resemblyzer** is a single-purpose library: load encoder, embed audio, get 256-dim vector. It uses PyTorch internally (which sentence-transformers already provides as a transitive dep), so no new heavy deps.
- For our use case (detecting if a TTS output drifted from its reference voice), Resemblyzer's accuracy is MORE than sufficient. We are comparing the same voice model's outputs against its own reference — not doing speaker verification across real-world speakers.

**Why NOT sentence-transformers for this:** sentence-transformers embeds TEXT, not audio. Voice consistency requires comparing AUDIO waveforms. Resemblyzer embeds audio signals directly.

**Voice consistency check pattern (maps to Feature #9):**

```python
from resemblyzer import VoiceEncoder, preprocess_wav
from pathlib import Path
import numpy as np

encoder = VoiceEncoder("cpu")

# Compute reference embedding once per character
ref_wav = preprocess_wav(Path("ref_clips/character_01.wav"))
ref_embedding = encoder.embed_utterance(ref_wav)

# After each TTS segment, check consistency
segment_wav = preprocess_wav(Path("output/seg_0042.wav"))
seg_embedding = encoder.embed_utterance(segment_wav)

similarity = np.dot(ref_embedding, seg_embedding)
if similarity < 0.80:  # Threshold — tune empirically
    # Flag for re-synthesis or manual review
    print(f"Voice drift detected: similarity={similarity:.3f}")
```

### 4. Ollama Model Upgrade

No new Python packages needed — this is an Ollama model swap.

| Model | Ollama Tag | Size | Memory | Purpose | Recommendation |
|-------|-----------|------|--------|---------|----------------|
| Qwen3 8B Q4_K_M | `qwen3:8b` (default) | 4.9 GB | ~5 GB | Current LLM for attribution | **KEEP as baseline** |
| Qwen3 8B Q8_0 | `qwen3:8b-q8_0` | 8.5 GB | ~9 GB | Higher quality attribution | **DO NOT USE** — 9GB VRAM + 3GB OS overhead = 12GB, leaving only 4GB for system. Too tight on 16GB. |
| Qwen3 14B Q4_K_M | `qwen3:14b-q4_K_M` | 9 GB | ~10 GB | Better reasoning for complex scenes | **RECOMMENDED UPGRADE** — 10GB fits in 16GB during LLM phase (TTS unloaded). Significantly better at nuanced emotion detection and dialogue attribution than 8B. Use `OLLAMA_KV_CACHE_TYPE=q8_0` to save ~1-2GB on context window. |

**Memory optimization for 14B on 16GB:**

```bash
# Set before running Ollama
export OLLAMA_KV_CACHE_TYPE=q8_0       # Halves KV cache memory (~2GB savings)
export OLLAMA_FLASH_ATTENTION=1         # Faster attention, slightly less memory
export OLLAMA_KEEP_ALIVE=0              # Unload immediately after use (frees memory for TTS)
```

**Migration:** Change `model` parameter in `src/attribution/llm_client.py` from `qwen3:8b` to `qwen3:14b-q4_K_M`. The Ollama API is identical — no code changes beyond the model name string.

---

## Stack Additions That Are NOT New Packages

These features use libraries already in the project:

### Larger TTS Chunks (Feature #2)

No new deps. Increase chunk target from ~280 chars to 500-600 chars in the text segmentation logic. Qwen3-TTS handles longer sequences than Chatterbox. Existing `pysbd` sentence boundary detection is reused; just change the join-until-limit threshold.

### Longer Voice References (Feature #3)

No new deps. LibriTTS-R clips are longer and higher quality than LibriTTS-P. Change the clip selection logic in `src/matching/clip_selector.py` to prefer 10-15 second clips (currently selects shorter clips for Chatterbox). LibriTTS-R data is a download, not a pip package.

**LibriTTS-R vs LibriTTS-P:**
- LibriTTS-P: 2,443 speakers, personality annotations, variable audio quality
- LibriTTS-R: 2,456 speakers, restored audio quality (Miipher speech restoration), 585 hours at 24kHz
- Use LibriTTS-R for AUDIO (higher quality references) and LibriTTS-P for ANNOTATIONS (personality traits)
- Both datasets use compatible speaker IDs

### Three-Layer Emotion System (Feature #5)

No new deps. Implemented in the attribution LLM prompts and passed through to Qwen3-TTS's `instruct` parameter. The three layers (character baseline + scene mood + line overrides) are composed into a single natural language instruction string:

```python
instruct = f"{character_baseline}. {scene_mood}. {line_override}."
# Example: "Deep gravelly voice, speaks slowly. Tense and dark scene. Shouting angrily."
```

### LLM-Based Dialogue Detection (Feature #6)

No new deps. Replaces regex-based dialogue detection with LLM prompting via existing Ollama client. Include dialogue/narration classification in the attribution prompt rather than as a separate call.

### Randomized Pause Timing (Feature #7)

No new deps. Use Python `random` stdlib + existing pydub `AudioSegment.silent()` to generate variable-length silence segments between speech segments. Ranges: sentence boundary (200-400ms), paragraph (400-800ms), chapter (1000-2000ms).

### Crossfade Assembly (part of Feature #8)

No new deps. Use existing pydub's `segment1.append(segment2, crossfade=50)` for 50ms crossfades between segments within a chapter. Already in pydub API.

### Silence Trimming (part of Feature #8)

No new deps. Use existing pydub's `detect_leading_silence()` to trim excessive silence from TTS output head/tail before post-processing.

---

## Summary: New Dependencies for pyproject.toml

```toml
[project]
dependencies = [
    # === EXISTING (unchanged) ===
    "EbookLib>=0.20",
    "beautifulsoup4>=4.14",
    "lxml>=5.0",
    "nltk>=3.8",
    "typer>=0.24",
    "rich>=13.0",
    "ollama>=0.6",
    "pydantic>=2.0",
    "sentence-transformers>=3.0",
    "pydub>=0.25.1",
    "pyloudnorm>=0.2.0",
    "mutagen>=1.47.0",
    # === REMOVED ===
    # "chatterbox-tts>=0.1.6",  # REMOVED — replaced by mlx-audio
    # === ADDED ===
    "mlx>=0.31.0",
    "mlx-audio[tts]>=0.3.1",
    "pedalboard>=0.9.22",
    "resemblyzer>=0.1.3",
]
```

**Net dependency change:**
- Removed: `chatterbox-tts` (and its heavy transitive deps including direct torch/torchaudio management)
- Added: `mlx` (~50MB), `mlx-audio[tts]` (~depends on mlx), `pedalboard` (~20MB native wheels), `resemblyzer` (~small, uses existing torch)
- PyTorch remains as transitive dep of `sentence-transformers` and `resemblyzer` but is no longer directly managed or imported for TTS

### Installation Changes

```bash
# System dependencies (unchanged)
brew install ffmpeg

# Ollama model upgrade
ollama pull qwen3:14b-q4_K_M

# Download Qwen3-TTS model (auto-downloaded on first use by mlx-audio,
# or pre-download with huggingface-cli)
huggingface-cli download mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit

# Verify MLX works
python -c "import mlx.core as mx; print(mx.default_device())"
# Should print: Device(gpu, 0)
```

**CRITICAL: PyTorch install order no longer matters.** With Chatterbox removed, the fragile "install torch BEFORE chatterbox" requirement is eliminated. MLX is a standalone framework with no PyTorch dependency for TTS inference.

---

## Alternatives Considered (New Additions Only)

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| TTS Engine | mlx-audio + Qwen3-TTS 1.7B | Chatterbox (current) | Memory leak, 280 char limit, no emotion control, requires PyTorch MPS hacks |
| TTS Engine | mlx-audio + Qwen3-TTS 1.7B | F5-TTS via MLX | F5-TTS lacks emotion/style instruction parameter; voice cloning only without expressiveness control |
| TTS Engine | mlx-audio + Qwen3-TTS 1.7B | Kokoro TTS | Kokoro is lighter (~1GB) but lacks voice cloning entirely; uses fixed voices only |
| Audio Effects | pedalboard | noisereduce + scipy.signal | noisereduce is spectral gating only (no compressor, EQ, limiter). scipy requires manual filter design. Two separate packages vs one integrated chain. |
| Audio Effects | pedalboard | pydub built-in effects | pydub's compressor is primitive (dBFS threshold only). No proper EQ, limiter, or noise gate. |
| Audio Effects | pedalboard | ffmpeg -af filter chain | No Python-native API; subprocess stderr parsing for errors; hard to debug; no programmatic access to intermediate results |
| Voice Consistency | resemblyzer | SpeechBrain ECAPA-TDNN | SpeechBrain pulls 864KB+ package plus heavy deps; ECAPA-TDNN accuracy (0.69% EER) is overkill for same-model drift detection |
| Voice Consistency | resemblyzer | pyannote-audio | pyannote is a full diarization pipeline, not a lightweight embedder; massive dependency footprint |
| Voice Consistency | resemblyzer | Custom embedding via sentence-transformers | sentence-transformers embeds TEXT not AUDIO; wrong modality for voice waveform comparison |
| LLM Model | qwen3:14b Q4_K_M | qwen3:8b Q8_0 | Q8_0 at 8B uses 9GB — only marginally better quality than Q4_K_M at 14B which also uses ~10GB but has far more parameters and reasoning capability |
| LLM Model | qwen3:14b Q4_K_M | qwen3:8b Q4_K_M (current) | 14B significantly outperforms 8B on nuanced tasks (emotion detection, complex dialogue attribution). Fits in 16GB with KV cache quantization. |

---

## What NOT to Add

| Avoid | Why | What to Use Instead |
|-------|-----|---------------------|
| `noisereduce` as standalone dep | Spectral gating is not de-clicking. Adds PyTorch-based processing when pedalboard's C++ NoiseGate is faster and more appropriate for transient artifact removal. | pedalboard `NoiseGate` |
| `sox` / `pysox` | System-level dependency with OS-specific installation issues. pysox is unmaintained. Everything sox does, pedalboard + pydub + ffmpeg can do. | pedalboard |
| `librosa` | Heavy dependency (pulls numba, llvmlite, soundfile, etc.) just for audio feature extraction. Resemblyzer handles voice embeddings; pedalboard handles effects. No gap librosa fills. | resemblyzer + pedalboard |
| `speechbrain` | Massive research toolkit when we need one function (embed audio). 864KB package + hundreds of MB in transitive deps. | resemblyzer (17MB model, single purpose) |
| `pyannote-audio` | Full speaker diarization pipeline. We do not need diarization — we already know who speaks each line from LLM attribution. We only need embedding comparison for drift detection. | resemblyzer |
| `transformers` (HuggingFace) directly | mlx-audio already handles model loading internally. Adding transformers directly creates version conflicts (mlx-audio pins `transformers<5.0.0`). | Let mlx-audio manage its own transformers dep |
| Running Qwen3-TTS 1.7B bf16 | bf16 uses ~4GB vs 8-bit's ~3GB. On 16GB with post-processing overhead, the extra 1GB matters. Quality difference between 8-bit and bf16 is minimal for TTS. | 8-bit quantized model |
| Python 3.12+ | Still risky. While Chatterbox is removed (eliminating the main 3.12 blocker), sentence-transformers and its transitive deps may have edge-case issues on 3.12. mlx-audio pins `transformers<5.0.0` which may conflict with newer Python. | Stay on Python 3.11 |
| `torch` as explicit dependency | With Chatterbox gone, PyTorch should flow in as a transitive dep of sentence-transformers and resemblyzer, not be explicitly managed. Remove `torch==2.6.0` from install instructions. | Let pip resolve torch version from transitive deps |

---

## Version Compatibility Matrix (New Additions)

| Package | Python 3.11 | macOS 14+ ARM64 | Interop Notes |
|---------|-------------|-----------------|---------------|
| `mlx>=0.31.0` | YES (3.10-3.14) | YES (native Apple Silicon) | No conflict with PyTorch — separate framework |
| `mlx-audio[tts]>=0.3.1` | YES (3.10+) | YES | Pins `transformers<5.0.0`. May conflict if sentence-transformers pulls transformers>=5.0. Test carefully. |
| `pedalboard>=0.9.22` | YES (3.10-3.14) | YES (ARM64 wheel: `cp311-macosx_11_0_arm64`) | No dependency conflicts. Pure C++ extension, no Python deps. GPLv3 license. |
| `resemblyzer>=0.1.3` | YES (3.5+) | YES (pure Python + PyTorch) | Uses PyTorch for inference. Shares torch installation with sentence-transformers. |
| Ollama `qwen3:14b-q4_K_M` | N/A (system) | YES | ~10GB memory. Use `OLLAMA_KV_CACHE_TYPE=q8_0` on 16GB systems. |

**Potential conflict to watch:** mlx-audio pins `transformers<5.0.0`. If `sentence-transformers>=3.0` requires `transformers>=5.0` in a future release, pip will fail to resolve. Current sentence-transformers 3.x works with transformers 4.x, so this is safe NOW but could break on upgrade. Pin `sentence-transformers<4.0` if needed.

---

## Memory Budget by Phase (Updated for v1.1)

| Phase | Primary Consumer | Memory | Budget Status |
|-------|-----------------|--------|---------------|
| 1. EPUB Parsing | Python + lxml | ~0.5 GB | Comfortable |
| 2. LLM Attribution | Ollama qwen3:14b Q4_K_M | ~10 GB | Tight but fits with KV cache quant |
| 3. Voice Matching | sentence-transformers (CPU) | ~1.5 GB | Comfortable |
| 4. TTS Synthesis | Qwen3-TTS 1.7B 8-bit (MLX) | ~3.5 GB | Comfortable |
| 4b. Post-processing | pedalboard + pyloudnorm | ~0.5 GB | Runs alongside TTS or after |
| 5. Audio Assembly | pydub + ffmpeg | ~1 GB | Comfortable |
| 5b. Voice Consistency | resemblyzer (CPU) | ~0.5 GB | Can run alongside assembly |

**Key constraint:** Phase 2 (LLM) is now the tightest phase at ~10GB for 14B Q4_K_M. If this proves unstable, fall back to 8B Q4_K_M (~5GB). Phase 4 (TTS) is now MUCH more comfortable — Qwen3-TTS 1.7B 8-bit via MLX uses ~3GB vs Chatterbox's ~4GB + PyTorch MPS overhead.

---

## Sources

### HIGH Confidence (PyPI / Official Docs)
- MLX 0.31.0: https://pypi.org/project/mlx/ (verified 2026-03-04, released 2026-02-27)
- mlx-audio 0.3.1: https://pypi.org/project/mlx-audio/ (verified 2026-03-04, released 2026-01-29)
- pedalboard 0.9.22: https://pypi.org/project/pedalboard/ (verified 2026-03-04, released 2026-02-02)
- pyloudnorm 0.2.0: https://pypi.org/project/pyloudnorm/ (verified 2026-03-04, released 2026-01-04)
- noisereduce 3.0.3: https://pypi.org/project/noisereduce/ (verified 2026-03-04, released 2024-10-06)
- MLX documentation: https://ml-explore.github.io/mlx/build/html/install.html
- Pedalboard documentation: https://spotify.github.io/pedalboard/
- Ollama qwen3:14b-q4_K_M: https://ollama.com/library/qwen3:14b-q4_K_M

### MEDIUM Confidence (GitHub / Community Sources)
- mlx-audio Qwen3-TTS README: https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md
- mlx-audio releases: https://github.com/Blaizzy/mlx-audio/releases
- mlx-audio Issue #464 (audio dropout): https://github.com/Blaizzy/mlx-audio/issues/464
- mlx-audio Issue #439 (accent loss after streaming change): https://github.com/Blaizzy/mlx-audio/issues/439
- Qwen3-TTS Apple Silicon guide: https://github.com/kapi2800/qwen3-tts-apple-silicon
- MLX Community Qwen3-TTS models: https://huggingface.co/collections/mlx-community/qwen3-tts
- Qwen3-TTS 1.7B CustomVoice 8-bit: https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit
- Resemblyzer: https://github.com/resemble-ai/Resemblyzer (functionally stable, inactive maintenance)
- Resemblyzer PyPI: https://pypi.org/project/Resemblyzer/
- Ollama memory requirements guide: https://localllm.in/blog/ollama-vram-requirements-for-local-llms
- Ollama Mac optimization: https://insiderllm.com/guides/ollama-mac-setup-optimization/

### LOW Confidence (Single Source / Blog Posts)
- Qwen3-TTS performance ~1000 chars/min on M2: https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos (single blog post, M2 not M4)
- Qwen3-TTS voice cloning 10-15s optimal: https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning (blog, not official docs)
- 1.7B needs ~6GB RAM (non-quantized): https://github.com/kapi2800/qwen3-tts-apple-silicon (refers to non-quantized; 8-bit should be ~3GB)
- LibriTTS-R: https://www.openslr.org/141/ (dataset page, not a pip package)

---

*Stack research for: audio-book-plz v1.1 improvements*
*Focus: Qwen3-TTS MLX migration, audio post-processing, voice consistency, LLM upgrade*
*Researched: 2026-03-04*
