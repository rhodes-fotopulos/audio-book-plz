# Feature Landscape: v1.2 Voice Expression

**Domain:** Expressive TTS conditioning for AI audiobook pipeline
**Researched:** 2026-03-06
**Confidence:** MEDIUM (Qwen3-TTS Base model limitations confirmed via official sources; VoiceDesign workaround is verified but untested in this codebase; emotion-to-prosody effectiveness is empirically dependent)

---

## Critical Context: What Already Exists

Before mapping features, the existing system must be understood. v1.1 shipped these components that v1.2 builds on:

| Component | Status | Where | What It Produces |
|-----------|--------|-------|------------------|
| `VoiceBaseline` | Extracted, never consumed by TTS | `attribution/models.py` | pace, tone, energy, typical_emotion, description per character |
| `VoiceQualities` | Used by voice matching only | `attribution/models.py` | pitch, pace, tone, accent per character |
| `SceneMood` | Extracted, never consumed by TTS | `attribution/emotion/models.py` | mood (8 categories), intensity, description per scene |
| `LineOverride` | Extracted, never consumed by TTS | `attribution/emotion/models.py` | emotion, intensity, reason per high-contrast line |
| Speech-act tags | Consumed by post-processor | `synthesis/post_processor.py` | volume/speed adjustments for whispered/shouted/thought |
| `QwenTTSEngine.generate()` | Only uses text + ref_audio + ref_text | `synthesis/qwen_engine.py` | Raw audio with no style conditioning |

**The gap:** Rich emotion and voice data is extracted by the LLM but never reaches the TTS engine. The pipeline generates the same prosody whether a character is "whispering in terror" or "shouting with joy" -- only post-processing volume/speed adjustments differentiate speech acts.

---

## Critical Technical Constraint: Base Model Has No Instruct Parameter

**Confidence: HIGH** (confirmed via HuggingFace model card, official GitHub, mlx-audio docs)

The project uses `Qwen3-TTS-12Hz-1.7B-Base` via mlx-audio. This model variant does **not** accept an `instruct` parameter. The `generate()` / `generate_voice_clone()` API accepts only:

- `text` -- the content to speak
- `ref_audio` -- reference voice clip
- `ref_text` -- transcript of reference clip
- Standard generation kwargs (`max_new_tokens`, `top_p`, etc.)

Style/emotion instructions (`instruct` parameter) only work with:
- **CustomVoice** model -- 9 preset speakers, no voice cloning
- **VoiceDesign** model -- generates new voices from descriptions, no cloning

**You cannot combine voice cloning with explicit emotion instructions in a single model call.** This is the fundamental constraint shaping all v1.2 features.

---

## Table Stakes

Features users expect from an expressive audiobook. Missing these means the "voice expression" milestone delivers no perceptible improvement.

| Feature | Why Expected | Complexity | Dependencies | Notes |
|---------|--------------|------------|--------------|-------|
| Unified voice_profile field | Two overlapping voice models (VoiceQualities + VoiceBaseline) creates confusion and inconsistency in matching | LOW | None -- pure data model refactor | Merge into single `VoiceProfile` with all fields. voice_qualities.tone and voice_baseline.tone currently duplicate. |
| Voice profile consumed by voice matching | Currently VoiceQualities drives matching; VoiceBaseline is ignored | LOW | Unified voice_profile | trait_matcher and embedding_matcher should use the richer unified profile for better speaker selection |
| Scene mood influences synthesis | Emotion data is extracted but thrown away -- the emotion system is inert | MEDIUM | Requires a conditioning pathway to TTS | The hardest table-stakes item because Base model has no instruct param |
| Line-level emotion overrides influence synthesis | High-contrast moments (laughing at a funeral) should sound different | MEDIUM | Scene mood pathway must exist first | Overrides are sparse (few per chapter) so the mechanism can be simpler |

---

## Differentiators

Features that move beyond "functional" to "notably expressive." Not expected but valued by anyone doing A/B comparison.

