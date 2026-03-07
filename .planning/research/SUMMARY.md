# Project Research Summary

**Project:** audio-book-plz v1.2 Voice Expression
**Domain:** Expressive TTS conditioning for EPUB-to-audiobook pipeline
**Researched:** 2026-03-06
**Confidence:** MEDIUM

## Executive Summary

The v1.2 milestone aims to make the audiobook pipeline emotionally expressive by wiring the rich emotion data already extracted in v1.1 (scene moods, line overrides, voice baselines) into the TTS synthesis phase. The central finding across all four research tracks is that **Qwen3-TTS Base model cannot combine voice cloning with style instructions** -- these are mutually exclusive capabilities split across different model variants. Since voice cloning from LibriTTS-R speakers is the project's core value proposition, style/emotion control must happen entirely through audio post-processing, not TTS model instructions. This is not a limitation to work around later; it is the defining architectural constraint for all v1.2 work.

The recommended approach is a three-layer post-processing expression system: character voice baseline (constant per character, derived from a unified VoiceProfile), scene mood (per scene, from existing emotion.json), and line-level overrides (sparse, for high-contrast moments). All three layers resolve to concrete audio parameters (volume, speed, pitch shift) applied after TTS generation using existing libraries (numpy, pedalboard). Zero new dependencies are needed. The data model must first be cleaned up by merging the duplicated VoiceQualities and VoiceBaseline into a single VoiceProfile, with backward-compatible migration for existing JSON artifacts.

The primary risks are: (1) the data model merge breaking existing pipeline artifacts if not handled with backward compatibility, (2) speech-act and emotion post-processing conflicting when stacked without a clear priority model, and (3) emotion data never actually reaching the synthesis loop due to the disconnect between the attribution phase (which produces emotion.json) and the synthesis phase (which never loads it). All three are preventable with careful implementation ordering -- data model first, expression resolver second, synthesis wiring last.

## Key Findings

### Recommended Stack

No new dependencies are required. The entire v1.2 feature set builds on existing libraries. This is a significant finding -- it means zero installation risk and no memory budget changes.

**Core technologies (all existing, unchanged):**
- **Qwen3-TTS 1.7B Base via mlx-audio** -- TTS engine stays on Base model for voice cloning. No model switch.
- **pedalboard PitchShift** -- adds pitch shifting as a third post-processing dimension alongside volume and speed. Already installed at >=0.9.22.
- **Pydantic** -- VoiceProfile data model unification. Pure schema refactor using existing library.
- **numpy** -- audio signal processing for speed/volume adjustments. Already the backbone of post_processor.py.

**What NOT to add:** CustomVoice model (loses voice cloning), VoiceDesign model (loses real human voices), librosa (heavy deps for what numpy handles), any separate emotion NLP model (LLM already does this).

### Expected Features

**Must have (table stakes):**
- **Unified VoiceProfile** -- merge duplicated VoiceQualities + VoiceBaseline into one model. Prerequisite for everything else.
- **Voice matching uses unified profile** -- trait_matcher and embedding_matcher consume the richer unified data.
- **Scene mood influences synthesis** -- the emotion data extracted in v1.1 must actually affect audio output. Without this, v1.2 delivers nothing perceptible.
- **Line-level emotion overrides influence synthesis** -- high-contrast moments (laughing at a funeral) sound different from the scene's default mood.

**Should have (differentiators):**
- **Emotion-to-post-processing expansion** -- extend volume/speed with pitch shifting, intensity scaling, and emotion-category deltas. Low risk, additive.
- **Text-cue injection** -- prepend natural-language emotion cues to segment text to leverage Qwen3-TTS's text-semantic prosody. Effectiveness uncertain; needs empirical testing with a feature flag.
- **Cached voice_clone_prompt per character** -- performance optimization eliminating redundant reference audio processing.

**Defer (v2+):**
- **VoiceDesign-then-Clone pipeline** -- generate styled reference clips per character using VoiceDesign model. High complexity, unclear value vs simpler approaches. Evaluate only if text cues and post-processing prove insufficient.
- **Per-word emphasis marking** -- no mechanism in Base model for word-level control.
- **Emotion interpolation between scenes** -- over-engineering; scene breaks are natural transition points in audiobooks.

### Architecture Approach

The existing six-phase sequential pipeline remains unchanged. The key architectural addition is a new `expression.py` module that resolves three emotion layers (character baseline, scene mood, line override) into a single `ExpressionParams` dataclass consumed by the extended post-processor. The synthesis loop gains two new data inputs (emotion.json, characters.json) but the TTS engine API is untouched. All expression is applied as audio post-processing after generation.

