# Technology Stack: v1.3 Voice Quality

**Project:** audio-book-plz v1.3
**Researched:** 2026-03-09
**Scope:** Stack additions for merger hardening (cross-name exclusion, co-occurrence guards, merge diagnostics), opinionated voice profile extraction (distinctiveness pass, voice overrides), and expressive reference clip selection (pitch/energy/rate variance scoring).
**Overall Confidence:** HIGH -- All three feature areas rely on libraries already installed in the project. One library (librosa) needs to be promoted from transitive to explicit dependency. No new models, no new system dependencies.

---

## Summary: Two Explicit Dependencies to Add, Zero New Installs

The v1.3 features require **zero new pip installs**. Two libraries already present in the venv need to be promoted to explicit dependencies in `pyproject.toml`:

1. **librosa** (already installed as transitive dep, v0.11.0) -- for pitch/energy/rate variance scoring of reference clips
2. **PyYAML** (already installed as transitive dep, v6.0.3) -- for `voice_overrides.yaml` loading

Everything else -- merger hardening, co-occurrence guards, merge diagnostics, opinionated extraction, distinctiveness pass -- uses existing Python stdlib and Pydantic.

---

## Existing Stack (Unchanged for v1.3)

| Technology | Version | Status | v1.3 Role |
|------------|---------|--------|-----------|
| Python | 3.11 | Keep | All features |
| Pydantic | >=2.0 | Keep | Merge audit models, override validation |
| Ollama + Qwen3 14B/8B | existing | Keep | Opinionated extraction prompts, distinctiveness pass |
| difflib.SequenceMatcher | stdlib | Keep | Fuzzy name matching (merger) |
| logging | stdlib | Keep | Merge diagnostics logging |
| json | stdlib | Keep | merge_audit.json output |
| mlx-audio | >=0.3 | Keep | TTS synthesis (unchanged) |
| pedalboard | >=0.9.19 | Keep | Audio mastering (unchanged) |
| Resemblyzer | >=0.1.3 | Keep | Voice consistency (unchanged) |
| soundfile | >=0.12 | Keep | WAV I/O (unchanged) |
| numpy | >=2.0 | Keep | Array operations for audio analysis |

---

## Stack ADDITIONS for v1.3

### 1. librosa >=0.10.0 -- Expressive Reference Clip Scoring

**Purpose:** Compute pitch variance (F0), RMS energy variance, and speaking rate from WAV reference clips to score expressiveness.

**Why librosa:** It is already installed (v0.11.0) as a transitive dependency in the venv. It provides exactly the three audio analysis functions needed:

| Function | What It Computes | Use in Clip Scoring |
|----------|-----------------|---------------------|
| `librosa.pyin()` | Fundamental frequency (F0) contour using probabilistic YIN | Pitch variance -- higher variance = more expressive clip |
| `librosa.feature.rms()` | Root-mean-square energy per frame | Energy variance -- dynamic range indicates expressiveness |
| `librosa.onset.onset_detect()` | Syllable/word onset times | Speaking rate estimate (onsets per second) |

**Why not alternatives:**
- **scipy.signal only:** Can do basic FFT pitch detection but `pyin` is significantly more robust for speech (handles unvoiced frames, octave errors). Reinventing pyin from scipy would be 200+ lines of fragile code.
- **parselmouth (Praat):** Better pitch tracking (STRAIGHT/Praat algorithms) but adds a heavy C++ binary dependency. Overkill for scoring -- we need variance statistics, not phonetic-quality F0.
- **torchaudio:** Already have torch as transitive dep, but torchaudio's pitch tracking is GPU-oriented and less mature for offline batch analysis.
- **Raw numpy FFT:** Too error-prone for voiced/unvoiced detection in speech. Would produce noisy F0 estimates.

**Integration point:** `src/matching/clip_selector.py` -- extend the existing `select_reference_clip()` scoring from duration-only to duration + expressiveness.

**Memory impact:** Negligible. librosa loads audio into numpy arrays (~2MB per 12s clip at 24kHz). Processes one clip at a time.

