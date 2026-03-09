# Phase 15: Opinionated Profiles and Expressive Clips - Research

**Researched:** 2026-03-09
**Domain:** LLM prompt engineering for voice profile extraction, audio signal analysis for clip scoring
**Confidence:** HIGH

## Summary

Phase 15 has two distinct workstreams: (1) making voice profiles more distinctive and user-controllable (PROF-01/02/03), and (2) replacing duration-only clip selection with expressiveness-aware scoring (CLIP-01/02). The profile work is primarily LLM prompt engineering and a new distinctiveness pass -- both patterns already exist in the codebase. The clip work requires audio signal analysis (SNR, pitch variance, energy variance, speaking rate estimation) using numpy and soundfile, which are already installed dependencies.

The codebase is well-structured for these changes. The extraction prompt (EXTRACTION_SYSTEM_PROMPT in extractor.py) is a single string constant that can be conditionally modified. The clip selector (clip_selector.py) has a clean single-function interface (`select_reference_clip`) that scores by duration only -- this needs rework to add the expressiveness composite. The voice_overrides.yaml feature is net-new but follows established patterns (YAML loading, Pydantic validation, pipeline integration via book_dir).

**Primary recommendation:** Split into two plans: Plan 01 covers PROF-01/02/03 (opinionated extraction, distinctiveness pass, voice overrides), Plan 02 covers CLIP-01/02 (expressiveness scoring, rate matching). Both are independent workstreams that touch different files.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
None -- all decisions delegated to Claude.

### Claude's Discretion
**Opinionated extraction (PROF-01):**
- How --opinionated modifies EXTRACTION_SYSTEM_PROMPT (separate prompt variant vs appended instructions)
- What vocabulary constraints to enforce (ban "moderate", "medium", "average", "unknown" where evidence exists)
- How extreme to push descriptors while keeping them grounded in literary context

**Distinctiveness pass (PROF-02):**
- Whether to use LLM-based review (send all profiles, ask to push apart) or rule-based field comparison
- Prior context: user prefers LLM approaches over heuristics (Phase 14 decision)
- Single pass vs iterative refinement
- What similarity threshold triggers intervention

**Voice overrides (PROF-03):**
- Scope of voice_overrides.yaml (voice_profile fields, speaker_id, or both)
- YAML schema design
- Validation and error handling for invalid overrides
- Where in the pipeline overrides are applied (must be last per success criteria)

**Clip scoring (CLIP-01, CLIP-02):**
- Whether the defined weights (0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match) are hardcoded or configurable
- How to compute pitch/energy variance from WAV files (librosa, parselmouth, or simpler approach)
- Fallback behavior when a speaker has few clips or no clips with good expressiveness scores
- How rate_match maps character pace profile to speaker talking speed

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROF-01 | --opinionated flag modifies extraction prompt to push for extreme distinctive descriptions, never use "moderate"/"medium" | Append opinionated instructions to EXTRACTION_SYSTEM_PROMPT; ban list of bland vocabulary; thread --opinionated through CLI/pipeline |
| PROF-02 | Post-extraction distinctiveness pass -- review all profiles together and push similar-sounding characters apart | LLM-based pass using call_llm_structured with new Pydantic response model; send all profiles, get back modified ones; cache with key "distinctiveness_v1" |
| PROF-03 | voice_overrides.yaml -- user can manually set voice profile fields per character, applied last in pipeline | PyYAML (already installed) to load YAML from book_dir; Pydantic validation; apply after extraction+merge+distinctiveness |
| CLIP-01 | Score clips by expressiveness composite (0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match) not just duration | numpy+soundfile for audio analysis; SNR via RMS signal/noise estimation; pitch variance via autocorrelation F0; energy variance via frame-level RMS |
| CLIP-02 | Rate-match reference clips to character profile -- fast-paced character gets a fast-talking speaker's clip | Map VoiceProfile.pace/pace_style to target syllable rate; estimate speaking rate from audio via energy-based syllable detection |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy | 2.4.2 (installed) | Audio signal analysis for clip scoring | Already a dependency; sufficient for SNR, pitch, energy variance |
| soundfile | 0.13.1 (installed) | Read WAV files as numpy arrays | Already a dependency; used by clip_selector.py's callers |
| pyyaml | installed | Load voice_overrides.yaml | Already installed in project environment |
| pydantic | 2.0+ (installed) | Validation models for overrides and distinctiveness response | Project standard for all data models |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ollama (via llm_client) | 0.6+ | LLM calls for distinctiveness pass | Reuse existing call_llm_structured infrastructure |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| numpy autocorrelation for F0 | librosa.pyin or parselmouth | More accurate pitch tracking, but adds heavy dependency; numpy autocorrelation is sufficient for relative variance comparison |
| numpy energy-based syllable detection | my-voice-analysis or myprosody | More accurate syllable counting, but adds unmaintained dependencies; energy envelope + zero-crossing is sufficient for rate estimation |