| Feature | Value Proposition | Complexity | Dependencies | Notes |
|---------|-------------------|------------|--------------|-------|
| VoiceDesign-then-Clone pipeline for per-character style | Generate a reference clip using VoiceDesign with character's voice_profile description, then clone from it -- bakes style into the voice itself | HIGH | VoiceDesign model via mlx-audio, voice_profile description field | The official recommended approach for combining style with cloning. Requires loading VoiceDesign model during voice prep (one-time per character). |
| Three-layer TTS conditioning stack | voice_profile (constant per character) + scene mood (varies per scene) + line override (rare) cascading to influence synthesis | HIGH | All table-stakes items above | The architecture goal. How each layer actually reaches the TTS is the design challenge. |
| Emotion-to-text-cue injection | Prepend contextual text cues based on scene mood/line override to leverage Qwen3-TTS's text-semantic understanding | MEDIUM | Scene mood data, synthesizer integration | e.g., prepending "[speaking softly, with sadness]" before the text. Qwen3-TTS infers prosody from text semantics. Effectiveness varies -- needs empirical testing. |
| Speech-act-aware post-processing expansion | Extend current volume/speed adjustments to include emotion-mapped parameters (e.g., sad = slower pace, angry = faster pace + slight volume boost) | LOW | Emotion data flow to post-processor | Builds on existing `SPEECH_ACT_PARAMS` pattern. Low risk, additive. |
| Cached voice_clone_prompt per character | Pre-compute `create_voice_clone_prompt()` once per character and reuse across all segments -- faster synthesis, more consistent voice | LOW | mlx-audio API support for `voice_clone_prompt` | Currently re-processes ref_audio for every segment. Caching eliminates redundant computation. |

---

## Anti-Features

Features to explicitly NOT build. Each has been considered and rejected for specific reasons.

| Anti-Feature | Why Tempting | Why Avoid | What to Do Instead |
|--------------|-------------|-----------|-------------------|
| Per-segment instruct parameter with cloned voice | Seems like the obvious way to add emotion | Base model does not support instruct with cloning. Period. No workaround except switching models. | Use text-semantic inference + text cue injection + post-processing |
| Switching to CustomVoice model | Has instruct support for emotion | Only 9 preset voices. Loses the core value prop of distinct per-character voices from 2,443 LibriTTS-P speakers. | Stay on Base model with voice cloning |
| Loading VoiceDesign + Base simultaneously | Could design voices on-the-fly during synthesis | 16GB memory budget. Two 1.7B models cannot coexist with any headroom. | Load VoiceDesign during voice prep phase (before synthesis), unload, then load Base for synthesis |
| Real-time emotion re-synthesis | Re-generate segment if emotion analysis changes | 3000+ segments per book. Emotion changes are rare. Full re-synthesis is wasteful. | Checkpoint-aware selective regeneration for changed segments only |
| SSML/markup-based prosody control | Industry standard for commercial TTS | Qwen3-TTS does not support SSML. MLX inference path has no SSML parser. | Text-semantic inference is Qwen3-TTS's approach to prosody |
| Per-word emphasis marking | "Emphasize THIS word in the sentence" | No mechanism in Qwen3-TTS Base to control word-level emphasis. Would require fine-tuning. | Rely on text-semantic understanding. Qwen3-TTS handles emphasis from context (italics, caps, exclamation) |
| Emotion interpolation between scenes | Smooth transition from "joyful" to "tense" across scene boundary | Over-engineering. Scene breaks already have pauses. Listeners expect mood shifts at scene boundaries. | Sharp scene mood transitions are natural in audiobooks |

---

## Feature Dependencies

```
Unified voice_profile (data model refactor)
    |
    +-- Voice matching uses unified profile
    |       (trait_matcher, embedding_matcher consume new fields)
    |
    +-- VoiceDesign-then-Clone pipeline (OPTIONAL, HIGH value)
    |       Uses voice_profile.description to generate styled reference clip
    |       Requires: loading VoiceDesign model during voice prep phase
    |       Produces: style-baked reference clips per character
    |
    +-- Cached voice_clone_prompt
            Pre-compute once per character, reuse for all segments

Scene mood data flow to synthesizer
    |
    +-- Emotion-to-text-cue injection
    |       Prepend mood context to segment text before TTS
    |
    +-- Speech-act post-processing expansion
            Extend volume/speed params with emotion-mapped values

Line override data flow to synthesizer
    |
    +-- Overrides replace scene mood for specific segments
    |       Higher priority than scene mood in the cascade
    |
    +-- Same text-cue injection mechanism as scene mood
```

### Critical Path

1. **voice_profile unification** -- Pure refactor, no TTS changes, unblocks everything
2. **Scene mood data flow** -- Pipe emotion data from attribution output to synthesizer
3. **Text-cue injection** -- The primary mechanism for emotion to reach TTS
4. **Line overrides** -- Uses same mechanism as scene mood, just higher priority
5. **Post-processing expansion** -- Additive, low risk
6. **VoiceDesign pipeline** (optional) -- Highest impact but highest complexity
7. **Cached voice_clone_prompt** -- Performance optimization, do last

---

## Detailed Feature Analysis

### 1. Unified voice_profile

**Complexity:** LOW
**Risk:** LOW

Merge `VoiceQualities` and `VoiceBaseline` into a single `VoiceProfile` model:

