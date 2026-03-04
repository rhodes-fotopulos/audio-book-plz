# Phase 4: TTS Synthesis with Checkpoint/Resume - Research

**Researched:** 2026-03-03
**Domain:** Chatterbox TTS voice cloning on Apple Silicon MPS with crash recovery
**Confidence:** MEDIUM — Chatterbox API is stable but Apple Silicon MPS support has known issues requiring workarounds

## Summary

Chatterbox TTS (v0.1.6, December 2025) by Resemble AI is the 500M-parameter English model chosen for this project. It provides zero-shot voice cloning from a reference WAV clip and tuneable expressiveness via `exaggeration` and `cfg_weight` parameters. The model loads ~1GB of weights and runs inference through a diffusion-based pipeline.

Apple Silicon MPS support is functional but requires careful handling: models must be loaded to CPU first then selectively moved to MPS, `PYTORCH_ENABLE_MPS_FALLBACK=1` must be set for unsupported ops (FFT), and there is a known memory leak (~363MB per 5 generations on MPS) that requires periodic `gc.collect()` + `torch.mps.empty_cache()` to mitigate. The Turbo model variant must NOT be used — it triggers a Float64 error on MPS that has no workaround.

The synthesis pipeline processes segments sequentially per chapter, writing each WAV atomically (`.tmp` then rename). A JSON checkpoint file tracks completion state so interrupted runs resume from the last unfinished segment. Chatterbox's 250-character practical chunk limit aligns with the existing 280-char segment cap from Phase 1, so most segments need no further splitting.

**Primary recommendation:** Use the standard Chatterbox 500M model with CPU-first loading, MPS acceleration via environment variable fallback, aggressive memory cleanup every N segments, and atomic WAV writes with JSON checkpoint tracking.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Progress display
- Default: chapter-level progress bar ("Chapter 3/24 — segment 47/312")
- Verbose mode (-v): adds per-segment detail (character name, duration, time taken) as scrolling log
- Show ETA based on rolling average time per segment, updating as it goes
- On completion: Rich stats table — chapters completed, total segments, total audio duration, failures, wall-clock time
- Always write a synthesis.log file alongside WAVs for morning-after debugging

#### Voice tuning parameters
- Exaggeration: Claude's discretion for sensible audiobook default
- Per-character overrides supported in voice_map.json, with global defaults as fallback
- CFG/guidance weight: lean natural — prioritize natural-sounding speech over precise text adherence
- Different defaults for narration vs dialogue: lower exaggeration for narration, higher for dialogue, automatic based on segment type

#### Failure behavior
- Segment failure: retry 2-3 times, then skip. Collect failures for a retry pass at end of run
- Hard crash (GPU OOM, MPS error): auto-restart Chatterbox once and resume from last checkpoint. If second crash, exit cleanly with checkpoint saved
- Partial/corrupted WAVs: delete and re-queue for synthesis (minimum duration check)
- Failure threshold: configurable — stop the entire run if failure rate exceeds threshold (prevents burning hours on a broken run)

#### Run modes
- Single-chapter mode: `synthesize --chapter 3` to process just one chapter (useful for voice testing)
- Dry run mode: `synthesize --dry-run` shows segment count, estimated time, disk space needed
- Re-synthesis: delete the WAV file and re-run — checkpoint detects missing file and regenerates (no special segment-ID flag)
- Ollama auto-unload: automatically detect running Ollama, unload models to free GPU memory before Chatterbox loads