**Installation:**
No new dependencies needed. All required libraries (numpy, soundfile, pyyaml, pydantic) are already installed.

## Architecture Patterns

### Recommended Project Structure
```
src/
├── attribution/
│   ├── extractor.py          # Modified: --opinionated prompt variant (PROF-01)
│   ├── distinctiveness.py    # NEW: LLM-based distinctiveness pass (PROF-02)
│   └── models.py             # Modified: add DistinctivenessResult model
├── matching/
│   ├── clip_selector.py      # Modified: expressiveness scoring (CLIP-01, CLIP-02)
│   └── audio_analyzer.py     # NEW: SNR, pitch variance, energy variance, rate estimation
├── pipeline.py               # Modified: --opinionated flag, distinctiveness pass, voice_overrides loading
├── cli.py                    # Modified: --opinionated CLI flag
└── voice_overrides.py        # NEW: YAML loading + validation (PROF-03)
```

### Pattern 1: Opinionated Prompt Variant (PROF-01)
**What:** Append opinionated instructions to EXTRACTION_SYSTEM_PROMPT when --opinionated flag is set
**When to use:** When the user wants polarized, distinctive voice profiles
**Example:**
```python
# In extractor.py
OPINIONATED_ADDENDUM = """\

OPINIONATED MODE — Push for distinctiveness:
- NEVER use these bland descriptors: "moderate", "medium", "average", "normal", "standard", "typical", "ordinary", "neutral" (for voice traits — "neutral" is OK for accent)
- For pace: choose "fast", "slow", "rapid", "deliberate", "languid", "clipped" — NEVER "moderate"
- For pitch: choose "high" or "low" — NEVER "medium" unless truly average
- For energy: choose "restrained", "intense", "animated", "subdued" — NEVER "moderate"
- Push every trait to its distinctive extreme based on textual evidence
- When evidence is weak, make a bold literary inference rather than defaulting to bland middle-ground
- "unknown" is acceptable ONLY for accent when no accent evidence exists
- The description field should be vivid and specific, not generic"""

def get_extraction_prompt(opinionated: bool = False) -> str:
    if opinionated:
        return EXTRACTION_SYSTEM_PROMPT + OPINIONATED_ADDENDUM
    return EXTRACTION_SYSTEM_PROMPT
```

### Pattern 2: LLM Distinctiveness Pass (PROF-02)
**What:** Send all profiles to LLM, ask it to review and push similar profiles apart
**When to use:** After extraction + merge, before voice matching
**Example:**
```python
# In distinctiveness.py
DISTINCTIVENESS_PROMPT = """\
You are a voice casting director reviewing character voice profiles for an audiobook.
Your job: ensure every character sounds DISTINCTLY different from every other character.

Review the profiles below. For any pair that sound too similar, modify one or both to
create audible separation. Push traits to opposite extremes where possible.

Rules:
- Every character must be distinguishable by at least 2 voice traits
- If two characters share pitch+pace+tone, change at least one trait for one character
- Preserve traits that are strongly supported by literary evidence
- Push apart the character with LESS textual evidence (more flexibility)
- Return ALL profiles, even unmodified ones"""

# Response model
class DistinctivenessResult(BaseModel):
    characters: list[CharacterProfile]
    modifications: list[str]  # Human-readable list of what changed
```

