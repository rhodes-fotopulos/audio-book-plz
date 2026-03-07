# Phase 12: Emotion Removal and LLM Optimization - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Remove the emotion annotation system (scene moods + line overrides) from the attribution pipeline. Make speech-act post-processing opt-in via flag (default OFF). Add trait matching cache. This phase reduces LLM calls per chapter from 5 to 2-3 and simplifies the pipeline.

**Scope change from original Phase 12:** The original "Expression System Core" (three-layer expression resolver, parameter tables, precedence rules) is replaced by emotion removal after research confirmed that Qwen3-TTS Base model cannot combine voice cloning with emotion instructions. Post-processing volume/speed/pitch fights the model's natural prosody and the LUFS normalization in the mastering chain undoes volume deltas anyway.

</domain>

<decisions>
## Implementation Decisions

### Emotion system removal
- Delete `src/attribution/emotion/` directory entirely (scene_mood.py, overrides.py, models.py, __init__.py)
- Remove emotion annotation block from `src/pipeline.py` (lines 223-306): scene mood LLM calls, line override LLM calls, emotion.json writing, failure reporting
- Remove `from src.attribution.emotion import annotate_scene_moods, detect_overrides` from pipeline.py
- Remove emotion.json output — no longer produced by the attribution phase
- Remove any references to emotion.json in CLI, docs, or other modules
- Existing emotion.json files in output directories are simply ignored (no cleanup needed)
- Delete `tests/test_emotion.py`

### Speech-act post-processing flag
- Add `--speech-act-fx` CLI flag to enable speech-act post-processing (volume/speed adjustments for whispered/shouted/thought)
- Default: OFF — the TTS engine's natural prosody is trusted; LUFS normalization undoes most volume deltas anyway
- When OFF: speech-act tags still present in attributed.json (tagging is cheap), but no audio modification in synthesis
- Keep `src/synthesis/post_processor.py` — code stays, just gated behind the flag
- Keep `src/attribution/speech_acts.py` — regex+LLM tagging still runs (tags are useful metadata)

### Speech-act LLM refinement flag
- Make the speech-act LLM pass optional — add flag or config to skip LLM refinement and use regex-only classification
- Default: regex-only (skip LLM). Since post-processing is off by default, the precision gain from LLM refinement is marginal
- Regex catches explicit narration tags ("she whispered") at 0.9 confidence — covers the clear cases
- Saves 0-1 LLM calls per chapter for ambiguous segments

### Trait matching cache
- Cache trait_matcher LLM results based on character profile hash
- Re-running `match` on the same book with unchanged characters skips LLM casting calls
- Saves N LLM calls on re-runs (N = number of major characters)

### v1.2 milestone restructure
- Collapse remaining phases from 5 (11-15) to 3 (11-13)
- Phase 11: Data Model Unification (COMPLETE)
- Phase 12: Emotion Removal and LLM Optimization (THIS PHASE)
- Phase 13: Synthesis Performance (reference caching + batch-by-character, formerly Phase 14)
- Drop original Phase 13 (Synthesis Wiring — no emotion data to wire)
- Drop original Phase 15 (Text-cue injection doesn't work with Base model; A/B preview has less value without expression)
- Update ROADMAP.md and REQUIREMENTS.md to reflect restructure

### Claude's Discretion
- Exact implementation of speech-act LLM skip (flag vs config vs removing the LLM code path)
- Cache key format for trait matching (character profile hash strategy)
- How to handle the `--expression` flag references in REQUIREMENTS.md (SYNTH-04) — may need to be repurposed or removed
- Whether to update pipeline.py phase comments/docstrings to reflect removed emotion phase

</decisions>

<code_context>
## Existing Code Insights

### Files to Delete
- `src/attribution/emotion/__init__.py`: Exports annotate_scene_moods, detect_overrides
- `src/attribution/emotion/models.py`: EmotionCategory, MoodIntensity, SceneMood, LineOverride, EmotionAnnotation
- `src/attribution/emotion/scene_mood.py`: Scene boundary detection + LLM mood annotation
- `src/attribution/emotion/overrides.py`: LLM line-level override detection
- `tests/test_emotion.py`: Tests for emotion models and annotation

### Files to Modify
- `src/pipeline.py` (lines 34, 223-306): Remove emotion imports and annotation block
- `src/synthesis/synthesizer.py` (lines 294-303, 358-370, 480-490): Gate speech-act post-processing behind flag
- `src/synthesis/post_processor.py`: No changes needed (stays, just gated)
- `src/attribution/speech_acts.py` (line 304): Make LLM pass optional
- `src/matching/trait_matcher.py`: Add caching for LLM casting results
- `src/cli.py`: Add --speech-act-fx flag, update help text

### Established Patterns
- Pydantic BaseModel with ConfigDict(strict=True) for all value objects
- LLM call caching via `src/attribution/cache.py` (check_cache/write_cache/get_cache_key) — reuse for trait matching
- Pipeline phases use Rich progress bars and print colored summaries
- Feature flags passed through SynthesisConfig or as CLI arguments

### Integration Points
- `src/attribution/__init__.py`: May export emotion-related symbols — needs cleanup
- `src/cli.py`: CLI flag definitions and pipeline invocation
- `src/synthesis/models.py`: SynthesisConfig may need new flag field for speech-act-fx

</code_context>

<specifics>
## Specific Ideas

- Research confirmed Qwen3-TTS Base model cannot combine voice cloning with emotion/style instructions — this is an architectural limitation, not a bug
- CustomVoice model supports emotions but only has 2 English voices (both male) — insufficient for novel casts
- VoiceDesign model supports unlimited voices + emotions but has per-generation variability (voice drift) — makes characters indistinguishable
- The user's priority is distinct character voices over emotional expression
- The TTS engine already reads text semantically and produces natural prosody — post-processing fights this
- LUFS normalization (-19.0 target) in the mastering chain undoes most volume-based expression adjustments

</specifics>

<deferred>
## Deferred Ideas

- CustomVoice model integration as an alternative engine mode (blocked by only 2 English voices — revisit if Qwen expands preset library)
- VoiceDesign model for unlimited voices with emotion (blocked by per-generation voice inconsistency — revisit if deterministic generation is added)
- Text-cue injection (prepending emotion cues to text before TTS) — doesn't work with Base model (cues get spoken aloud)
- Re-evaluate emotion expression if a future TTS model supports voice cloning + emotion instructions simultaneously

</deferred>

---

*Phase: 12-expression-system-core*
*Context gathered: 2026-03-06*
