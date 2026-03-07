# Technology Stack: v1.2 Voice Expression

**Project:** audio-book-plz v1.2
**Researched:** 2026-03-06
**Scope:** Stack additions/changes for voice expression features: style conditioning, emotion-to-prosody mapping, unified voice profiles.
**Overall Confidence:** MEDIUM -- The central question (combining voice cloning + style control in Qwen3-TTS) has a confirmed architectural limitation that shapes the entire approach.

---

## Critical Finding: Voice Cloning vs Style Control Are Separate Models

**Confidence: HIGH** (verified via Qwen3-TTS technical report, official HuggingFace model cards, GitHub discussion #231)

Qwen3-TTS has three model variants with mutually exclusive capabilities:

| Model | Voice Cloning (`ref_audio`) | Style Instructions (`instruct`) | Voice Source |
|-------|:---------------------------:|:-------------------------------:|-------------|
| **Base** (current) | YES | NO | Any audio reference |
| **CustomVoice** | NO | YES | 9 preset speakers only |
| **VoiceDesign** | NO | YES (voice creation) | Text description only |

**No single Qwen3-TTS model supports both voice cloning from LibriTTS-R AND emotion/style instructions simultaneously.** The v1.1 STACK.md incorrectly showed `ref_audio` being passed to `generate_custom_voice()` -- this does not work. The Base model ignores `instruct` parameters entirely (confirmed via GitHub discussion #231 and HuggingFace discussion #38).

**The upcoming `Qwen3-TTS-25Hz-1.7B-VoiceEditing` model may solve this**, but it has not been released as of 2026-03-06.

### Implication for v1.2

Since the project clones voices from LibriTTS-R (the core value proposition), we MUST stay on the Base model. This means **style/emotion control cannot happen at the TTS model level** and must be achieved through other means.

---

## Existing Stack (Unchanged for v1.2)

Everything from v1.0/v1.1 remains. No new pip packages are needed.

| Technology | Version | Status |
|------------|---------|--------|
| Python | 3.11 | Keep |
| mlx-audio | >=0.3.1 | Keep -- Qwen3-TTS 1.7B Base via MLX |
| mlx | >=0.30.3 | Keep |
| pedalboard | >=0.9.22 | Keep -- gains new emotion-aware parameterization |
| Resemblyzer | >=0.1.3 | Keep |
| pydub | >=0.25.1 | Keep |
| Pydantic | >=2.0 | Keep -- used for voice profile data models |
| Ollama + Qwen3 14B/8B | existing | Keep |
| All other v1.1 deps | existing | Keep |

---

## Stack ADDITIONS: None Required

**The v1.2 voice expression features require ZERO new pip packages.** Everything needed is already in the project. This section explains what existing tools cover each need.

### 1. Voice Style Descriptions -> TTS: Text Prompt Engineering (No New Deps)

Since the Base model's `generate()` does not accept an `instruct` parameter, the primary mechanism for influencing prosody is **text manipulation** -- prepending or embedding style cues in the synthesized text itself.

**Approach: Contextual text conditioning via the input text**

The Base model has strong contextual understanding and adapts prosody based on text semantics. While it cannot follow explicit style instructions, it DOES respond to:

1. **Text content itself** -- exclamation marks, question marks, ellipses, and emotional word choice naturally affect prosody
2. **Surrounding context** -- the model reads the full text chunk and adapts tone
3. **Speech-act annotations** -- already implemented in v1.1 via `post_processor.py`

**What this means practically:**
- The LLM (Qwen3 14B) generates emotion annotations (already built in v1.1)
- These annotations drive **post-processing parameters** (volume, speed, pitch-shift), NOT TTS model instructions
- The three-layer system (voice baseline + scene mood + line override) maps to post-processing parameter tables, not TTS API calls

**No new library needed.** The existing `post_processor.py` (speech-act adjustments via numpy) is the correct integration point.

### 2. Emotion-to-Prosody Mapping: Extended Post-Processing (No New Deps)

The current `post_processor.py` handles 4 speech acts (spoken, whispered, shouted, thought) with volume_db and speed_factor adjustments. v1.2 extends this to also consider the 8-category emotion taxonomy from `EmotionCategory`.

**Implementation: Expand `SPEECH_ACT_PARAMS` into a 2D mapping**

```python
# Existing (v1.1) -- speech act only
SPEECH_ACT_PARAMS = {
    "spoken":    {"volume_db": 0.0,  "speed_factor": 1.0},
    "whispered": {"volume_db": -4.5, "speed_factor": 1.0},
    "shouted":   {"volume_db": 4.5,  "speed_factor": 1.08},
    "thought":   {"volume_db": -3.0, "speed_factor": 0.93},
}

# New (v1.2) -- emotion layer adds deltas on TOP of speech act
EMOTION_DELTAS = {
    "neutral":    {"volume_db": 0.0,  "speed_factor": 1.0,  "pitch_semitones": 0.0},
    "joy":        {"volume_db": 1.5,  "speed_factor": 1.05, "pitch_semitones": 0.5},
    "sadness":    {"volume_db": -2.0, "speed_factor": 0.92, "pitch_semitones": -0.3},
    "anger":      {"volume_db": 3.0,  "speed_factor": 1.10, "pitch_semitones": 0.0},
    "fear":       {"volume_db": -1.0, "speed_factor": 1.08, "pitch_semitones": 0.3},
    "surprise":   {"volume_db": 2.0,  "speed_factor": 1.12, "pitch_semitones": 0.5},
    "disgust":    {"volume_db": 0.5,  "speed_factor": 0.95, "pitch_semitones": -0.2},
    "tenderness": {"volume_db": -1.5, "speed_factor": 0.90, "pitch_semitones": 0.0},
}
```

**Pitch shifting** uses pedalboard's existing capabilities or numpy-based resampling (already in `post_processor.py` for speed adjustment). No new dependency.

**Three-layer composition order:**
1. Start with speech-act base params (whispered/shouted/thought/spoken)
2. Apply emotion delta from scene mood (additive)
3. Apply emotion delta from line override if present (replaces scene mood delta)
4. Clamp all values to safe ranges

**Libraries used:** numpy (existing), pedalboard (existing for pitch if needed).

### 3. Unified Voice Profile Data Model: Pydantic Refactor (No New Deps)

The current codebase has two overlapping voice description fields:
- `VoiceQualities` (pitch, pace, tone, accent) -- used by voice matching
- `VoiceBaseline` (pace, tone, energy, typical_emotion, description) -- used by emotion system

v1.2 merges these into a single `VoiceProfile` model. This is a Pydantic model refactor, not a library change.

```python
class VoiceProfile(BaseModel):
    """Unified voice description replacing VoiceQualities + VoiceBaseline.

    Used by:
    - Voice matching (trait_matcher, embedding_matcher)
    - Emotion system (character baseline layer)
    - Post-processing (per-character parameter offsets)
    """
    pitch: str           # "high", "medium", "low", "unknown"
    pace: str            # "fast", "moderate", "slow" / "measured", "rapid", etc.
    tone: str            # "warm", "gruff", "silky", "gravelly", etc.
    accent: str          # "British", "Southern American", "unknown"
    energy: str          # "restrained", "animated", "intense", "subdued"
    typical_emotion: str # "sardonic", "cheerful", "weary"
    description: str     # "A slow, gravelly voice with weary patience"
```

**Library used:** Pydantic (existing). No migration tool needed -- the merge is manual field consolidation.

### 4. Voice Profile -> Voice Matching Enhancement (No New Deps)

The unified `VoiceProfile.description` field (e.g., "A slow, gravelly voice with weary patience") can be embedded via the existing `sentence-transformers` and compared against LibriTTS-P speaker `trait_text` embeddings in `embedding_matcher.py`.

**Libraries used:** sentence-transformers (existing), numpy (existing).

---

## What NOT to Add

| Avoid | Why | What to Use Instead |
|-------|-----|---------------------|
| `Qwen3-TTS CustomVoice model` | Cannot clone from LibriTTS-R. Locked to 9 preset speakers. Loses the project's core value proposition of matching characters to real human voices. | Stay on Base model + post-processing for emotion |
| `Qwen3-TTS VoiceDesign model` | Creates voices from text descriptions, but cannot clone existing voices. Generated voices lack the human naturalness of LibriTTS-R references. | Stay on Base model |
| `pyttsx3` / `espeak` for style control | Low-quality TTS engines. Style control exists but voice quality is orders of magnitude worse. | Post-processing approach |
| `praat-parselmouth` for pitch manipulation | Adds a heavy dependency (Praat phonetics toolkit) for pitch shifting that numpy interpolation or pedalboard can handle. | numpy resampling or pedalboard |
| `librosa` for audio feature extraction | Pulls in numba, llvmlite, soundfile. Not needed -- pitch/speed modification via numpy is sufficient for the subtle adjustments required. | numpy (existing) |
| `sounddevice` or `pyaudio` | Not needed for batch processing. These are real-time playback libraries. | N/A -- batch pipeline |
| Any emotion detection NLP library (e.g., `transformers` for sentiment) | Emotion detection is already done by the LLM (Qwen3 14B via Ollama). Adding a separate NLP model wastes memory and creates conflicting annotations. | Existing Ollama LLM |
| `yaml` / `toml` for voice profiles | Voice profiles are Pydantic models serialized to JSON (consistent with all other data models in the project). Adding YAML/TOML config introduces a parallel config format. | Pydantic + JSON (existing) |

---

## Recommended Stack Changes Summary

| Component | Current (v1.1) | Change for v1.2 | New Deps? |
|-----------|----------------|-----------------|-----------|
| TTS Model | Qwen3-TTS 1.7B Base bf16 | **No change** -- stay on Base for voice cloning | No |
| TTS API | `model.generate(text, ref_audio, ref_text)` | **No change** -- no `instruct` param available on Base | No |
| Emotion -> Audio | Speech-act post-processing only (volume_db, speed_factor) | **Extend** with emotion-category deltas and optional pitch shift | No |
| Voice Data Model | `VoiceQualities` + `VoiceBaseline` (separate) | **Merge** into single `VoiceProfile` Pydantic model | No |
| Voice Matching | `trait_matcher` + `embedding_matcher` | **Enhance** to use unified `VoiceProfile.description` embedding | No |
| Post-Processor | `apply_speech_act_adjustments()` | **Extend** to `apply_expression_adjustments(audio, sample_rate, speech_act, emotion, intensity)` | No |

---

## API Details for Existing Libraries

### mlx-audio `model.generate()` -- Base Model (Current API, Unchanged)

```python
from mlx_audio.tts.utils import load_model

model = load_model("mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")

# This is the ONLY generate method available on the Base model.
# No instruct parameter. No style control. Voice cloning only.
results = list(model.generate(
    text="The door creaked open slowly.",
    ref_audio="voices/speaker_7335.wav",
    ref_text="She opened the door and stepped into the hallway.",
))
```

**Parameters accepted by Base model `generate()`:**
- `text` (str) -- text to synthesize
- `ref_audio` (str) -- path to reference audio for voice cloning
- `ref_text` (str) -- transcript of reference audio
- `verbose` (bool) -- logging verbosity

**Parameters NOT accepted by Base model:** `instruct`, `speaker`, `language` (CustomVoice-only).

### pedalboard -- Extended Emotion Post-Processing

Pitch shifting can be achieved via pedalboard's `PitchShift` plugin (available in pedalboard >=0.7.0, already installed at >=0.9.22):

```python
from pedalboard import PitchShift

# Subtle pitch shift for emotion (e.g., +0.5 semitones for joy)
pitch_shift = PitchShift(semitones=0.5)
shifted_audio = pitch_shift(audio_array, sample_rate)
```

This adds pitch as a third dimension alongside the existing volume and speed adjustments, without any new dependencies.

### Pydantic -- VoiceProfile Model Migration

```python
# Backward-compatible: old data with voice_qualities + voice_baseline
# can be loaded and merged into VoiceProfile

class CharacterProfile(BaseModel):
    # ... existing fields ...
    voice_profile: VoiceProfile          # NEW unified field
    voice_qualities: VoiceQualities | None = None  # DEPRECATED, keep for migration
    voice_baseline: VoiceBaseline | None = None    # DEPRECATED, keep for migration

    @model_validator(mode="after")
    def merge_legacy_fields(self) -> "CharacterProfile":
        """Auto-populate voice_profile from legacy fields if not set."""
        if self.voice_profile is None and self.voice_qualities is not None:
            self.voice_profile = VoiceProfile.from_legacy(
                self.voice_qualities, self.voice_baseline
            )
        return self
```

---

## Memory Budget (Unchanged from v1.1)

v1.2 adds no new models or heavy libraries. Memory profile is identical to v1.1:

| Phase | Primary Consumer | Memory |
|-------|-----------------|--------|
| 2. LLM Attribution (with emotion) | Ollama qwen3:14b Q4_K_M | ~10 GB |
| 4. TTS Synthesis | Qwen3-TTS 1.7B Base bf16 (MLX) | ~4 GB |
| 4b. Post-processing | numpy + pedalboard | ~0.5 GB |

No changes to the sequential phase architecture. LLM and TTS never run simultaneously.

---

## Installation Changes for v1.2

```bash
# No new packages to install.
# No new models to download.
# No new system dependencies.

# Verify existing stack is sufficient:
python -c "
from pedalboard import PitchShift
print('PitchShift available:', PitchShift is not None)

from pydantic import BaseModel
print('Pydantic available')

import numpy as np
print('NumPy available')
"
```

---

## Alternatives Considered

| Goal | Recommended | Alternative | Why Not |
|------|-------------|-------------|---------|
| Emotion in voice | Post-processing (volume, speed, pitch) | Switch to CustomVoice model | Loses voice cloning from LibriTTS-R. Only 9 preset voices -- cannot match character voice traits. |
| Emotion in voice | Post-processing | Wait for VoiceEditing model (25Hz) | Not released. Unknown timeline. Cannot plan v1.2 around unreleased software. |
| Emotion in voice | Post-processing | Fine-tune Base model to accept instruct | Requires GPU training infrastructure, curated dataset, and significant time investment. Overkill for personal audiobook tool. |
| Pitch manipulation | pedalboard PitchShift | librosa pitch_shift | Adds heavy deps (numba, llvmlite). pedalboard is already installed. |
| Pitch manipulation | pedalboard PitchShift | praat-parselmouth | Adds Praat binary dependency. Harder to install on macOS. |
| Voice profile format | Pydantic + JSON | YAML config files | Breaks consistency with all other data models in the project. |
| Emotion taxonomy | Existing 8-category EmotionCategory enum | Expand to 15+ emotions | More categories = less reliable LLM classification. 8 categories map cleanly to distinct audio parameter profiles. |

---

## Future Considerations (Out of Scope for v1.2)

| When Available | What | Impact |
|----------------|------|--------|
| Qwen3-TTS-25Hz-1.7B-VoiceEditing release | Model that may support voice cloning + style instructions | Could replace post-processing approach with native TTS-level emotion control |
| mlx-audio v0.4+ | May add new APIs or fix CustomVoice chunking | Monitor releases monthly |
| Fine-tuning Qwen3-TTS Base | Train Base model to follow instruct with cloned voices | Would require GPU training pipeline; consider for v1.3+ if post-processing approach proves insufficient |

---

## Sources

### HIGH Confidence (Official Documentation, Technical Report)
- Qwen3-TTS Technical Report: https://arxiv.org/html/2601.15621v1 -- confirms Base model does NOT support instruction control
- Qwen3-TTS-12Hz-1.7B-CustomVoice HuggingFace: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice -- confirms 9 preset speakers only, no ref_audio
- Qwen3-TTS-12Hz-1.7B-Base HuggingFace: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base -- confirms voice cloning API
- Qwen3-TTS GitHub: https://github.com/QwenLM/Qwen3-TTS -- official model comparison table
- pedalboard PitchShift: https://spotify.github.io/pedalboard/ -- verified PitchShift available in current version
- mlx-audio GitHub: https://github.com/Blaizzy/mlx-audio -- model loading and generate API

### MEDIUM Confidence (Community Sources, Discussions)
- GitHub Discussion #231 (emotion in cloned voices): https://github.com/QwenLM/Qwen3-TTS/discussions/231 -- confirms Base model ignores instruct, community suggests waiting for VoiceEditing model
- HuggingFace Discussion #38 (CustomVoice emotion): https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/discussions/38 -- workaround via fine-tuning, not viable for this project
- myByways blog (mlx-audio on macOS): https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos -- confirms CustomVoice and Base are separate code paths
- mlx-audio Qwen3-TTS README: https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md

### LOW Confidence (Unverified)
- Pitch shift quality via pedalboard at sub-semitone levels for emotional expression -- needs empirical testing
- Whether Base model's contextual prosody adaptation responds meaningfully to punctuation/word-choice manipulation -- needs A/B testing
- Optimal emotion delta values (volume_db, speed_factor, pitch_semitones) -- need tuning against real audiobook output

---

## CORRECTION to v1.1 STACK.md

The v1.1 STACK.md (lines 82-104) incorrectly shows CustomVoice model as supporting both `ref_audio` voice cloning AND `instruct` style control. This is wrong:

- `generate_custom_voice()` does NOT accept `ref_audio`
- `generate()` on Base model does NOT accept `instruct`

The v1.1 code (qwen_engine.py) correctly uses the Base model with `model.generate(text, ref_audio, ref_text)` -- no instruct parameter. The v1.1 STACK.md documentation was aspirational, not factual. The actual v1.1 implementation is correct; only the research document had the error.

---

*Stack research for: audio-book-plz v1.2 voice expression features*
*Focus: Qwen3-TTS style conditioning limitations, emotion-to-prosody via post-processing, voice profile unification*
*Researched: 2026-03-06*