```python
import librosa
import numpy as np

def score_expressiveness(wav_path: str) -> dict[str, float]:
    """Score a reference clip's expressiveness via pitch/energy/rate variance."""
    y, sr = librosa.load(wav_path, sr=None)  # Keep native sample rate

    # Pitch variance (F0 via pyin)
    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=50, fmax=500, sr=sr
    )
    voiced_f0 = f0[voiced_flag]
    pitch_var = float(np.std(voiced_f0)) if len(voiced_f0) > 5 else 0.0

    # Energy variance (RMS)
    rms = librosa.feature.rms(y=y)[0]
    energy_var = float(np.std(rms)) if len(rms) > 1 else 0.0

    # Speaking rate (onsets per second)
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
    duration = len(y) / sr
    rate = len(onsets) / duration if duration > 0 else 0.0

    return {
        "pitch_variance": pitch_var,
        "energy_variance": energy_var,
        "speaking_rate": rate,
    }
```

### 2. PyYAML >=6.0 -- Voice Overrides File

**Purpose:** Load `voice_overrides.yaml` for manual per-character voice profile tuning.

**Why YAML over JSON:** Voice overrides are a user-facing configuration file that humans will edit by hand. YAML is the right format because:
- No trailing comma issues (common JSON editing pain)
- Comments allowed (users can annotate why they chose specific overrides)
- More readable for nested voice profile fields
- The v1.2 STACK.md ruled out YAML for voice profiles (data models should stay JSON/Pydantic). That reasoning holds for pipeline data, but overrides are user config, not pipeline data. Different concern.

**Why not alternatives:**
- **TOML:** Python 3.11 has `tomllib` in stdlib, but TOML's nested table syntax is awkward for per-character voice profiles with 9+ fields. YAML's indentation-based nesting is more natural.
- **JSON:** No comments. Users need to explain their override choices (e.g., "# Based on BBC audiobook narrator voice").
- **Pydantic Settings:** Overkill. This is a flat config file, not environment-variable-driven configuration.

**Integration point:** New `src/attribution/voice_overrides.py` module. Loaded during the extraction phase, applied after LLM extraction and before merger.

```yaml
# voice_overrides.yaml -- per-character voice profile overrides
# These override LLM-extracted values. Omitted fields keep LLM values.

characters:
  Mr. Darcy:
    pitch: low
    tone: commanding
    energy: restrained
    description: "A deep, measured voice with aristocratic reserve"

  Mrs. Bennet:
    pitch: high
    pace: fast
    energy: animated
    tone: shrill
    description: "A high-pitched, excitable voice prone to dramatic outbursts"
```

```python
from pathlib import Path
import yaml
from src.attribution.models import VoiceProfile

def load_voice_overrides(override_path: Path) -> dict[str, dict[str, str]]:
    """Load voice overrides from YAML file."""
    if not override_path.exists():
        return {}
    with open(override_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("characters", {})
```

---

## Feature-by-Feature Stack Analysis

### Merger Hardening: No New Dependencies

All merger hardening features use existing stdlib and Pydantic:

| Feature | Implementation Approach | Libraries Used |
|---------|------------------------|----------------|
| Cross-name exclusion | Check if candidate alias matches another character's canonical name | `difflib.SequenceMatcher` (existing) |
| Co-occurrence guards on all merge stages | Extend `_named_pair_cooccurs()` check from LLM-consolidation-only to fuzzy + substring stages | stdlib `set` operations (existing) |
| Merge diagnostics / `merge_audit.json` | New Pydantic model for audit trail, `json.dump()` output | `pydantic`, `json`, `logging` (existing) |
| Post-merge validation | Cross-check final registry for contaminated profiles | Pure Python iteration (existing) |
| Trait count cap (30) | Truncate `personality_traits` list in `_merge_two_profiles()` | Python slicing (existing) |
| Surname-only exclusion hardening | Extend `_names_share_surname_only()` to handle title variations | Pure Python string ops (existing) |
| Extraction prompt hardening | Add negative examples to `EXTRACTION_SYSTEM_PROMPT` | String constant (existing) |

**Merge audit model (Pydantic, no new dep):**

