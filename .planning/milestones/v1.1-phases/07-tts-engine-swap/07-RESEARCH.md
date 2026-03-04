# Phase 7: TTS Engine Swap - Research

**Researched:** 2026-03-04
**Domain:** TTS engine migration (Chatterbox -> Qwen3-TTS via mlx-audio on Apple Silicon)
**Confidence:** MEDIUM (mlx-audio is young library, v0.3.1, some bugs recently fixed)

## Summary

Phase 7 replaces Chatterbox TTS with Qwen3-TTS 1.7B Base model via the mlx-audio library for voice cloning on Apple Silicon. The mlx-audio library (v0.3.1, MIT license) provides a Python API that loads Qwen3-TTS models as MLX-native weights, generates audio as `mx.array` objects, and supports voice cloning via `ref_audio` + `ref_text` parameters. The 1.7B Base model achieves state-of-the-art WER (1.24 on test-en) and handles texts up to 2000 words. Audio output is `mx.array` at the model's native sample rate, convertible to numpy for WAV saving via `soundfile.write()`.

Key risks: mlx-audio v0.3.1 had two notable bugs (#464 audio dropout on M5, #439 accent loss in cloned voices) — both now closed. Memory management uses MLX's Metal API (`mx.core.clear_cache()`, `mx.core.set_cache_limit()`) rather than PyTorch's MPS cache. The library is actively developed but young — a validation spike before full build is prudent.

**Primary recommendation:** Use `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` for voice cloning via mlx-audio's `load_model()` + `model.generate(text, ref_audio, ref_text)` API. Build an adapter layer (`QwenTTSEngine`) behind the existing `TTSEngine` interface, with Chatterbox as configurable fallback.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Voice reference preparation: Keep existing LibriVox voice bank for Phase 7 — reprocess clips for Qwen3-TTS requirements, upgrade bank later
- Fallback policy: Auto-fallback on Qwen3-TTS failure — if a segment fails with Qwen3, automatically retry with Chatterbox
- Log each fallback event as it happens AND show a summary when the run completes
- Warn user if fallback rate exceeds a threshold, but continue the run (don't abort)
- Chunk splitting: Never break mid-sentence — always split at sentence boundaries, even if chunk is shorter than 500 chars
- Split by speaker — separate chunks when speaker changes, even within a paragraph
- Keep both chunking strategies available — new chunker for Qwen3-TTS, old chunker accessible for Chatterbox fallback
- Migration experience: Auto-archive old v1.0 checkpoints — move to backup folder automatically, then start fresh
- Tag each checkpoint with engine name, version, and settings used (full metadata)
- Full re-run only — don't mix engines in a single audiobook, archive old and re-synthesize everything
- TTS engine configurable as global default with per-project override

### Claude's Discretion
- Voice reference clip selection strategy (single vs multiple)
- SNR filter failure handling
- Transcript generation method
- Retry-before-fallback logic
- Short paragraph merging strategy
- Memory management approach for MLX Metal cache

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TTS-01 | Pipeline synthesizes audio using Qwen3-TTS 1.7B via mlx-audio instead of Chatterbox TTS | mlx-audio `load_model("mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")` + `model.generate()` API verified; voice cloning via `ref_audio`/`ref_text` params |
| TTS-02 | TTS engine manages MLX Metal cache to remain memory-stable across full-book synthesis runs | MLX provides `mx.core.clear_cache()`, `mx.core.set_cache_limit()`, `mx.core.get_active_memory()`, `mx.core.get_peak_memory()` for Metal memory management |
| TTS-03 | Pipeline pre-splits text into 500-600 char chunks at paragraph/sentence boundaries before TTS generation | Qwen3-TTS handles texts up to 2000 words; NLTK `sent_tokenize` already in codebase for sentence splitting; new chunker targets 500-600 chars at sentence boundaries |
| TTS-04 | Voice references use 10-15 second SNR-filtered clips from LibriTTS-R with bundled transcripts | LibriTTS-R includes normalized text files alongside WAVs (`*trans.tsv`); Qwen3-TTS `ref_text` param accepts transcript for cloning quality; existing clip_selector.py selects longest clip — needs enhancement for SNR filtering and 10-15s target |
| TTS-05 | Chatterbox preserved as fallback behind config flag during migration | Current `TTSEngine` class is Chatterbox-specific; refactor to engine interface with `ChatterboxEngine` and `QwenTTSEngine` implementations; config flag selects engine |
| TTS-06 | Existing checkpoint files are versioned — old Chatterbox checkpoints are gracefully invalidated, not silently reused | Current `checkpoint.py` stores `"model": "chatterbox-500m"` in config; add engine version field, detect mismatches, auto-archive to backup |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mlx-audio | 0.3.1 | Qwen3-TTS inference on Apple Silicon | Only MLX-native TTS library with Qwen3-TTS support; MIT license |
| mlx | >=0.30.3 | Apple Silicon ML framework | Required by mlx-audio; provides Metal memory management |
| soundfile | >=0.12 | WAV file reading/writing | Standard for audio I/O; works with numpy arrays from mlx |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | (existing) | Array conversion from mx.array | `np.array(audio)` for soundfile compatibility |
| nltk | (existing) | Sentence tokenization for chunking | Already used in `_split_long_text()` |
| noisereduce | >=3.0 | SNR filtering for voice references | Optional — for clip quality assessment |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| mlx-audio | qwen-tts (official) | Official package requires CUDA; mlx-audio is the only Apple Silicon option |
| soundfile | torchaudio | Would keep torch dependency; soundfile is lighter since we're moving away from torch |
| noisereduce | custom SNR calc | Could compute SNR with just numpy+scipy; noisereduce adds a dependency |

**Installation:**
```bash
pip install mlx-audio soundfile
# or with uv:
uv add mlx-audio soundfile
```

**Note:** mlx-audio transitively installs `mlx`. Chatterbox dependencies (`torch`, `torchaudio`, `chatterbox-tts`) remain for fallback.

## Architecture Patterns

### Recommended Project Structure
```
src/synthesis/
├── __init__.py
├── models.py              # SynthesisConfig gains engine_type field
├── engine_base.py         # NEW: Abstract TTSEngine interface
├── chatterbox_engine.py   # RENAMED: Current tts_engine.py
├── qwen_engine.py         # NEW: Qwen3-TTS via mlx-audio
├── engine_factory.py      # NEW: Creates engine from config
├── chunker.py             # NEW: 500-600 char sentence-boundary splitter
├── checkpoint.py          # MODIFIED: Engine version tagging
├── synthesizer.py         # MODIFIED: Uses engine interface
├── progress.py            # UNCHANGED
└── voice_prep.py          # NEW: SNR filter + transcript bundling
```

### Pattern 1: Engine Abstraction
**What:** Abstract base class for TTS engines with factory pattern
**When to use:** When swapping implementations while preserving the synthesis loop
**Example:**
```python
# engine_base.py
from abc import ABC, abstractmethod

class TTSEngineBase(ABC):
    @abstractmethod
    def load_model(self) -> None: ...

    @abstractmethod
    def generate(self, text: str, ref_clip_path: str,
                 ref_transcript: str | None = None,
                 segment_type: str = "narration") -> AudioResult: ...

    @abstractmethod
    def save_wav_atomic(self, audio: "AudioResult", output_path: str) -> bool: ...

    @abstractmethod
    def cleanup_memory(self) -> None: ...

    @abstractmethod
    def unload(self) -> None: ...

    @property
    @abstractmethod
    def sample_rate(self) -> int: ...

    @property
    @abstractmethod
    def engine_name(self) -> str: ...

# engine_factory.py
def create_engine(config: SynthesisConfig) -> TTSEngineBase:
    if config.engine_type == "qwen3":
        from src.synthesis.qwen_engine import QwenTTSEngine
        return QwenTTSEngine(config)
    else:
        from src.synthesis.chatterbox_engine import ChatterboxEngine
        return ChatterboxEngine(config)
```

### Pattern 2: Auto-Fallback with Logging
**What:** Segment-level fallback from Qwen3-TTS to Chatterbox on failure
**When to use:** Per user decision — automatic fallback, never abort
**Example:**
```python
class FallbackEngine(TTSEngineBase):
    def __init__(self, primary: TTSEngineBase, fallback: TTSEngineBase):
        self.primary = primary
        self.fallback = fallback
        self.fallback_events: list[dict] = []

    def generate(self, text, ref_clip_path, **kwargs):
        try:
            return self.primary.generate(text, ref_clip_path, **kwargs)
        except Exception as e:
            self.fallback_events.append({"segment": text[:50], "error": str(e)})
            logger.warning("Qwen3 failed, falling back to Chatterbox: %s", e)
            return self.fallback.generate(text, ref_clip_path, **kwargs)
```

### Pattern 3: MLX Memory Management
**What:** Periodic Metal cache clearing to bound memory across 3000+ segments
**When to use:** Every N segments during synthesis loop
**Example:**
```python
import mlx.core as mx

def cleanup_memory(self) -> None:
    mx.metal.clear_cache()
    active = mx.metal.get_active_memory() / (1024**2)
    peak = mx.metal.get_peak_memory() / (1024**2)
    logger.debug("MLX memory: active=%.1fMB peak=%.1fMB", active, peak)
```

### Anti-Patterns to Avoid
- **Loading both engines simultaneously:** Memory budget is tight on 16GB. Load Qwen3 first; only load Chatterbox on fallback (lazy init)
- **Mixing mx.array and torch.Tensor:** Convert at engine boundary — synthesizer should receive a uniform type (numpy or bytes)
- **Keeping torch imported when using Qwen3:** torch + mlx together consume significant memory; isolate imports behind engine boundary
- **Using streaming mode for file output:** Streaming adds complexity; use non-streaming `model.generate()` for batch file generation

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Sentence splitting | Custom regex tokenizer | NLTK `sent_tokenize()` | Already in codebase; handles abbreviations, decimals, quotes |
| Audio file I/O | Manual WAV header writing | `soundfile.write()` | Handles format, bit depth, endianness correctly |
| SNR estimation | Custom spectral analysis | `noisereduce` or simple RMS-based SNR | SNR calc has edge cases; even simple RMS ratio suffices for clip ranking |
| Metal memory stats | Manual memory tracking | `mx.core.get_active_memory()` / `get_peak_memory()` | MLX provides accurate Metal-level accounting |
| mx.array to numpy | Manual memory copy | `np.array(mx_array)` | Standard MLX interop; handles dtype conversion |

**Key insight:** The mlx-audio library handles all Qwen3-TTS model loading, tokenization, and inference internally. Our job is integration and orchestration, not reimplementing TTS.

## Common Pitfalls

### Pitfall 1: Memory Accumulation Over 3000+ Segments
**What goes wrong:** MLX Metal cache grows unbounded if not cleared, eventually causing system swap and slowdown
**Why it happens:** Each `model.generate()` call allocates Metal buffers; MLX caches them for reuse but cache can grow large
**How to avoid:** Call `mx.metal.clear_cache()` every N segments (recommend starting at 50, tune based on monitoring). Use `mx.core.set_cache_limit()` to set hard cap. Monitor with `get_active_memory()`.
**Warning signs:** `get_active_memory()` exceeds 6GB on 16GB machine; system starts using swap

### Pitfall 2: Chatterbox + MLX Memory Collision
**What goes wrong:** Loading both torch (for Chatterbox) and MLX (for Qwen3) simultaneously exhausts unified memory
**Why it happens:** torch MPS and MLX Metal both allocate from the same unified memory pool on Apple Silicon
**How to avoid:** Never load both engines simultaneously. Unload Qwen3 fully before loading Chatterbox for fallback. Consider lazy fallback engine initialization.
**Warning signs:** OOM errors after fallback triggers; system becomes unresponsive

### Pitfall 3: Missing ref_text Degrades Voice Cloning
**What goes wrong:** Calling `model.generate(text, ref_audio=clip)` without `ref_text` falls back to x_vector_only_mode, producing generic-sounding clones
**Why it happens:** Qwen3-TTS Base model needs both the audio reference AND its transcript for high-quality cloning
**How to avoid:** Always pair ref_audio with ref_text. LibriTTS-R includes normalized transcripts — extract and bundle them with clips.
**Warning signs:** Cloned voices sound flat/generic despite good reference audio

### Pitfall 4: Checkpoint Engine Mismatch
**What goes wrong:** Resuming a v1.0 Chatterbox run with Qwen3-TTS produces audio with different characteristics mid-book
**Why it happens:** Old checkpoints don't record which engine was used; new engine silently continues from last segment
**How to avoid:** Tag checkpoints with engine name + version. On mismatch, auto-archive old checkpoint and start fresh (per user decision).
**Warning signs:** Audible timbre shift in the middle of an audiobook

### Pitfall 5: Accent Loss in Streaming Mode
**What goes wrong:** Voice clones lose accents when using streaming generation
**Why it happens:** mlx-audio #439 — stream decode was hardcoded to 25 tokens, truncating voice characteristics
**How to avoid:** Use non-streaming mode for file generation (our use case). If streaming is ever needed, set `streaming_interval=4`.
**Warning signs:** British accent becomes American; distinctive voice features flatten out

### Pitfall 6: Audio Dropout on Newer Apple Silicon
**What goes wrong:** Generated audio has gaps/silence in the middle
**Why it happens:** mlx-audio #464 — M5-specific NAX (Neural Accelerator) issue in older MLX versions
**How to avoid:** Require `mlx>=0.30.3`. Add post-generation duration validation (already exists in current `save_wav_atomic`).
**Warning signs:** Audio plays fine at start/end but has silence in the middle

## Code Examples

### Loading and Using Qwen3-TTS for Voice Cloning
```python
# Source: mlx-audio README + Qwen3-TTS README
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

model = load_model("mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")

results = list(model.generate(
    text="The morning sun cast long shadows across the cobblestone street.",
    ref_audio="voices/speaker_7335.wav",
    ref_text="She opened the door and stepped into the hallway.",
))

audio = results[0].audio  # mx.array
audio_np = np.array(audio)
sf.write("output.wav", audio_np, model.sample_rate)
```

### MLX Memory Management for Long Runs
```python
# Source: MLX official docs (ml-explore.github.io/mlx)
import mlx.core as mx

# Set cache limit to 4GB (on 16GB machine, leaves room for OS + other)
mx.core.set_cache_limit(4 * 1024 * 1024 * 1024)

# Periodic cleanup in synthesis loop
for i, segment in enumerate(segments):
    audio = engine.generate(segment.text, segment.ref_clip)
    engine.save_wav_atomic(audio, segment.output_path)

    if i % 50 == 0:
        mx.core.clear_cache()
        active_mb = mx.core.get_active_memory() / (1024**2)
        peak_mb = mx.core.get_peak_memory() / (1024**2)
        logger.info("Memory: active=%.0fMB peak=%.0fMB", active_mb, peak_mb)
```

### Extracting Transcripts from LibriTTS-R
```python
# LibriTTS-R file naming: {speaker}_{chapter}_{utterance_start}_{utterance_end}.wav
# Corresponding normalized text: {speaker}_{chapter}_{utterance_start}_{utterance_end}.normalized.txt
from pathlib import Path

def get_transcript_for_clip(clip_path: Path) -> str | None:
    """Find the normalized transcript for a LibriTTS-R WAV clip."""
    txt_path = clip_path.with_suffix(".normalized.txt")
    if txt_path.exists():
        return txt_path.read_text().strip()
    return None
```

### Checkpoint Versioning
```python
def create_checkpoint(book_slug, total_segments, config, engine_name, engine_version):
    return {
        "book_slug": book_slug,
        "started_at": now,
        "total_segments": total_segments,
        "engine": {
            "name": engine_name,      # "qwen3-tts" or "chatterbox"
            "version": engine_version, # "1.7B-Base-bf16" or "500m"
            "library": "mlx-audio",    # or "chatterbox-tts"
            "library_version": "0.3.1",
        },
        "config": { ... },
        "completed": {},
        "failed": {},
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chatterbox TTS (500M, PyTorch MPS) | Qwen3-TTS 1.7B (MLX native) | Jan 2026 | Better WER (1.24 vs ~3.5), native Apple Silicon, larger input chunks |
| Max 280 char chunks | 500-600 char chunks (up to 2000 words) | Phase 7 | Fewer segment boundaries, more natural speech flow |
| No transcript for voice cloning | ref_audio + ref_text paired | Phase 7 | Significantly better voice cloning accuracy |
| PyTorch MPS with CPU fallback | MLX Metal native | Phase 7 | No CPU fallback needed; direct Metal acceleration |
| `torch.mps.empty_cache()` | `mx.core.clear_cache()` + `set_cache_limit()` | Phase 7 | Proper Metal memory management instead of PyTorch shim |

**Deprecated/outdated:**
- Chatterbox TTS: Still functional but lower quality; kept as fallback only
- PyTorch MPS pipeline: Replaced by MLX for TTS; torch remains only for Chatterbox fallback
- 280-char chunk limit: Was Chatterbox-specific; Qwen3-TTS handles much longer text

## Open Questions

1. **Exact sample rate of Qwen3-TTS output**
   - What we know: Model name includes "12Hz" referring to token rate, not audio sample rate. Output is `mx.array` at `model.sample_rate`.
   - What's unclear: Exact audio sample rate (likely 24kHz like LibriTTS-R, but unverified)
   - Recommendation: Validate in spike — print `model.sample_rate` after loading. If different from 24kHz, may need resampling for assembly.

2. **Memory footprint of 1.7B bf16 model on 16GB unified memory**
   - What we know: Batch 6-bit uses ~3.88GB base. bf16 1.7B will be larger.
   - What's unclear: Exact peak memory during generation with 500-char chunks
   - Recommendation: Spike should measure. If too large, fall back to `Qwen3-TTS-12Hz-0.6B-Base-bf16` or use 8-bit quantized variant.

3. **Whether `model.generate()` blocks or needs explicit `mx.eval()`**
   - What we know: MLX uses lazy evaluation by default
   - What's unclear: Whether mlx-audio's generate internally calls eval, or if we need to force evaluation before saving
   - Recommendation: Validate in spike. If lazy, wrap with `mx.eval()` before numpy conversion.

4. **SNR filtering approach for voice clips**
   - What we know: User wants 10-15s SNR-filtered clips. LibriTTS-R is already clean studio audio.
   - What's unclear: Whether SNR filtering is needed at all for LibriTTS-R (it's already studio quality), or just duration filtering
   - Recommendation: Start with duration-based selection (10-15s target). Add SNR scoring only if quality issues arise. Claude's discretion per context.

## Sources

### Primary (HIGH confidence)
- [mlx-audio GitHub](https://github.com/Blaizzy/mlx-audio) — API, model list, usage patterns
- [mlx-audio Qwen3-TTS README](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md) — Voice cloning API, parameters, model variants
- [MLX Metal docs](https://ml-explore.github.io/mlx/build/html/python/metal.html) — Memory management functions
- [Qwen3-TTS GitHub](https://github.com/QwenLM/Qwen3-TTS) — Official model specs, architecture, capabilities

### Secondary (MEDIUM confidence)
- [mlx-audio PyPI](https://pypi.org/project/mlx-audio/) — Version 0.3.1, Jan 29 2026, Python >=3.10
- [myByways blog](https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos) — Real-world mlx-audio + Qwen3-TTS usage on macOS, ~1000 chars/min on M2
- [Issue #464](https://github.com/Blaizzy/mlx-audio/issues/464) — Audio dropout bug (CLOSED, M5-specific, fixed via MLX update)
- [Issue #439](https://github.com/Blaizzy/mlx-audio/issues/439) — Accent loss bug (CLOSED, fixed via PR #461)

### Tertiary (LOW confidence)
- Performance numbers (~1000 chars/min) from single blog post on M2 — needs validation on target hardware
- Memory footprint estimates extrapolated from batch benchmarks — actual single-generation footprint unverified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — mlx-audio is the only viable Apple Silicon option for Qwen3-TTS; API verified from multiple sources
- Architecture: MEDIUM — engine abstraction pattern is well-established but mlx-audio-specific integration patterns are thin on real-world examples
- Pitfalls: MEDIUM — bug reports are verified (closed issues), but memory behavior under 3000+ segment load is unvalidated
- Voice cloning API: HIGH — ref_audio + ref_text pattern confirmed across README, blog, and issue tracker

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (mlx-audio is fast-moving; check for new releases monthly)