**Major components:**
1. **VoiceProfile model** (`models.py` MODIFY) -- unified voice description replacing two overlapping models
2. **Expression resolver** (`expression.py` NEW) -- resolves three emotion layers into concrete audio parameters with clear precedence rules
3. **Extended post-processor** (`post_processor.py` EXTEND) -- applies volume, speed, and pitch adjustments driven by ExpressionParams
4. **Synthesis wiring** (`synthesizer.py` MODIFY) -- loads emotion.json + characters.json, builds lookups, calls expression resolver per segment

### Critical Pitfalls

1. **Base model cannot accept style instructions** -- do not add an `instruct` parameter to the TTS engine. All expression is post-processing. Any code that constructs style prompts for the Base model is wasted effort.
2. **Data model merge breaks existing artifacts** -- add VoiceProfile as a computed field with migration from old schema. Keep LLM extraction producing the old fields; merge happens in Python. Version the characters.json format.
3. **Speech-act and emotion post-processing conflict** -- define a strict resolution function that returns a single set of parameters, not sequential independent adjustments. Line override replaces scene mood (not additive). Clamp combined values to safe ranges.
4. **Voice matching quality regression** -- keep structured fields for matching prompts; do not rely solely on free-text description. A/B test matching results before and after the change.
5. **Emotion data never reaching synthesis** -- wire the data flow first with no-op processing and logging. Verify data reaches the right place before implementing audio modifications.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Data Model Unification and Migration

**Rationale:** Every downstream feature depends on the unified VoiceProfile schema. This is a pure refactor with zero TTS changes -- lowest risk, highest unblocking value.
**Delivers:** Single VoiceProfile model replacing VoiceQualities + VoiceBaseline. Backward-compatible migration for existing characters.json. Updated LLM extraction post-processing (LLM schema stays the same; merge happens in Python).
**Addresses:** Unified voice_profile (table stakes), voice matching enhancement
**Avoids:** Pitfall 2 (data model breaks artifacts), Pitfall 4 (matching regression)

### Phase 2: Expression System Core

**Rationale:** The expression resolver must exist before the post-processor can be extended or the synthesizer can be wired. This phase creates the central abstraction that all emotion conditioning flows through.
**Delivers:** `expression.py` with ExpressionParams dataclass and `resolve_expression()` function. MOOD_PARAMS, INTENSITY_MULTIPLIER, and PACE_MAP lookup tables. Unit tests covering all layer combinations and edge cases.
**Addresses:** Three-layer TTS conditioning stack (differentiator)
**Avoids:** Pitfall 3 (speech-act + emotion conflict) by designing the resolution function with clear precedence from the start

### Phase 3: Post-Processing Extension and Synthesis Wiring

**Rationale:** With the data model stable and expression resolver ready, this phase connects everything: loads emotion.json in the synthesis loop, resolves expression per segment, applies audio adjustments including pitch shifting. This is the integration phase where the feature becomes audible.
**Delivers:** Extended `apply_expression()` in post_processor.py with pitch shifting via pedalboard. Synthesis loop loads emotion.json + characters.json, builds segment lookups, calls expression resolver. Feature flag (`--expression`) for opt-in. Graceful fallback when emotion.json is missing.
**Addresses:** Scene mood influences synthesis (table stakes), line-level overrides (table stakes), emotion-to-post-processing expansion (differentiator)
**Avoids:** Pitfall 5 (emotion data not reaching synthesis) by wiring data flow first with logging before audio modifications

### Phase 4: Text-Cue Injection (Experimental)

**Rationale:** This is the highest-uncertainty feature. Prepending emotion cues to segment text may improve prosody, or the model may speak the cues aloud. Must be tested empirically with multiple cue formats. Depends on all prior phases being stable.
**Delivers:** Emotion-to-text-cue injection with configurable cue format. Feature flag to enable/disable. A/B comparison tooling for evaluating effectiveness.
**Addresses:** Emotion-to-text-cue injection (differentiator)
**Avoids:** N/A -- this phase IS the risk. Failure mode is well-defined (cues spoken aloud = disable feature).

### Phase 5: Performance and Polish

**Rationale:** Optimization and UX improvements after core features are working. Includes cached voice_clone_prompt (faster synthesis), preview tooling, and checkpoint compatibility verification.
**Delivers:** Cached voice_clone_prompt per character. `--preview-segment N` flag for A/B comparison. Logging of emotion-affected segments. Checkpoint metadata with feature hash.
**Addresses:** Cached voice_clone_prompt (differentiator), UX pitfalls
**Avoids:** Performance traps (loading emotion.json per segment, recomputing profiles)

### Phase Ordering Rationale