```python
class MergeEvent(BaseModel):
    """Single merge event for audit trail."""
    stage: str           # "exact", "fuzzy", "substring", "llm"
    merged_name: str     # Name that was absorbed
    into_name: str       # Name it was merged into
    reason: str          # Why the merge happened
    blocked: bool        # Whether co-occurrence or exclusion blocked it
    block_reason: str    # Why it was blocked (empty if not blocked)

class MergeAudit(BaseModel):
    """Full merge audit trail written to merge_audit.json."""
    input_count: int
    output_count: int
    events: list[MergeEvent]
    cross_contamination_flags: list[str]  # Post-validation warnings
```

### Opinionated Voice Profile Extraction: Ollama LLM (Existing) + PyYAML

| Feature | Implementation Approach | Libraries Used |
|---------|------------------------|----------------|
| `--opinionated` flag | CLI flag in typer, passes to extraction phase | `typer` (existing) |
| Opinionated extraction prompt | Modified `EXTRACTION_SYSTEM_PROMPT` pushing for specific/distinct values instead of "unknown" | String constant (existing) |
| Post-extraction distinctiveness pass | LLM call comparing all profiles, pushing overlapping voices apart | `ollama` (existing) |
| Voice overrides via `voice_overrides.yaml` | Load YAML, apply overrides to CharacterProfile.voice_profile fields | **PyYAML** (promote to explicit dep) |

**Distinctiveness pass approach:** After extraction and merger, send the full character registry back to the LLM with a prompt asking it to differentiate overlapping profiles. This is a single LLM call using the existing `call_llm_structured()` infrastructure -- no new libraries.

### Expressive Reference Clip Selection: librosa (Existing)

| Feature | Implementation Approach | Libraries Used |
|---------|------------------------|----------------|
| Pitch variance scoring | `librosa.pyin()` -> `np.std()` of voiced F0 values | **librosa** (promote), numpy (existing) |
| Energy variance scoring | `librosa.feature.rms()` -> `np.std()` of RMS frames | **librosa** (promote), numpy (existing) |
| Speaking rate scoring | `librosa.onset.onset_detect()` -> onsets/second | **librosa** (promote) |
| Rate-match to character pace | Compare clip speaking rate against VoiceProfile.pace | Pure Python comparison (existing) |
| Combined expressiveness score | Weighted combination of pitch_var + energy_var + rate_match | numpy (existing) |

**Scoring formula (proposed):**

```python
def combined_score(
    duration: float,
    pitch_var: float,
    energy_var: float,
    speaking_rate: float,
    target_pace: str,  # from VoiceProfile.pace
) -> float:
    """Combine duration proximity + expressiveness into single score."""
    # Duration score (existing logic, 0-1)
    dur_score = 1.0 / (1.0 + abs(duration - 12.5))

    # Expressiveness score (0-1, normalized)
    # Higher pitch/energy variance = more expressive = better reference
    expr_score = min(1.0, (pitch_var / 50.0) + (energy_var / 0.05))

    # Rate match score (0-1)
    pace_targets = {"fast": 5.0, "moderate": 3.5, "slow": 2.0}
    target_rate = pace_targets.get(target_pace, 3.5)
    rate_score = 1.0 / (1.0 + abs(speaking_rate - target_rate))

    # Weighted combination: duration matters most, then expressiveness
    return 0.4 * dur_score + 0.35 * expr_score + 0.25 * rate_score
```

---

## Installation Changes for v1.3

```bash
# No new pip installs needed -- both libraries are already in the venv.
# Only change: add to pyproject.toml explicit dependencies.
```

**pyproject.toml additions:**

```toml
[project]
dependencies = [
    # ... existing deps ...
    "librosa>=0.10.0",   # Pitch/energy/rate analysis for clip scoring
    "PyYAML>=6.0",       # Voice overrides config file
]
```

**Verification script:**

```bash
python -c "
import librosa
print(f'librosa {librosa.__version__} -- pyin: {hasattr(librosa, \"pyin\")}')

import yaml
print(f'PyYAML {yaml.__version__} -- safe_load: {hasattr(yaml, \"safe_load\")}')

from pydantic import BaseModel
print('Pydantic available')

import numpy as np
print(f'NumPy {np.__version__}')
"
```