### Pattern 3: Voice Overrides YAML (PROF-03)
**What:** Load voice_overrides.yaml from book_dir, apply as final step
**When to use:** User wants to manually set voice profile fields
**Example YAML schema:**
```yaml
# voice_overrides.yaml
characters:
  "Elizabeth Bennet":
    voice_profile:
      pitch: "high"
      pace: "fast"
      tone: "bright"
      description: "A quick, bright voice with barely contained wit"
  "Mr. Darcy":
    voice_profile:
      pitch: "low"
      tone: "reserved"
    speaker_id: "7335"  # Force specific LibriTTS speaker
```

### Pattern 4: Audio Analysis for Clip Scoring (CLIP-01)
**What:** Compute expressiveness metrics from WAV files using numpy+soundfile
**When to use:** Scoring reference clips for voice cloning quality
**Example:**
```python
# In audio_analyzer.py
import numpy as np
import soundfile as sf

def analyze_clip(wav_path: Path) -> dict:
    """Compute expressiveness metrics for a WAV clip."""
    data, sr = sf.read(wav_path)
    if data.ndim > 1:
        data = data.mean(axis=1)  # mono

    return {
        "snr_db": _compute_snr(data),
        "pitch_variance": _compute_pitch_variance(data, sr),
        "energy_variance": _compute_energy_variance(data, sr),
        "syllable_rate": _estimate_syllable_rate(data, sr),
        "duration_s": len(data) / sr,
    }

def _compute_snr(data: np.ndarray) -> float:
    """Estimate SNR using signal RMS vs noise floor."""
    # Sort amplitude, bottom 10% is noise estimate
    sorted_abs = np.sort(np.abs(data))
    noise_floor = sorted_abs[:len(sorted_abs) // 10]
    signal_rms = np.sqrt(np.mean(data ** 2))
    noise_rms = np.sqrt(np.mean(noise_floor ** 2)) if len(noise_floor) > 0 else 1e-10
    return 20 * np.log10(signal_rms / max(noise_rms, 1e-10))

def _compute_pitch_variance(data: np.ndarray, sr: int) -> float:
    """Estimate F0 variance via autocorrelation on overlapping frames."""
    # Frame-based autocorrelation pitch estimation
    frame_size = int(0.03 * sr)  # 30ms frames
    hop = int(0.01 * sr)  # 10ms hop
    f0s = []
    for start in range(0, len(data) - frame_size, hop):
        frame = data[start:start + frame_size]
        if np.max(np.abs(frame)) < 0.01:  # silence
            continue
        corr = np.correlate(frame, frame, mode='full')
        corr = corr[len(corr)//2:]
        # Find first peak after initial decline
        min_lag = int(sr / 500)  # 500 Hz max
        max_lag = int(sr / 60)   # 60 Hz min
        if max_lag > len(corr):
            continue
        segment = corr[min_lag:max_lag]
        if len(segment) == 0:
            continue
        peak_idx = np.argmax(segment) + min_lag
        if corr[peak_idx] > 0.3 * corr[0]:  # confidence threshold
            f0s.append(sr / peak_idx)
    return float(np.var(f0s)) if len(f0s) > 2 else 0.0

def _compute_energy_variance(data: np.ndarray, sr: int) -> float:
    """Compute variance of frame-level RMS energy."""
    frame_size = int(0.03 * sr)
    hop = int(0.01 * sr)
    energies = []
    for start in range(0, len(data) - frame_size, hop):
        frame = data[start:start + frame_size]
        energies.append(np.sqrt(np.mean(frame ** 2)))
    return float(np.var(energies)) if energies else 0.0

def _estimate_syllable_rate(data: np.ndarray, sr: int) -> float:
    """Estimate syllables per second via energy envelope peak counting."""
    # Compute envelope via RMS in short frames
    frame_size = int(0.02 * sr)  # 20ms
    hop = int(0.01 * sr)
    envelope = []
    for start in range(0, len(data) - frame_size, hop):
        envelope.append(np.sqrt(np.mean(data[start:start+frame_size] ** 2)))
    envelope = np.array(envelope)
    if len(envelope) < 3:
        return 0.0

    # Smooth envelope
    kernel = np.ones(5) / 5
    smoothed = np.convolve(envelope, kernel, mode='same')

    # Count peaks above threshold (syllable nuclei)
    threshold = np.mean(smoothed) * 0.5
    peaks = 0
    above = False
    for val in smoothed:
        if val > threshold and not above:
            peaks += 1
            above = True
        elif val < threshold:
            above = False

    duration = len(data) / sr
    return peaks / duration if duration > 0 else 0.0
```