### Claude's Discretion
- Exact Chatterbox exaggeration default value
- CFG/guidance weight default value
- Narration vs dialogue exaggeration split values
- Failure threshold default percentage
- Retry count (2 or 3)
- Checkpoint file format and naming
- WAV file naming convention
- synthesis.log format

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SYNTH-01 | Synthesize audio for each segment using Chatterbox TTS with assigned voice reference | Chatterbox `generate(text, audio_prompt_path=ref.wav)` API; standard 500M model; exaggeration/cfg_weight tuning |
| SYNTH-02 | TTS runs on MPS (Apple Silicon GPU) with CPU fallback for unsupported ops (FFT) | `PYTORCH_ENABLE_MPS_FALLBACK=1` env var; CPU-first model loading; component-wise MPS migration |
| SYNTH-03 | Ollama is explicitly unloaded before TTS model loads to stay within 16GB memory budget | Existing `unload_model()` in `src/attribution/llm_client.py`; verify Ollama process via `ollama list` / API |
| SYNTH-04 | Segments exceeding 280 characters are split at sentence boundaries | Phase 1 already caps at 280 chars; add safety split for edge cases using NLTK sentence tokenizer |
| SYNTH-05 | Checkpoint/resume — completed segments are skipped on restart | JSON checkpoint file tracking segment IDs + WAV paths; WAV existence + minimum duration validation |
| SYNTH-06 | Per-segment WAV files written atomically (write to .tmp, rename) | `torchaudio.save()` to `.tmp` path then `os.rename()` — atomic on same filesystem |
| CLI-03 | User can resume an interrupted synthesis run without re-generating completed segments | Checkpoint file loaded at start; only missing/corrupted WAVs queued for synthesis |
| CLI-04 | Progress reported during synthesis (per-segment/chapter progress) | Rich progress bars (chapter-level default, segment-level verbose); ETA via rolling average |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| chatterbox-tts | 0.1.6 | Voice cloning TTS (500M standard model) | Project decision; only open-source TTS with zero-shot cloning quality rivaling ElevenLabs |
| torch | >=2.0 | PyTorch runtime for model inference | Required by Chatterbox; MPS backend needs 2.0+ |
| torchaudio | (matches torch) | Audio I/O — `torchaudio.save()` for WAV output | Standard PyTorch audio I/O; already in Chatterbox deps |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=13.0 | Progress bars, stats tables, logging | Already in project deps; use for all synthesis UI |
| nltk | >=3.8 | Sentence splitting for oversized segments | Already in project deps; safety net for >280 char segments |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Chatterbox standard 500M | Chatterbox Turbo 350M | Turbo triggers Float64 MPS error — MUST NOT USE on Apple Silicon |
| Chatterbox Multilingual 500M | Chatterbox standard 500M | Multilingual has map_location loading bugs on MPS (#357); English-only is fine for this project |
| torchaudio.save() | soundfile / scipy.io.wavfile | torchaudio already loaded by Chatterbox; no extra dependency |

**Installation:**
```bash
pip install chatterbox-tts
# OR in pyproject.toml:
# "chatterbox-tts>=0.1.6"
```

**Note:** chatterbox-tts pulls in torch, torchaudio, transformers, diffusers, conformer, librosa, resemble-perth (watermarker) as transitive dependencies. On Apple Silicon, install via brew Python 3.11 to get ARM64-native wheels.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── synthesis/               # NEW — Phase 4 module
│   ├── __init__.py
│   ├── models.py           # SynthesisConfig, SegmentResult, Checkpoint, SynthesisStats
│   ├── tts_engine.py       # Chatterbox wrapper: load, generate, cleanup
│   ├── checkpoint.py       # Checkpoint save/load/validate
│   ├── synthesizer.py      # Segment-by-segment synthesis loop
│   └── progress.py         # Rich progress display + synthesis.log
├── pipeline.py             # Add run_synthesize() orchestrator
└── ...existing modules...
```

### Pattern 1: CPU-First Model Loading with MPS Migration
**What:** Load Chatterbox weights to CPU, then selectively move model components to MPS
**When to use:** Always on Apple Silicon — avoids MPS tensor allocation errors at load time
**Example:**
```python
import os
import torch
from chatterbox.tts import ChatterboxTTS

# MUST be set before any torch operations
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

def load_model() -> tuple[ChatterboxTTS, str]:
    """Load Chatterbox with MPS acceleration and CPU fallback."""
    # Always load to CPU first
    model = ChatterboxTTS.from_pretrained("cpu")

    # Detect best device
    if torch.backends.mps.is_available():
        device = "mps"
        # Move components individually (not whole model)
        for attr in ("t3", "s3gen", "ve"):
            if hasattr(model, attr):
                setattr(model, attr, getattr(model, attr).to(device))
        model.device = device
    else:
        device = "cpu"

    return model, device
```
**Source:** Jimmi42/chatterbox-tts-apple-silicon-code adaptation (HuggingFace)

### Pattern 2: Atomic WAV Write with Duration Validation
**What:** Write WAV to `.tmp` file, validate minimum duration, then atomic rename
**When to use:** Every segment write — prevents corrupted WAVs from crashes
**Example:**
```python
import os
import torchaudio as ta

def save_wav_atomic(wav_tensor: torch.Tensor, sample_rate: int,
                    output_path: str, min_duration_s: float = 0.1) -> bool:
    """Save WAV atomically with duration validation."""
    duration = wav_tensor.shape[-1] / sample_rate
    if duration < min_duration_s:
        return False  # Likely corrupted/empty

    tmp_path = output_path + ".tmp"
    ta.save(tmp_path, wav_tensor, sample_rate)
    os.rename(tmp_path, output_path)  # Atomic on same filesystem
    return True
```

### Pattern 3: Memory Cleanup Between Segments
**What:** Periodic garbage collection + MPS cache clear to mitigate memory leak
**When to use:** Every N segments (recommended: every 10-20 segments)
**Example:**
```python
import gc
import torch

def cleanup_memory(device: str) -> None:
    """Aggressive memory cleanup to mitigate Chatterbox memory leak."""
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()
```
**Source:** resemble-ai/chatterbox#218 — memory leak investigation

### Anti-Patterns to Avoid
- **Loading model with `device="mps"` directly:** Causes MPS tensor allocation errors. Always load to CPU first, then migrate components.
- **Using Chatterbox Turbo on Apple Silicon:** Float64 error with no workaround. Standard 500M only.
- **Skipping memory cleanup:** Memory leak accumulates ~70MB per generation. Without periodic cleanup, 300+ segment runs will OOM.
- **Writing WAV directly to final path:** Crash during write produces corrupted file that blocks resume. Always write to `.tmp` then rename.
- **Re-loading model after crash:** If model is already in memory, re-initializing wastes time. Check if model object exists before reloading.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WAV file I/O | Custom wave module writer | `torchaudio.save()` | Already loaded by Chatterbox; handles sample rate, bit depth, format correctly |
| Progress bars | Custom terminal progress | `rich.progress.Progress` | Already in project deps; handles ETA, rate, nested bars |
| Sentence splitting | Regex-based splitter | `nltk.tokenize.sent_tokenize` | Already in project deps; handles abbreviations, edge cases |
| JSON checkpoint | Custom binary format | Standard `json.dump`/`json.load` | Human-readable for debugging; small overhead for metadata-only file |
| Ollama detection | Custom process scanning | `ollama.list()` API call | Already have ollama package in deps; cleaner than `ps aux` parsing |

**Key insight:** Phase 4 is an orchestration challenge, not a TTS challenge. Chatterbox does the hard work — we need reliable segment iteration, crash recovery, and progress reporting around it.

## Common Pitfalls

### Pitfall 1: MPS Float64 Crash with Turbo Model
**What goes wrong:** `Cannot convert a MPS Tensor to float64 dtype as the MPS framework doesn't support float64`
**Why it happens:** Chatterbox Turbo (350M) uses Float64 operations internally; MPS only supports Float32
**How to avoid:** Use standard Chatterbox 500M model exclusively. Never instantiate `ChatterboxTurboTTS` on MPS.
**Warning signs:** Any import of `chatterbox.tts_turbo` in synthesis code

### Pitfall 2: Memory Leak Accumulation
**What goes wrong:** Process RSS grows 60-70MB per `generate()` call, eventually OOMs on 16GB machine
**Why it happens:** Intermediate tensors from diffusion sampling loop retain references (not tracked by PyTorch memory)
**How to avoid:** Call `gc.collect()` + `torch.mps.empty_cache()` every 10-20 segments. Monitor RSS. Consider model reload every 100-200 segments if leak persists.
**Warning signs:** RSS crossing 12GB (model + OS overhead takes ~6-8GB baseline)
**Source:** resemble-ai/chatterbox#218

### Pitfall 3: Corrupted WAV from Interrupted Write
**What goes wrong:** Crash mid-`torchaudio.save()` produces a WAV file with valid header but truncated audio
**Why it happens:** File write is not atomic — header written first, then PCM data
**How to avoid:** Write to `.tmp` path, validate duration, then `os.rename()` (atomic on same FS)
**Warning signs:** WAV files with abnormally small size or duration < 0.1s

### Pitfall 4: Ollama Still Loaded During Synthesis
**What goes wrong:** Chatterbox + Ollama together exceed 16GB RAM, triggering swap thrashing or OOM
**Why it happens:** Ollama keeps models in VRAM until explicitly evicted; Phase 3 might leave a model loaded
**How to avoid:** Before loading Chatterbox: call `unload_model()` from existing `llm_client.py`, then verify with `ollama list` that no models have non-zero VRAM
**Warning signs:** System memory pressure warnings, synthesis much slower than expected

### Pitfall 5: MPS Output Channels > 65536
**What goes wrong:** `NotImplementedError: Output channels > 65536 not supported at the MPS device`
**Why it happens:** PyTorch MPS backend has hardware constraint on conv layer output dimensions
**How to avoid:** Ensure `PYTORCH_ENABLE_MPS_FALLBACK=1` is set; this falls back affected ops to CPU transparently. Users report success with Python 3.11 + macOS 15.5+.
**Warning signs:** Error during model forward pass, not during loading
**Source:** resemble-ai/chatterbox#147

### Pitfall 6: Reference Clip Quality
**What goes wrong:** Generated speech has artifacts, wrong accent, or robotic quality
**Why it happens:** Reference clips shorter than ~5 seconds or with background noise degrade cloning quality
**How to avoid:** LibriTTS-R clips are typically 5-15 seconds of clean studio audio — good quality. The clip_selector from Phase 3 already picks clips in the 8-15 second sweet spot. No additional filtering needed.
**Warning signs:** Consistent quality issues across all segments for one character

## Code Examples

### Complete Segment Synthesis Flow
```python
import os
import gc
import time
import torch
import torchaudio as ta
from chatterbox.tts import ChatterboxTTS

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

# Recommended defaults for audiobook narration
NARRATION_EXAGGERATION = 0.25   # Calm, steady delivery
DIALOGUE_EXAGGERATION = 0.45    # More expressive for character voices
CFG_WEIGHT = 0.3                # Low for natural pacing (lean natural per user decision)

def synthesize_segment(
    model: ChatterboxTTS,
    text: str,
    ref_clip_path: str,
    segment_type: str = "narration",
    exaggeration: float | None = None,
    cfg_weight: float | None = None,
) -> torch.Tensor:
    """Generate audio for a single text segment."""
    if exaggeration is None:
        exaggeration = (DIALOGUE_EXAGGERATION if segment_type == "dialogue"
                       else NARRATION_EXAGGERATION)
    if cfg_weight is None:
        cfg_weight = CFG_WEIGHT

    wav = model.generate(
        text,
        audio_prompt_path=ref_clip_path,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )
    return wav
```

### Checkpoint File Structure
```json
{
  "book_slug": "the-name-of-the-wind",
  "started_at": "2026-03-03T22:00:00Z",
  "updated_at": "2026-03-03T23:45:00Z",
  "total_segments": 2847,
  "completed": {
    "seg_0000": {"wav": "wavs/ch01/seg_0000.wav", "duration_s": 3.2, "took_s": 4.1},
    "seg_0001": {"wav": "wavs/ch01/seg_0001.wav", "duration_s": 2.8, "took_s": 3.7}
  },
  "failed": {
    "seg_0042": {"error": "MPS OOM", "attempts": 3}
  },
  "config": {
    "narration_exaggeration": 0.25,
    "dialogue_exaggeration": 0.45,
    "cfg_weight": 0.3,
    "device": "mps",
    "model": "chatterbox-500m"
  }
}
```

### WAV File Naming Convention
```
output/{book-slug}/wavs/
├── ch01/
│   ├── seg_0000.wav    # Global segment ID, zero-padded
│   ├── seg_0001.wav
│   └── ...
├── ch02/
│   ├── seg_0047.wav
│   └── ...
└── checkpoint.json
```

### Dry Run Estimation
```python
# Average Chatterbox generation: ~1.5x real-time on MPS M4
# So a 3-second audio segment takes ~4.5 seconds to generate
ESTIMATED_RTF = 1.5  # Real-time factor (generation time / audio duration)
AVERAGE_SEGMENT_DURATION_S = 3.0  # Estimated from 280-char limit
WAV_BYTES_PER_SECOND = 48000  # 24kHz * 16bit * 1ch = 48KB/s

def estimate_run(total_segments: int) -> dict:
    """Estimate synthesis time and disk usage for dry run."""
    est_audio_s = total_segments * AVERAGE_SEGMENT_DURATION_S
    est_wall_s = est_audio_s * ESTIMATED_RTF
    est_disk_bytes = est_audio_s * WAV_BYTES_PER_SECOND
    return {
        "segments": total_segments,
        "est_audio_hours": est_audio_s / 3600,
        "est_wall_hours": est_wall_s / 3600,
        "est_disk_gb": est_disk_bytes / (1024**3),
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Chatterbox standard only | Three models: Standard, Turbo, Multilingual | Dec 2025 (v0.1.6) | Turbo is faster but BROKEN on MPS — stick with standard |
| `device="cuda"` only | CPU-first load + device migration | Community fix, late 2025 | Required for Apple Silicon; official fix pending (#410) |
| No memory management | gc.collect() + cache clear needed | Discovered in #218 | Without cleanup, OOM after ~100 segments on 16GB |
| torchaudio pre-2.9 | torchaudio 2.9+ uses TorchCodec | 2025 | `torchaudio.save()` API unchanged; encoding params now ignored |

**Deprecated/outdated:**
- `ChatterboxTTS.from_pretrained(device="mps")`: Direct MPS loading may cause tensor allocation errors on some systems. Use CPU-first pattern instead.

## Open Questions

1. **Exact MPS memory leak rate on M4**
   - What we know: ~363MB per 5 generations on MPS (from #218, tested on M1/M2)
   - What's unclear: Whether M4 with newer macOS has improved MPS memory management
   - Recommendation: Implement cleanup every 10 segments; add RSS monitoring; tune interval based on observed behavior during first run

2. **Chatterbox sample rate**
   - What we know: Chatterbox outputs at `model.sr` (likely 24kHz based on the diffusion architecture)
   - What's unclear: Exact sample rate not explicitly documented
   - Recommendation: Read `model.sr` at runtime; use it for all WAV writes and duration calculations

3. **MPS vs CPU speed on M4 with thermal throttling**
   - What we know: MPS is 2-3x faster than CPU on M-series chips, but fanless MacBooks throttle under sustained load
   - What's unclear: Whether the M4 Mac being used has active cooling
   - Recommendation: Default to MPS; add `--cpu` flag as escape hatch; log per-segment times so user can compare

## Sources

### Primary (HIGH confidence)
- [resemble-ai/chatterbox GitHub](https://github.com/resemble-ai/chatterbox) — Official repo, API, model variants
- [chatterbox-tts PyPI](https://pypi.org/project/chatterbox-tts/) — v0.1.6, Python >=3.10, Dec 2025
- [resemble-ai/chatterbox#218](https://github.com/resemble-ai/chatterbox/issues/218) — Memory leak investigation with repro data
- [resemble-ai/chatterbox#357](https://github.com/resemble-ai/chatterbox/issues/357) — Apple Silicon CUDA mapping fix
- [resemble-ai/chatterbox#147](https://github.com/resemble-ai/chatterbox/issues/147) — Output channels > 65536 MPS error
- [resemble-ai/chatterbox#336](https://github.com/resemble-ai/chatterbox/issues/336) — Apple Silicon dependency installation script

### Secondary (MEDIUM confidence)
- [Jimmi42/chatterbox-tts-apple-silicon-code](https://huggingface.co/Jimmi42/chatterbox-tts-apple-silicon-code) — Community Apple Silicon adaptation with working MPS pattern
- [petermg/Chatterbox-TTS-Extended](https://github.com/petermg/Chatterbox-TTS-Extended) — Audiobook-focused fork with chunking strategy (~300 chars)
- [devnen/Chatterbox-TTS-Server](https://github.com/devnen/Chatterbox-TTS-Server) — Server with batch audiobook processing, voice consistency patterns

### Tertiary (LOW confidence)
- [torchaudio.save() docs](https://docs.pytorch.org/audio/stable/generated/torchaudio.save.html) — WAV save API (2.9+ uses TorchCodec)
- Chatterbox exaggeration/cfg_weight defaults: 0.5/0.5 — from README examples, but audiobook use case likely needs different tuning

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Chatterbox API, torchaudio well-documented
- Architecture: MEDIUM — MPS patterns from community adaptations, not official docs
- Pitfalls: HIGH — All from real GitHub issues with reproduction steps

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (30 days — Chatterbox is actively developed, check for MPS fixes)
