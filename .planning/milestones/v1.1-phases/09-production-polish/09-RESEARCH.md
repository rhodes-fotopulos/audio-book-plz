# Phase 9: Production Polish - Research

**Researched:** 2026-03-04
**Domain:** Audio post-processing, mastering, voice consistency, ACX-compliant export
**Confidence:** HIGH

## Summary

Phase 9 polishes assembled audiobooks into professional-quality output. The core technologies are well-established: Spotify's **pedalboard** (v0.9.22) provides a complete audio effects chain in Python with C++-backed processing, **Resemblyzer** provides 256-dimensional speaker embeddings for voice consistency verification via cosine similarity, and **pydub** (already in the project) handles crossfade operations at segment boundaries. The project already has the audio assembly pipeline (concatenator, normalizer, encoder, tagger) built in Phase 5, and Phase 9 extends it with randomized pauses, effects processing, voice verification, and ACX-grade export.

The main integration points are: (1) replacing fixed silence durations with Gaussian-randomized values in the concatenator, (2) inserting a pedalboard effects chain between concatenation and LUFS normalization, (3) adding a voice consistency pass before assembly that compares speaker embeddings and triggers TTS regeneration for outliers, and (4) upgrading the encoder to output 44.1kHz 192kbps CBR MP3 with crossfaded segment boundaries.

**Primary recommendation:** Use pedalboard for effects chain + Resemblyzer for speaker embeddings + numpy for Gaussian randomization. All are pip-installable, well-documented, and proven in audio/speech pipelines.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Pause timing & rhythm:** Natural narrator feel — pauses should be organic, slightly varied, never metronomic. Paragraph breaks get a small pause (0.3-0.6s range). Chapter breaks are just a longer silence pause — no chimes or audio cues. Scene break and chapter break durations: Claude's discretion based on audiobook conventions.
- **Mastering character:** Transparent/clean processing — should be invisible, just removes problems (noise, peaks) without coloring the sound. Noise gate: aggressive — dead quiet gaps between phrases, studio clean. Compression: moderate — tighten dynamic range for comfortable listening without constant volume adjusting. A/B validation runs automatically, logging before/after metrics (loudness, peak, SNR) and flagging any regressions.
- **Voice consistency handling:** Check every segment — thorough, not periodic sampling. When 3 regeneration attempts all fail threshold: keep the best-scoring attempt but flag it as a warning for optional manual review. Cosine threshold (default 0.60) is configurable via `--voice-threshold` CLI flag for stricter matching when quality matters. Voice consistency results go in a separate report file (not just inline logging).
- **Chapter & file structure:** Generate both per-chapter MP3 files AND a single combined file — user picks what to use. Full ID3 metadata: title, author, chapter name, cover art (if available from EPUB), genre=Audiobook, track numbers. File naming: sequential + title from EPUB (e.g., `01-chapter-one.mp3`, `02-the-journey.mp3`). Output location: configurable via `--output-dir` flag, default alongside the input EPUB.

### Claude's Discretion
- Exact scene break and chapter break pause durations (within natural narrator feel)
- Pedalboard effects chain parameter tuning (gate threshold, compressor ratio, EQ curve)
- Voice consistency report format (JSON vs text)
- Combined file chapter marker implementation
- Crossfade curve shape (linear vs equal-power)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| POL-01 | Pause timing uses Gaussian-randomized durations within context-aware ranges (scene breaks, speaker changes, chapter breaks) | numpy.random.normal() with per-boundary-type mean/std; replace fixed AssemblyConfig silence values |
| POL-02 | Post-processing applies pedalboard effects chain incrementally: trim silence, noise gate, compress, high-pass EQ at 80Hz, limit | pedalboard v0.9.22: NoiseGate + Compressor + HighpassFilter + Limiter; A/B validation via pyloudnorm metrics |
| POL-03 | Final export is 44.1kHz 192kbps CBR MP3 (ACX spec) | pydub export with parameters=["-ar", "44100", "-b:a", "192k", "-ac", "1"]; ACX requires RMS -23 to -18 dB, peak < -3 dB, noise floor < -60 dB |
| POL-04 | Voice consistency pass compares same-speaker segment embeddings and regenerates outliers (max 3 attempts, cosine threshold starting at 0.60) | Resemblyzer VoiceEncoder + embed_utterance; cosine similarity via numpy; integrates with existing TTS regeneration loop |
| POL-05 | Segments use 5-10ms fade-in/fade-out crossfades instead of hard silence insertion | pydub fade_in() and fade_out() on each AudioSegment before concatenation |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pedalboard | >=0.9.19 | Audio effects chain (noise gate, compressor, EQ, limiter) | Spotify's production-grade C++ audio processing with Python bindings; handles real-time effects without FFmpeg subprocess shells |
| Resemblyzer | >=0.1.3 | Speaker embedding extraction (256-dim vectors) | Lightweight voice encoder (GE2E model), ~1000x real-time on CPU, 256-dim embeddings with proven cosine similarity for speaker verification |
| numpy | (already installed) | Gaussian random pause generation, cosine similarity math | Standard numerical computing; numpy.random.normal for Gaussian distributions |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydub | (already installed) | Crossfade operations, segment fade-in/fade-out | Segment boundary smoothing (5-10ms fades) |
| pyloudnorm | (already installed) | LUFS measurement for A/B validation | Before/after effects chain comparison |
| soundfile | (already installed) | WAV I/O for pedalboard processing | Loading segments for effects processing |
| mutagen | (already installed) | ID3 tagging (already wired in Phase 5) | Chapter file naming and metadata updates |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pedalboard | sox/ffmpeg CLI | pedalboard is native Python, no subprocess overhead, better parameter control |
| pedalboard | noisereduce + custom DSP | noisereduce is stationary noise only; pedalboard handles full effects chain in one pass |
| Resemblyzer | SpeechBrain ECAPA-TDNN | SpeechBrain is more accurate but heavier (~500MB model); Resemblyzer is lightweight and sufficient for same-voice consistency checking |
| Resemblyzer | sentence-transformers (already installed) | sentence-transformers embeds text, not audio; Resemblyzer is purpose-built for speaker voice embeddings |