### Anti-Patterns to Avoid
- **Adding librosa as a dependency:** numpy+soundfile is sufficient for the variance/SNR metrics needed. librosa pulls in numba, llvmlite, and other heavy deps.
- **Iterative distinctiveness refinement:** One LLM pass is enough. Iterating risks oscillation where the LLM keeps flipping traits back and forth.
- **Hardcoding pace-to-rate mapping as exact values:** Use ranges and relative comparison, not absolute syllable-per-second thresholds. LibriTTS speakers vary widely.
- **Modifying EXTRACTION_SYSTEM_PROMPT in place:** Keep the original prompt intact; build opinionated variant by appending. Easier to maintain and test.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom config parser | `yaml.safe_load()` from PyYAML | Edge cases in YAML spec (anchors, multiline strings, etc.) |
| Structured LLM output | Custom JSON parsing + retry | `call_llm_structured()` from llm_client.py | Already handles retries, truncation, validation |
| Cache invalidation | Time-based cache | `get_cache_key(content, "distinctiveness_v1")` from cache.py | Content-hash caching already established; bump version on prompt changes |

**Key insight:** The codebase already has robust patterns for LLM calls, caching, and Pydantic validation. The new features (distinctiveness pass, overrides) should reuse these patterns exactly.

## Common Pitfalls

### Pitfall 1: Cache invalidation when --opinionated changes
**What goes wrong:** User runs without --opinionated, then with --opinionated, gets cached non-opinionated results
**Why it happens:** Cache key is based on chapter content + pass name, not prompt variant
**How to avoid:** Use different cache key prefix: `"extraction_v3"` for normal, `"extraction_v3_opinionated"` for opinionated mode
**Warning signs:** Same characters.json output regardless of --opinionated flag

### Pitfall 2: Distinctiveness pass modifying characters the user overrode
**What goes wrong:** User sets voice_overrides.yaml, but distinctiveness pass has already been cached with different profiles
**Why it happens:** Overrides are applied AFTER distinctiveness, which is correct. But if distinctiveness is cached, re-running with new overrides doesn't invalidate.
**How to avoid:** Apply pipeline order strictly: extraction -> merge -> distinctiveness -> overrides. Overrides are always applied last, never cached. Distinctiveness cache is independent.
**Warning signs:** voice_overrides.yaml changes not reflected in output

### Pitfall 3: SNR estimation on very short clips
**What goes wrong:** Bottom-10% noise estimation fails on clips with only a few hundred samples
**Why it happens:** Very short clips don't have enough silence for noise floor estimation
**How to avoid:** Skip SNR scoring for clips under 2 seconds; use default score of 0.5
**Warning signs:** Negative or extremely high SNR values