---

## What NOT to Add

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `parselmouth` (Praat bindings) | Heavy C++ binary dependency for phonetic-quality F0 tracking. We need variance statistics, not formant analysis or phonetic alignment. Adds ~50MB to install. | `librosa.pyin()` -- probabilistic YIN is sufficient for scoring variance |
| `crepe` (neural pitch tracker) | Requires TensorFlow/PyTorch inference for pitch detection. Accurate but massive overkill for ranking clips by variance. Would compete for memory with Ollama/MLX. | `librosa.pyin()` -- lightweight, CPU-only |
| `opensmile` (audio feature toolkit) | Full-featured but complex C++ dependency with Python bindings. Extracts 6,000+ features when we need 3. | `librosa` for the 3 specific features needed |
| `FuzzyWuzzy` / `thefuzz` for name matching | Current `difflib.SequenceMatcher` works well. FuzzyWuzzy wraps SequenceMatcher with minor additions and pulls in `python-Levenshtein` C extension. | `difflib.SequenceMatcher` (stdlib, already working) |
| `networkx` for co-occurrence graph | Co-occurrence is simple set intersection -- characters share chapters. A graph library is overkill for `set_a & set_b`. | Python `set` operations (stdlib) |
| `rapidfuzz` for faster fuzzy matching | Faster than SequenceMatcher but merger processes <100 profiles. Sub-millisecond improvement is irrelevant. Adds C++ dependency. | `difflib.SequenceMatcher` (stdlib) |
| `jsonschema` for merge audit validation | Pydantic already validates the audit model. Adding jsonschema creates parallel validation. | Pydantic `BaseModel` (existing) |
| Any new LLM model for distinctiveness | The existing Qwen3 14B/8B via Ollama handles profile comparison and differentiation well. A second model wastes memory. | Existing Ollama + Qwen3 |
| `confuse` or `dynaconf` for config management | Voice overrides is a single YAML file. Full config management frameworks are overkill. | `yaml.safe_load()` (PyYAML) |

---

## Alternatives Considered

| Goal | Recommended | Alternative | Why Not |
|------|-------------|-------------|---------|
| Pitch analysis for clip scoring | librosa `pyin()` | scipy `find_peaks()` on FFT | pyin handles voiced/unvoiced detection, octave correction. Raw FFT pitch detection is brittle for speech. |
| Pitch analysis for clip scoring | librosa `pyin()` | `parselmouth` Praat | Better quality but heavy dependency for a scoring heuristic. We need variance, not phonetic precision. |
| Energy analysis | librosa `feature.rms()` | numpy manual RMS | Equivalent result but librosa handles framing, hop_length, windowing correctly. 1 line vs 5 lines. |
| Speaking rate estimation | librosa `onset_detect()` | Word count / duration from transcript | Not all clips have transcripts. Onset detection works on audio directly. |
| Voice overrides format | YAML | JSON | No comments, harder to edit by hand. Overrides are user config, not pipeline data. |
| Voice overrides format | YAML | TOML (stdlib `tomllib`) | TOML's `[characters."Mr. Darcy"]` table syntax is awkward. YAML nesting is more natural for voice profiles. |
| Merge diagnostics output | JSON (`merge_audit.json`) | Structured logging only | Logging is ephemeral. A persistent audit file enables post-hoc analysis and debugging of merge decisions. |
| Cross-name exclusion | Set-based exclusion list built during merge | Pre-computed graph of all character name relationships | Set operations are O(n) and merger has <100 profiles. Graph is overkill. |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| librosa >=0.10.0 | numpy >=2.0, scipy >=1.5, soundfile >=0.12 | All already in venv. librosa 0.11.0 installed. |
| librosa >=0.10.0 | Python 3.11 | Fully supported. |
| PyYAML >=6.0 | Python 3.11 | Fully supported. PyYAML 6.0.3 installed. |
| Pydantic >=2.0 | All existing models | No changes to Pydantic usage patterns. |