- **Data model before everything** because VoiceProfile schema changes propagate through matching, extraction, and synthesis. Getting this wrong poisons all downstream work.
- **Expression resolver before post-processor** because ExpressionParams defines the contract between emotion data and audio processing. The post-processor must consume a well-defined input.
- **Synthesis wiring after post-processor** because the synthesizer is the integration point -- both the resolver and post-processor must be ready.
- **Text-cue injection is isolated** because it has the highest uncertainty and can be added or removed without affecting the post-processing approach.
- **Performance last** because optimization before correctness is premature. Cached voice_clone_prompt is valuable but not blocking any feature.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Synthesis Wiring):** The emotion.json structure (scene ranges, segment ID mapping) needs careful inspection during implementation. The lookup from segment_id to scene mood involves range queries, not direct ID matching.
- **Phase 4 (Text-Cue Injection):** Entirely empirical. No documentation on how Qwen3-TTS Base responds to prepended cue text. Multiple cue formats must be tested. Consider building a small test harness before committing to an approach.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Data Model):** Well-understood Pydantic migration pattern. Backward compatibility approach is clearly documented.
- **Phase 2 (Expression System):** Pure Python data resolution logic. No external dependencies or API uncertainty.
- **Phase 5 (Performance):** mlx-audio's `create_voice_clone_prompt()` API is documented. Standard caching pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new deps. Base model limitation verified via official HuggingFace docs, technical report, and installed source code. |
| Features | MEDIUM | Table stakes are clear. Text-cue injection effectiveness is unverified. VoiceDesign pipeline deferred due to complexity uncertainty. |
| Architecture | MEDIUM-HIGH | Data flow and component boundaries are well-defined. Post-processing approach is proven by existing speech-act system. Expression resolution logic is straightforward. |
| Pitfalls | HIGH | Grounded in actual codebase inspection and verified API limitations. Recovery strategies identified for each pitfall. |

**Overall confidence:** MEDIUM -- the architecture and stack are solid, but the core question of "how expressive can post-processing make the output?" requires empirical validation. The post-processing approach is the right one given the constraints, but the magnitude of perceptible improvement is unknown until implemented and listened to.

### Gaps to Address

- **Post-processing expressiveness ceiling:** How much emotion can volume/speed/pitch adjustments actually convey? The parameter values in EMOTION_DELTAS and MOOD_PARAMS are educated guesses that need tuning against real audiobook output. Plan for an iterative tuning cycle in Phase 3.
- **Text-cue injection viability:** Will Qwen3-TTS Base speak the cue text aloud, ignore it, or use it for prosody? This is a binary unknown that determines whether Phase 4 delivers value or gets disabled. Test early with a simple prototype.
- **Optimal emotion delta values:** STACK.md and FEATURES.md propose slightly different parameter values for the same emotions. These need empirical calibration. Neither set is validated.
- **Checkpoint re-synthesis scope:** When emotion conditioning is enabled for a book previously synthesized without it, which segments need re-synthesis? A naive approach re-synthesizes everything; a smart approach only re-synthesizes segments with non-neutral mood or line overrides.

## Sources

### Primary (HIGH confidence)
- [Qwen3-TTS Technical Report](https://arxiv.org/html/2601.15621v1) -- Base model capabilities and limitations
- [Qwen3-TTS-12Hz-1.7B-Base HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) -- API surface, no instruct support
- [Qwen3-TTS-12Hz-1.7B-CustomVoice HuggingFace](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) -- 9 preset speakers only
- [Qwen3-TTS GitHub](https://github.com/QwenLM/Qwen3-TTS) -- official model comparison
- [pedalboard docs](https://spotify.github.io/pedalboard/) -- PitchShift API verified
- [mlx-audio GitHub](https://github.com/Blaizzy/mlx-audio) -- generate API surface
- Installed mlx-audio source code (`qwen3_tts.py` lines 687-812) -- verified Base model routing

### Secondary (MEDIUM confidence)
- [GitHub Discussion #231](https://github.com/QwenLM/Qwen3-TTS/discussions/231) -- community confirms Base ignores instruct
- [Qwen3-TTS Voice Cloning Guide 2026](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) -- VoiceDesign-then-Clone workflow
- [Enhanced Prosody Modeling for Audiobook Synthesis (ACM 2025)](https://dl.acm.org/doi/10.1145/3749644) -- hierarchical prosody patterns
- [Controlling Emotion in TTS with NL Prompts (Interspeech 2024)](https://arxiv.org/html/2406.06406v1) -- text-based emotion approaches
- [FlexiVoice paper](https://arxiv.org/html/2601.04656v1) -- Style-Timbre-Content conflict research
- [Pydantic backward compatibility patterns](https://roman.pt/posts/pydantic-as-backward-compatibility-layer/)

### Tertiary (LOW confidence)
- Pitch shift quality at sub-semitone levels via pedalboard -- needs empirical testing
- Base model responsiveness to punctuation/word-choice prosody cues -- needs A/B testing
- Optimal EMOTION_DELTAS parameter values -- need tuning against real output

---
*Research completed: 2026-03-06*
*Ready for roadmap: yes*