### Pitfall 4: Pitch detection on non-speech audio
**What goes wrong:** Autocorrelation finds "pitch" in noise, silence, or music
**Why it happens:** No voice activity detection before pitch estimation
**How to avoid:** Frame energy threshold (skip frames below 0.01 amplitude); require correlation peak confidence > 0.3
**Warning signs:** Pitch variance is extremely high or exactly 0.0

### Pitfall 5: LLM distinctiveness pass returning fewer/more characters than input
**What goes wrong:** LLM drops characters or invents new ones
**Why it happens:** LLM instruction following is imperfect with small models
**How to avoid:** Validate output character count matches input; fall back to original profiles if mismatch. Match returned characters by name, log any unmatched.
**Warning signs:** Character count in characters.json changes after distinctiveness pass

### Pitfall 6: Rate matching with "unknown" pace profiles
**What goes wrong:** Characters with pace="unknown" get random rate-match scores
**Why it happens:** No mapping defined for "unknown" pace
**How to avoid:** Map "unknown" to neutral rate_match score (0.5) so it doesn't penalize or boost
**Warning signs:** Characters with unknown pace consistently get the same speaker

## Code Examples

### Composite Clip Score (CLIP-01)
```python
def score_clip(metrics: dict, target_rate: float | None = None) -> float:
    """Compute expressiveness composite score.

    Weights: 0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match
    All components normalized to 0-1 range before weighting.
    """
    # Normalize SNR: 0-40 dB range mapped to 0-1
    snr_score = min(max(metrics["snr_db"], 0), 40) / 40

    # Normalize pitch variance: higher = more expressive
    # Typical range 0-5000 Hz^2 for speech
    pitch_score = min(metrics["pitch_variance"] / 5000, 1.0)

    # Normalize energy variance: higher = more dynamic
    # Typical range 0-0.01 for normalized audio
    energy_score = min(metrics["energy_variance"] / 0.01, 1.0)

    # Rate match: 1.0 = perfect match, 0.0 = worst mismatch
    if target_rate is not None and metrics["syllable_rate"] > 0:
        rate_diff = abs(metrics["syllable_rate"] - target_rate)
        rate_score = max(0, 1.0 - rate_diff / 5.0)  # 5 syl/s = max diff
    else:
        rate_score = 0.5  # neutral when no target

    return (0.4 * snr_score +
            0.3 * pitch_score +
            0.2 * energy_score +
            0.1 * rate_score)
```

### Pace Profile to Target Rate Mapping (CLIP-02)
```python
# Map VoiceProfile pace/pace_style to target syllable rate
PACE_TO_RATE = {
    "fast": 5.5,
    "rapid": 6.0,
    "clipped": 5.5,
    "moderate": 4.0,
    "measured": 3.5,
    "slow": 2.5,
    "deliberate": 3.0,
    "languid": 2.0,
    "unknown": None,  # No rate matching
}

def get_target_rate(voice_profile: VoiceProfile) -> float | None:
    """Get target syllable rate from character's pace descriptors."""
    # Try pace_style first (more specific), fall back to pace
    rate = PACE_TO_RATE.get(voice_profile.pace_style.lower())
    if rate is None:
        rate = PACE_TO_RATE.get(voice_profile.pace.lower())
    return rate
```