**librosa transitive dependency chain (already satisfied):**
- `numpy` (installed: 2.4.2)
- `scipy` (installed: 1.17.1)
- `soundfile` (installed: 0.13.1)
- `numba` (installed as librosa dep)
- `llvmlite` (installed as numba dep)

All already present. No new downloads when promoting librosa to explicit dep.

---

## Memory Budget (Unchanged from v1.2)

v1.3 adds no new models. librosa audio analysis is CPU-only and processes one clip at a time (~2MB per clip). Memory profile is identical to v1.2:

| Phase | Primary Consumer | Memory | v1.3 Change |
|-------|-----------------|--------|-------------|
| 2. LLM Attribution + Extraction | Ollama qwen3:14b Q4_K_M | ~10 GB | Opinionated prompt + distinctiveness pass = same model, more calls |
| 3. Voice Matching + Clip Selection | librosa + numpy | ~0.3 GB | Clip scoring adds ~2MB per clip analysis. Negligible. |
| 4. TTS Synthesis | Qwen3-TTS 1.7B Base bf16 (MLX) | ~4 GB | Unchanged |

No changes to the sequential phase architecture. LLM and TTS never run simultaneously.

---

## Integration Points Summary

| v1.3 Feature | Existing File to Modify | New Files |
|-------------|------------------------|-----------|
| Cross-name exclusion | `src/attribution/merger.py` | None |
| Co-occurrence guards (all stages) | `src/attribution/merger.py` | None |
| Merge diagnostics | `src/attribution/merger.py` | None (audit model goes in `models.py`) |
| Post-merge validation | `src/attribution/merger.py` | None |
| Trait count cap | `src/attribution/merger.py` | None |
| Surname-only hardening | `src/attribution/merger.py` | None |
| Extraction prompt hardening | `src/attribution/extractor.py` | None |
| Opinionated extraction (`--opinionated`) | `src/attribution/extractor.py`, `src/cli.py` | None |
| Distinctiveness pass | `src/attribution/merger.py` or new function | None |
| Voice overrides | `src/attribution/extractor.py` | `src/attribution/voice_overrides.py` |
| Expressive clip scoring | `src/matching/clip_selector.py` | None |
| Rate-match to character pace | `src/matching/clip_selector.py`, `src/matching/orchestrator.py` | None |

---

## Sources

### HIGH Confidence (Verified in Current Venv)
- librosa 0.11.0 installed and tested: `pyin()`, `feature.rms()`, `onset.onset_detect()` all available
- PyYAML 6.0.3 installed and tested: `safe_load()` works for voice override YAML format
- numpy 2.4.2, scipy 1.17.1, soundfile 0.13.1 all present as librosa dependencies
- Existing merger.py, clip_selector.py, extractor.py, models.py code reviewed for integration points

### MEDIUM Confidence (Library Documentation)
- librosa pyin documentation: https://librosa.org/doc/latest/generated/librosa.pyin.html -- probabilistic YIN pitch tracking, fmin/fmax params
- librosa RMS documentation: https://librosa.org/doc/latest/generated/librosa.feature.rms.html -- frame-level energy
- librosa onset_detect documentation: https://librosa.org/doc/latest/generated/librosa.onset.onset_detect.html -- onset detection for rate estimation
- PyYAML safe_load: https://pyyaml.org/wiki/PyYAMLDocumentation -- safe loading prevents arbitrary code execution

### LOW Confidence (Needs Empirical Validation)
- Optimal weights for combined expressiveness score (0.4 duration / 0.35 expressiveness / 0.25 rate-match) -- need A/B testing against clip quality
- Pitch variance normalization factor (dividing by 50.0 Hz) -- may need tuning per speaker gender/age
- Speaking rate thresholds for pace matching (fast=5.0, moderate=3.5, slow=2.0 onsets/sec) -- need calibration against LibriTTS-R data
- Whether higher expressiveness clips actually produce better TTS voice cloning -- the assumption is reasonable but unvalidated

---

*Stack research for: audio-book-plz v1.3 voice quality features*
*Focus: Merger hardening (pure Python), opinionated voice profiles (LLM + YAML), expressive clip scoring (librosa)*
*Researched: 2026-03-09*