```
VoiceProfile:
    pitch: str          (from VoiceQualities)
    pace: str           (from VoiceQualities -- overlaps VoiceBaseline.pace)
    tone: str           (from VoiceQualities -- overlaps VoiceBaseline.tone)
    accent: str         (from VoiceQualities)
    energy: str         (from VoiceBaseline)
    typical_emotion: str (from VoiceBaseline)
    description: str    (from VoiceBaseline -- key for VoiceDesign)
```

**Migration:** `CharacterProfile` gets `voice_profile: VoiceProfile` replacing both `voice_qualities` and `voice_baseline`. Backward compatibility via a migration function that reads old JSON and constructs the new model. LLM extraction prompt updated to produce unified schema.

**Why table stakes:** The duplication is confusing (which `tone` do you use?), and the unified `description` field is needed downstream for both VoiceDesign and text-cue injection.

### 2. Scene Mood + Line Override Conditioning via Text Cues

**Complexity:** MEDIUM
**Risk:** MEDIUM (effectiveness depends on how well Qwen3-TTS responds to prepended text cues)

**Mechanism:** Qwen3-TTS's Base model infers prosody from text semantics. The text IS the prompt. So to influence style, modify the text that reaches the engine.

**Approach -- text-cue injection:**

For dialogue segments, prepend a brief natural-language cue derived from scene mood:
- Input text: `"I can't believe you did that."`
- Scene mood: anger, HIGH intensity
- Injected text: `"Speaking with anger: I can't believe you did that."`

For narration segments, the cue is more subtle:
- Input text: `"The room fell silent."`
- Scene mood: fear, MEDIUM intensity
- Injected text: `"In a tense, fearful tone: The room fell silent."`

**Line overrides supersede scene mood** -- if a segment has a LineOverride, use the override's emotion instead of the scene mood.

**Key design decisions:**
- Cue format matters. Short, natural-language cues work best. Avoid XML-like tags.
- Cue should NOT appear in synthesized speech -- it primes the model's prosody but should not be verbalized. **This is the main risk.** If Qwen3-TTS speaks the cue text aloud, the feature is broken. Needs empirical testing with various cue formats.
- Fallback: If cues are spoken aloud, try parenthetical format `(angrily)` or bracket format `[angry]` which some models treat as stage directions.
- Nuclear fallback: If no cue format works silently, abandon text injection and rely solely on post-processing expansion (less expressive but reliable).

**Emotion-to-cue mapping:**

| EmotionCategory | Intensity LOW | Intensity MEDIUM | Intensity HIGH |
|-----------------|---------------|------------------|----------------|
| NEUTRAL | (no cue) | (no cue) | (no cue) |
| JOY | "With a hint of warmth:" | "Happily:" | "With great joy and excitement:" |
| SADNESS | "With a touch of melancholy:" | "Sadly:" | "With deep sorrow:" |
| ANGER | "With slight irritation:" | "Angrily:" | "With intense fury:" |
| FEAR | "With unease:" | "Fearfully:" | "In terror:" |
| SURPRISE | "With mild surprise:" | "In surprise:" | "In complete shock:" |
| DISGUST | "With distaste:" | "With disgust:" | "With revulsion:" |
| TENDERNESS | "Gently:" | "Tenderly:" | "With deep tenderness:" |

### 3. VoiceDesign-then-Clone Pipeline (Differentiator)

**Complexity:** HIGH
**Risk:** MEDIUM (proven workflow per official docs, but untested in this codebase)

**Confidence: MEDIUM** -- The workflow is officially documented by Qwen and verified by community guides. Memory feasibility on 16GB M4 is HIGH confidence (1.7B model fits in ~4GB via MLX bf16).