### Voice Overrides Loading (PROF-03)
```python
import yaml
from pathlib import Path
from pydantic import BaseModel

class VoiceOverride(BaseModel):
    voice_profile: dict[str, str] | None = None
    speaker_id: str | None = None

class VoiceOverrides(BaseModel):
    characters: dict[str, VoiceOverride] = {}

def load_voice_overrides(book_dir: Path) -> VoiceOverrides | None:
    """Load voice_overrides.yaml from book directory if it exists."""
    overrides_path = book_dir / "voice_overrides.yaml"
    if not overrides_path.exists():
        return None
    with open(overrides_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        return None
    return VoiceOverrides.model_validate(raw)

def apply_voice_overrides(
    characters: list[CharacterProfile],
    overrides: VoiceOverrides,
) -> list[CharacterProfile]:
    """Apply voice_overrides.yaml to character profiles (final step)."""
    override_map = {name.lower(): ov for name, ov in overrides.characters.items()}
    result = []
    for char in characters:
        key = char.name.lower()
        ov = override_map.get(key)
        if ov is None:
            result.append(char)
            continue
        updates = {}
        if ov.voice_profile:
            vp_dict = char.voice_profile.model_dump()
            vp_dict.update(ov.voice_profile)
            updates["voice_profile"] = VoiceProfile(**vp_dict)
        result.append(char.model_copy(update=updates))
    return result
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Duration-only clip scoring | Expressiveness composite (SNR + pitch + energy + rate) | This phase | Better voice cloning quality |
| Bland "moderate"/"medium" voice profiles | Opinionated extraction with banned vocabulary | This phase | More distinctive character voices |
| No post-extraction profile review | LLM distinctiveness pass | This phase | Characters sound more different |
| No user override mechanism | voice_overrides.yaml | This phase | User control over voice profiles |

## Open Questions

1. **Normalization ranges for expressiveness metrics**
   - What we know: SNR typically 10-40 dB for clean speech; pitch variance and energy variance ranges depend on recording conditions
   - What's unclear: Exact normalization bounds for LibriTTS-R clips specifically
   - Recommendation: Use conservative ranges initially (SNR 0-40, pitch_var 0-5000, energy_var 0-0.01), log actual distributions during first run, tune if needed

2. **Qwen 3.5 9B capability for distinctiveness pass**
   - What we know: User runs Qwen 3.5 9B; it handles extraction and merge arbiter well (Phase 14)
   - What's unclear: Whether sending 10+ full profiles in one prompt overwhelms the context window
   - Recommendation: Limit to profile summaries (name + voice_profile fields only, no full CharacterProfile) to fit in context. If >15 characters, batch into groups and run multiple passes.

3. **Should expressiveness scoring weights be configurable?**
   - What we know: CONTEXT.md lists this as Claude's discretion
   - What's unclear: Whether users will want to tune weights
   - Recommendation: Hardcode the 0.4/0.3/0.2/0.1 weights as constants. Add a comment noting they can be promoted to config if needed. Premature configuration adds complexity.

## Sources

### Primary (HIGH confidence)
- Project source code: extractor.py, models.py, clip_selector.py, llm_client.py, cache.py, pipeline.py, cli.py, orchestrator.py -- direct reading of implementation
- pyproject.toml and pip list -- verified installed dependencies

### Secondary (MEDIUM confidence)
- [WADA SNR Estimation](https://gist.github.com/johnmeade/d8d2c67b87cda95cd253f55c21387e75) -- SNR estimation approach
- [Gary Sieling - Compute SNR in audio files](https://www.garysieling.com/blog/compute-signal-noise-ratio-audio-files-python/) -- SNR computation patterns
- [Basic Sound Processing with Python](https://samcarcagno.altervista.org/blog/basic-sound-processing-python/) -- Autocorrelation pitch estimation
- [pyAudioAnalysis](https://github.com/tyiannak/pyAudioAnalysis) -- Energy-based syllable detection approach
- [PySDR Signal Processing](https://pysdr.org/content/noise.html) -- SNR = signal_variance / noise_variance

### Tertiary (LOW confidence)
- Normalization ranges for expressiveness metrics (educated estimates based on typical speech audio characteristics, needs validation against actual LibriTTS-R data)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already installed, no new dependencies
- Architecture: HIGH - follows established codebase patterns exactly
- Pitfalls: HIGH - identified from direct code reading and understanding of LLM behavior
- Audio analysis: MEDIUM - algorithms are well-known but normalization bounds are estimated

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable domain, no fast-moving dependencies)