**Installation:**
```bash
pip install "pedalboard>=0.9.19" "Resemblyzer>=0.1.3"
```

## Architecture Patterns

### Recommended Project Structure

Phase 9 adds new modules to existing packages — no new top-level packages needed:

```
src/
├── assembly/
│   ├── concatenator.py     # MODIFY: Gaussian pauses + crossfades (POL-01, POL-05)
│   ├── models.py           # MODIFY: PauseConfig with Gaussian params
│   ├── effects.py          # NEW: pedalboard effects chain (POL-02)
│   ├── encoder.py          # MODIFY: 44.1kHz 192kbps export (POL-03)
│   ├── assembler.py        # MODIFY: wire effects chain + file naming
│   └── ...existing...
├── synthesis/
│   ├── voice_verifier.py   # NEW: speaker embedding consistency (POL-04)
│   └── ...existing...
└── pipeline.py             # MODIFY: wire voice verification, --output-dir, --voice-threshold
```

### Pattern 1: Pedalboard Effects Chain (Per-Chapter Processing)

**What:** Apply effects to each chapter's audio after concatenation, before LUFS normalization.
**When to use:** Every chapter during assembly.

```python
import numpy as np
from pedalboard import Pedalboard, NoiseGate, Compressor, HighpassFilter, Limiter

def create_mastering_chain() -> Pedalboard:
    """Build the production mastering effects chain.

    Order matters: gate first (clean silence), then compress (tighten dynamics),
    then EQ (remove rumble), then limit (prevent clipping).
    """
    return Pedalboard([
        NoiseGate(
            threshold_db=-40.0,     # Aggressive gate per user decision
            ratio=10.0,             # High ratio for "studio clean" gaps
            attack_ms=1.0,          # Fast attack to preserve transients
            release_ms=100.0,       # Moderate release to avoid choppy gating
        ),
        Compressor(
            threshold_db=-20.0,     # Moderate compression per user decision
            ratio=3.0,              # 3:1 ratio — tightens without squashing
            attack_ms=10.0,         # Moderate attack for natural speech
            release_ms=150.0,       # Natural release
        ),
        HighpassFilter(
            cutoff_frequency_hz=80.0,  # Remove rumble below 80Hz per requirements
        ),
        Limiter(
            threshold_db=-3.0,      # ACX peak requirement: no peaks above -3dB
            release_ms=100.0,
        ),
    ])

# Usage: board = create_mastering_chain()
# processed = board(audio_float32, sample_rate)
```

### Pattern 2: A/B Validation with Metrics Logging

**What:** Measure audio quality before and after effects chain, flag regressions.
**When to use:** Every chapter — automatic per user decision.

```python
import pyloudnorm as pyln

def measure_audio_metrics(audio: np.ndarray, sample_rate: int) -> dict:
    """Measure loudness, peak, and estimated noise floor."""
    meter = pyln.Meter(sample_rate)
    lufs = meter.integrated_loudness(audio)
    peak_db = 20 * np.log10(np.max(np.abs(audio)) + 1e-10)
    # Noise floor: measure quietest 10% of windowed RMS
    # (simplified — actual implementation may use more sophisticated approach)
    return {"lufs": lufs, "peak_db": peak_db}
```