**Workflow:**
1. During voice prep phase (before synthesis), load VoiceDesign model
2. For each character, use `voice_profile.description` as the `instruct` parameter
3. Generate a 10-15s reference clip with styled voice matching the character description
4. Unload VoiceDesign model
5. Load Base model for synthesis
6. Clone from the VoiceDesign-generated reference clip (which now carries the character's style)

**Trade-off:** This replaces LibriTTS-P reference clips with VoiceDesign-generated clips. The cloned voice will sound like the VoiceDesign output, not like a real human from LibriTTS-P. This may reduce voice naturalness (real human recordings are typically more natural than synthesized references). But it gains style consistency -- every character sounds like their description says they should.

**Alternative hybrid approach:** Use LibriTTS-P clips for timbre (real human voice quality) and rely on text-cue injection for emotion. This preserves voice naturalness at the cost of less style control. **Recommend starting with text-cue injection (feature 2) and adding VoiceDesign pipeline only if text cues prove insufficient.**

### 4. Speech-Act Post-Processing Expansion

**Complexity:** LOW
**Risk:** LOW

Extend `SPEECH_ACT_PARAMS` to include emotion-mapped parameters. The existing pattern (volume_db + speed_factor per speech act) is proven. Add emotion-based adjustments that stack with speech-act adjustments:

| EmotionCategory | volume_db | speed_factor | Notes |
|-----------------|-----------|--------------|-------|
| NEUTRAL | 0.0 | 1.0 | No change |
| JOY | +1.0 | 1.03 | Slightly brighter, slightly faster |
| SADNESS | -1.5 | 0.95 | Slightly quieter, slightly slower |
| ANGER | +2.0 | 1.05 | Louder, faster |
| FEAR | -1.0 | 1.02 | Slightly quieter, slightly faster (breathless) |
| SURPRISE | +1.5 | 1.0 | Louder, same pace |
| DISGUST | 0.0 | 0.97 | Same volume, slightly slower |
| TENDERNESS | -2.0 | 0.95 | Quieter, slower |

**Intensity scaling:** LOW = 50% of values, MEDIUM = 100%, HIGH = 150%. Clamp to safe ranges.

**Stacking with speech acts:** Emotion adjustments apply first, speech-act adjustments apply second. A "shouted with anger" line gets anger boost (+2.0 dB, 1.05x speed) then shout boost (+4.5 dB, 1.08x speed) = +6.5 dB total, 1.13x speed. Clamp to prevent distortion.

### 5. Cached voice_clone_prompt

**Complexity:** LOW
**Risk:** LOW

Use mlx-audio's `create_voice_clone_prompt()` to pre-compute the voice embedding + prompt tokens once per character, then pass `voice_clone_prompt` to `generate_voice_clone()` for each segment. Currently the engine re-processes the reference audio for every single segment.

**Expected improvement:**
- Faster synthesis (skip ref audio processing per segment)
- More consistent voice (same prompt tokens every time)
- Lower memory churn (no repeated audio loading)

Store cached prompts in memory during the synthesis run (not to disk -- they are model-version-specific).

---

## MVP Recommendation

Prioritize in this order:

1. **Unified voice_profile** -- Pure refactor, unblocks everything, zero risk to synthesis quality
2. **Voice matching uses unified profile** -- Small change in trait_matcher and embedding_matcher
3. **Scene mood data flow to synthesizer** -- Pipe the data, even if conditioning mechanism is a no-op initially
4. **Text-cue injection for emotion** -- The primary mechanism. Must be empirically tested. Include a feature flag to disable if cues are spoken aloud.
5. **Line override conditioning** -- Same mechanism as scene mood, higher priority in cascade

**Defer:**
- **VoiceDesign pipeline:** High complexity, unclear value vs text-cue injection. Evaluate after text cues are tested.
- **Cached voice_clone_prompt:** Performance optimization. Do after functional features work.
- **Post-processing expansion:** Additive and low risk. Can be done anytime.

---

## Sources

- [Qwen3-TTS Official Repository](https://github.com/QwenLM/Qwen3-TTS) -- model variants, API, Base vs CustomVoice vs VoiceDesign (HIGH confidence)
- [Qwen3-TTS-12Hz-1.7B-Base HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) -- Base model API, no instruct support confirmed (HIGH confidence)
- [Qwen3-TTS-12Hz-1.7B-CustomVoice HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) -- CustomVoice API with instruct, 9 preset speakers only (HIGH confidence)
- [mlx-audio Qwen3-TTS README](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md) -- MLX API for all model variants (HIGH confidence)
- [mlx-community VoiceDesign bf16](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16) -- MLX-converted VoiceDesign model available (HIGH confidence)
- [Qwen3-TTS Voice Cloning Guide 2026](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) -- VoiceDesign-then-Clone workflow, accent instability warning (MEDIUM confidence)
- [Qwen3-TTS Complete Guide (DEV Community)](https://dev.to/czmilo/qwen3-tts-the-complete-2026-guide-to-open-source-voice-cloning-and-ai-speech-generation-1in6) -- ecosystem overview, model comparison (MEDIUM confidence)
- [Enhanced Prosody Modeling for Audiobook Synthesis (ACM 2025)](https://dl.acm.org/doi/10.1145/3749644) -- hierarchical prosody control patterns (MEDIUM confidence)
- [Controlling Emotion in TTS with Natural Language Prompts (Interspeech 2024)](https://arxiv.org/html/2406.06406v1) -- text-based emotion conditioning approaches (MEDIUM confidence)
- [Controllable Speech Synthesis Survey (2024)](https://arxiv.org/html/2412.06602v1) -- multi-scale prosody control taxonomy (MEDIUM confidence)
- [Qwen Blog: Qwen3-TTS Family](https://qwen.ai/blog?id=qwen3tts-0115) -- official capabilities description, text-semantic understanding (HIGH confidence)

---
*Feature research for: v1.2 voice expression milestone*
*Researched: 2026-03-06*