### Pattern 3: Gaussian Randomized Pauses

**What:** Replace fixed silence values with Gaussian-sampled durations.
**When to use:** Between every pair of segments during concatenation.

```python
def gaussian_pause_ms(mean_ms: float, std_ms: float, min_ms: float, max_ms: float) -> int:
    """Sample a pause duration from a clipped Gaussian distribution."""
    value = np.random.normal(mean_ms, std_ms)
    return int(np.clip(value, min_ms, max_ms))
```

### Pattern 4: Voice Consistency Verification

**What:** Compare each segment's speaker embedding against a reference embedding for that character.
**When to use:** After synthesis, before assembly.

```python
from resemblyzer import VoiceEncoder, preprocess_wav
from pathlib import Path

encoder = VoiceEncoder("cpu")

def compute_embedding(wav_path: Path) -> np.ndarray:
    wav = preprocess_wav(wav_path)
    return encoder.embed_utterance(wav)

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

### Anti-Patterns to Avoid
- **Processing per-segment instead of per-chapter:** Noise gate and compressor need context; per-segment processing creates inconsistent dynamics. Process full chapters.
- **Running LUFS normalization BEFORE effects chain:** The effects chain changes loudness; normalize AFTER effects, not before.
- **Using scipy.spatial.distance.cosine for similarity:** Returns DISTANCE (1 - similarity), not similarity. Use `np.dot(a, b) / (norm(a) * norm(b))` directly to avoid sign confusion.
- **Applying crossfades to silence gaps:** Crossfades should be on the audio segment edges only, not on the silence padding between segments.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Noise gate | Custom amplitude thresholding | pedalboard.NoiseGate | Proper attack/release envelope, ratio control, avoids choppy artifacts |
| Audio compression | Manual gain curves | pedalboard.Compressor | Handles knee, attack/release timing, makeup gain correctly |
| Speaker embeddings | Custom audio fingerprinting | Resemblyzer VoiceEncoder | GE2E-trained model produces reliable voice identity vectors; custom solutions would need training data |
| Gaussian sampling | Manual random with clipping | numpy.random.normal + np.clip | Numerically stable, reproducible with seeds |
| MP3 encoding | Raw LAME calls | pydub.export(format="mp3") | pydub wraps ffmpeg correctly, handles headers and padding |

**Key insight:** Audio DSP is full of subtle timing and envelope issues. pedalboard handles all the sample-accurate processing in C++ — custom Python implementations would introduce artifacts (gate clicks, compressor pumping, filter ringing).

## Common Pitfalls

### Pitfall 1: Pedalboard Expects Float32 [-1.0, 1.0]
**What goes wrong:** Passing int16 audio to pedalboard produces silence or garbage.
**Why it happens:** pedalboard processes float32 numpy arrays in [-1.0, 1.0] range.
**How to avoid:** Convert from pydub AudioSegment to float32 before processing, convert back after. The project already has this pattern in `normalizer.py`.
**Warning signs:** Processed audio is silent or clipped to all-ones.

### Pitfall 2: Sample Rate Mismatch in Effects Chain
**What goes wrong:** Effects chain produces distorted audio.
**Why it happens:** The project uses 24kHz from TTS engines, but ACX requires 44.1kHz. Pedalboard effects need the correct sample rate passed in.
**How to avoid:** Either (a) resample to 44.1kHz before effects chain, or (b) run effects at native rate then resample during export. Option (b) is simpler — let pydub/ffmpeg handle the final resample during MP3 export with `-ar 44100`.
**Warning signs:** Pitch-shifted or aliased audio output.

### Pitfall 3: Resemblyzer Preprocessing Requirements
**What goes wrong:** Embeddings are unreliable, cosine similarities are random.
**Why it happens:** Resemblyzer expects 16kHz mono audio via `preprocess_wav()`. Skipping preprocessing on 24kHz WAVs produces wrong embeddings.
**How to avoid:** Always call `preprocess_wav()` on WAV paths before `embed_utterance()`. The function handles resampling and normalization internally.
**Warning signs:** Same-speaker segments showing widely varying cosine similarities.

### Pitfall 4: Voice Consistency Running After Assembly
**What goes wrong:** Regenerated segments don't get included in final output.
**Why it happens:** If voice consistency runs after assembly, you'd need to re-assemble.
**How to avoid:** Run voice consistency pass AFTER synthesis but BEFORE assembly. This fits naturally in the pipeline: synthesize -> verify -> assemble.
**Warning signs:** Regenerated WAVs exist but audiobook still contains old versions.

### Pitfall 5: ACX Peak Requirement vs LUFS Normalization
**What goes wrong:** Audio passes LUFS check but fails ACX peak check (-3dB).
**Why it happens:** LUFS normalization adjusts average loudness but doesn't limit peaks.
**How to avoid:** The Limiter in the effects chain handles this (threshold_db=-3.0). Run limiter AFTER compressor, and normalize LUFS AFTER effects chain.
**Warning signs:** Peak values above -3dB in exported MP3.

### Pitfall 6: Crossfade Duration vs Segment Length
**What goes wrong:** Very short segments (< 50ms) fail with crossfade applied.
**Why it happens:** pydub fade_in/fade_out duration can't exceed segment length.
**How to avoid:** Guard: `fade_ms = min(fade_ms, len(segment) // 2)`. For 5-10ms fades this is unlikely to be an issue (would need sub-20ms segments), but defensive code prevents crashes.
**Warning signs:** pydub raises ValueError on fade duration.

## Code Examples

### Full Effects Chain with A/B Validation

```python
import numpy as np
import pyloudnorm as pyln
from pedalboard import Pedalboard, NoiseGate, Compressor, HighpassFilter, Limiter
from pydub import AudioSegment

def apply_effects_chain(
    chapter_audio: AudioSegment,
    board: Pedalboard,
) -> tuple[AudioSegment, dict]:
    """Apply mastering effects chain with before/after metrics.

    Args:
        chapter_audio: Raw chapter audio from concatenation.
        board: Pre-built pedalboard effects chain.

    Returns:
        Tuple of (processed AudioSegment, metrics dict with before/after).
    """
    sample_rate = chapter_audio.frame_rate

    # Convert to float32
    samples = np.array(chapter_audio.get_array_of_samples(), dtype=np.float32)
    max_val = float(2 ** (chapter_audio.sample_width * 8 - 1))
    audio_f32 = samples / max_val

    # Measure before
    meter = pyln.Meter(sample_rate)
    before_lufs = meter.integrated_loudness(audio_f32)
    before_peak = float(20 * np.log10(np.max(np.abs(audio_f32)) + 1e-10))

    # Apply effects
    processed = board(audio_f32, sample_rate)

    # Measure after
    after_lufs = meter.integrated_loudness(processed)
    after_peak = float(20 * np.log10(np.max(np.abs(processed)) + 1e-10))

    # Convert back to int16
    processed_clipped = np.clip(processed, -1.0, 1.0)
    processed_int = (processed_clipped * (2**15 - 1)).astype(np.int16)

    result = chapter_audio._spawn(processed_int.tobytes())

    metrics = {
        "before_lufs": before_lufs,
        "after_lufs": after_lufs,
        "before_peak_db": before_peak,
        "after_peak_db": after_peak,
    }

    return result, metrics
```

### Voice Consistency Check

```python
from resemblyzer import VoiceEncoder, preprocess_wav
from pathlib import Path

def build_reference_embeddings(
    voice_map: dict,
    encoder: VoiceEncoder,
) -> dict[str, np.ndarray]:
    """Build reference embedding for each character from their voice clip."""
    refs = {}
    for name, info in voice_map.items():
        clip_path = Path(info["clip_path"])
        if clip_path.exists():
            wav = preprocess_wav(clip_path)
            refs[name] = encoder.embed_utterance(wav)
    return refs

def check_segment_consistency(
    wav_path: Path,
    ref_embedding: np.ndarray,
    encoder: VoiceEncoder,
    threshold: float = 0.60,
) -> tuple[float, bool]:
    """Check if a segment matches its character's reference voice."""
    wav = preprocess_wav(wav_path)
    seg_embedding = encoder.embed_utterance(wav)

    similarity = float(
        np.dot(ref_embedding, seg_embedding)
        / (np.linalg.norm(ref_embedding) * np.linalg.norm(seg_embedding))
    )

    return similarity, similarity >= threshold
```

### Gaussian Pause Configuration

```python
from dataclasses import dataclass

@dataclass
class PauseConfig:
    """Gaussian-randomized pause timing for natural narrator feel."""

    # Paragraph break: 0.3-0.6s per user decision
    paragraph_mean_ms: float = 450.0
    paragraph_std_ms: float = 75.0
    paragraph_min_ms: float = 300.0
    paragraph_max_ms: float = 600.0

    # Scene break: longer than paragraph (Claude's discretion)
    scene_break_mean_ms: float = 2200.0
    scene_break_std_ms: float = 300.0
    scene_break_min_ms: float = 1800.0
    scene_break_max_ms: float = 3000.0

    # Chapter break: longest (Claude's discretion)
    chapter_mean_ms: float = 3500.0
    chapter_std_ms: float = 400.0
    chapter_min_ms: float = 2800.0
    chapter_max_ms: float = 4500.0

    # Speaker change: slightly longer than paragraph
    speaker_change_mean_ms: float = 600.0
    speaker_change_std_ms: float = 100.0
    speaker_change_min_ms: float = 400.0
    speaker_change_max_ms: float = 900.0

    # Sentence break (within paragraph)
    sentence_mean_ms: float = 350.0
    sentence_std_ms: float = 50.0
    sentence_min_ms: float = 250.0
    sentence_max_ms: float = 500.0
```

## State of the Art

| Old Approach (v1.0/Phase 5) | Current Approach (Phase 9) | What Changed | Impact |
|------------------------------|----------------------------|--------------|--------|
| Fixed silence values (900ms paragraph, 2500ms scene) | Gaussian-randomized durations per boundary type | Organic timing instead of metronomic | Natural narrator rhythm |
| No effects processing | pedalboard chain (gate, compress, EQ, limit) | Professional mastering in pipeline | Studio-clean output |
| 64kbps MP3, native sample rate | 44.1kHz 192kbps CBR MP3 | ACX-compliant export | Audible/ACX submission ready |
| No voice consistency checking | Resemblyzer embeddings + cosine similarity | Detect and fix voice drift | Consistent character voices |
| Hard silence insertion at boundaries | 5-10ms fade-in/fade-out crossfades | Smooth transitions | No audible clicks |
| Single audiobook.mp3 output | Per-chapter + combined with descriptive naming | User choice of format | Better file management |

**Deprecated/outdated:**
- The Phase 5 `AssemblyConfig` fixed silence values will be replaced by `PauseConfig` Gaussian parameters
- The Phase 5 64kbps bitrate will be upgraded to 192kbps for ACX compliance

## Open Questions

1. **Pedalboard at 24kHz vs 44.1kHz**
   - What we know: TTS engines output at 24kHz. Pedalboard effects work at any sample rate.
   - What's unclear: Whether to resample before or after effects chain.
   - Recommendation: Run effects at native 24kHz, let pydub/ffmpeg resample during MP3 export (`-ar 44100`). Simpler, and effects parameters are designed for the native rate.

2. **Resemblyzer on Very Short Segments**
   - What we know: Resemblyzer works reliably with 2.6+ seconds of audio. Some segments may be shorter.
   - What's unclear: Embedding quality for sub-2s segments.
   - Recommendation: Skip voice consistency check for segments shorter than 2 seconds. These are too short to reliably compare and unlikely to exhibit voice drift.

3. **Voice Consistency Memory Impact**
   - What we know: Resemblyzer's voice encoder is ~17MB. The project already loads sentence-transformers (~80MB) for matching.
   - What's unclear: Whether loading both simultaneously causes memory pressure on 16GB machines.
   - Recommendation: Voice consistency runs BEFORE assembly. Resemblyzer loads, runs, unloads. No overlap with TTS engine (which has already unloaded).

## Sources

### Primary (HIGH confidence)
- pedalboard v0.9.22 official documentation — effects API, parameters, examples
- Resemblyzer GitHub repository — VoiceEncoder API, embed_utterance, preprocess_wav
- ACX official audio submission requirements — 192kbps CBR MP3, 44.1kHz, peak < -3dB, RMS -23 to -18 dB
- pydub documentation — fade_in, fade_out, append with crossfade

### Secondary (MEDIUM confidence)
- pedalboard GitHub issue #279 — TTS audio quality improvement parameters (NoiseGate -30dB, Compressor, HighpassFilter 80Hz, Limiter -0.1dB)
- 2025 academic study on Resemblyzer for voice authentication — confirms reliable above 2.63s audio duration

### Tertiary (LOW confidence)
- Pedalboard parameter tuning for speech (gate threshold, compressor ratio) — empirical, will need A/B validation per user decision

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pedalboard, Resemblyzer, and numpy are well-documented with stable APIs
- Architecture: HIGH — integration points are clear; existing Phase 5 code provides natural insertion points
- Pitfalls: HIGH — pitfalls are well-known in audio processing; pedalboard float32 requirement, Resemblyzer preprocessing, sample rate handling all documented
- Parameter tuning: MEDIUM — noise gate threshold, compressor ratio values are starting points that need empirical A/B validation

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain — audio processing libraries change slowly)
