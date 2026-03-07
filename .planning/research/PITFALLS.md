# Pitfalls Research: v1.2 Voice Expression

**Domain:** Adding voice style conditioning and emotion-to-prosody to existing TTS pipeline with data model migration
**Researched:** 2026-03-06
**Confidence:** HIGH -- Verified against actual mlx-audio source code in .venv, existing codebase models, Qwen3-TTS official documentation, and Hugging Face model cards. Data model pitfalls grounded in actual Pydantic schema inspection.

---

## Critical Pitfalls

### Pitfall 1: Base Model Cannot Accept Style Instructions -- Fundamental Architecture Mismatch

**What goes wrong:**
The project uses `Qwen3-TTS-12Hz-1.7B-Base` for voice cloning. The v1.2 milestone plans to "feed voice_profile description to Qwen3-TTS as style conditioning per character." But the Base model's generation path **does not accept an `instruct` parameter**. Verified in the installed mlx-audio source (`qwen3_tts.py` line 785-812): when `ref_audio` and `ref_text` are provided (voice cloning mode), the code routes to `_generate_icl()` which accepts only `text`, `ref_audio`, `ref_text`, `language`, `temperature`, `max_tokens`, `top_k`, `top_p`, `repetition_penalty`, and `verbose`. There is no style/instruct input.

Attempting to pass style descriptions to the Base model will either silently ignore them (if added as unused kwargs) or require switching to the CustomVoice model variant -- which does not support arbitrary voice cloning from reference audio, only 9 preset voices.

**Why it happens:**
The Qwen3-TTS family separates voice cloning (Base) from style control (CustomVoice/VoiceDesign) into different model variants with incompatible generation paths. The project's key decision "Speech-act post-processing over TTS instruct -- Base model ignores instruct prompts with cloned voices" already acknowledges this, but the v1.2 milestone description ("Feed voice_profile description to Qwen3-TTS as style conditioning") directly contradicts this constraint.

**How to avoid:**
Accept that style conditioning via text descriptions is NOT available on the Base model with voice cloning. The v1.2 approach must be one of:
1. **Post-processing only** (current approach, extended): Use the unified voice_profile data to improve voice matching and post-processing parameters, NOT to instruct the TTS engine directly.
2. **Model swap to CustomVoice**: Lose arbitrary voice cloning (only 9 preset voices) but gain `instruct` parameter for style control.
3. **Dual-model approach**: Use Base for cloning + CustomVoice for style-conditioned narration (doubles memory, complex orchestration).
4. **Fine-tune Base model**: Single-speaker fine-tuning is documented as supported, but requires training infrastructure and per-book effort.

Recommendation: Option 1 (post-processing extension) is the only viable path that preserves the existing voice cloning pipeline. Use voice_profile data upstream (better matching) and downstream (richer post-processing) but do not attempt to pass it into TTS generation.

**Warning signs:**
- Code that constructs a text prompt/instruct string from voice_profile data
- Changes to `qwen_engine.py` that add an `instruct` parameter to the `generate()` call
- TTS output that sounds identical regardless of voice_profile content (because instructions are silently ignored)
- Any plan requiring "the TTS engine to interpret emotional context"

**Phase to address:**
Phase 1 (architecture/design). This must be resolved before any implementation begins. The entire v1.2 feature design hinges on understanding this constraint.

---

### Pitfall 2: Data Model Merge Breaks Existing JSON Artifacts and Checkpoints

**What goes wrong:**
Merging `voice_qualities` + `voice_baseline` into a single `voice_profile` field changes the `CharacterProfile` schema. Every existing pipeline output depends on this schema:
- `characters.json` contains `voice_qualities` and optional `voice_baseline` fields
- `voice_map.json` was built from characters with the old schema
- Attribution cache (`.cache/`) stores raw LLM responses with the old field names
- The LLM prompt for character extraction produces `voice_qualities` in its structured output

Breaking the schema means:
1. Existing book directories cannot resume or re-run individual phases
2. The LLM structured output format must change (new JSON schema for Ollama)
3. All cached extraction results become invalid
4. Tests that validate model serialization break

**Why it happens:**
Pydantic models serve as both runtime objects AND serialization schemas AND LLM output formats in this project. A field rename propagates through the LLM prompt schema, JSON artifacts on disk, and runtime code simultaneously.

**How to avoid:**
1. **Add `voice_profile` as a NEW computed field** rather than removing the old fields. Use a `@model_validator` or `@computed_field` on `CharacterProfile` that constructs `voice_profile` from the existing `voice_qualities` + `voice_baseline` at load time. Old JSON files remain loadable.
2. **Write a one-time migration function** for existing `characters.json` files that populates the new field from old data and is called at the start of the matching phase.
3. **Keep the LLM schema unchanged**. The LLM still outputs `voice_qualities` + `voice_baseline`. The merge into `voice_profile` happens in Python after LLM extraction, not in the LLM prompt.
4. **Version the `characters.json` format**. Add a `schema_version` field so code can detect old-format files and auto-migrate.

**Warning signs:**
- `pydantic.ValidationError` on loading existing `characters.json`
- LLM extraction returning empty/malformed results after schema change
- Checkpoint validation failures on resume
- Tests passing locally but failing on CI with fixture data

**Phase to address:**
Phase 1 (data model migration). Do this FIRST, verify backward compatibility, then build features on top.

---

### Pitfall 3: Speech-Act Post-Processing Conflicts with New Emotion Conditioning

**What goes wrong:**
The v1.1 pipeline already applies post-processing adjustments based on speech-acts (whispered: -4.5 dB, shouted: +4.5 dB, thought: -3.0 dB). The v1.2 milestone adds scene mood and line-level emotion overrides. If both systems modify audio independently, they produce unpredictable results:
- A whispered line (-4.5 dB) in an angry scene (could add +3 dB) = net -1.5 dB -- neither whispered nor angry
- A shouted line (+4.5 dB, +8% speed) with a "fear" emotion override (could add speed decrease) = conflicting speed adjustments
- Volume adjustments stack multiplicatively with the mastering chain's compressor and limiter, creating non-obvious interactions

The current `post_processor.py` explicitly notes: "Adjustments are ABSOLUTE per speech-act type, NOT cumulative with scene mood (per user decision). Scene mood annotations are stored for future enrichment but do not modify audio in v1.1."

**Why it happens:**
Speech-acts and emotions operate on overlapping audio parameters (volume, speed). Without a clear priority model, adding emotion adjustments alongside existing speech-act adjustments creates a combinatorial explosion of edge cases.

**How to avoid:**
Define a strict priority hierarchy before implementing any emotion-to-audio mapping:
1. **Speech-act takes priority** for the parameters it controls (volume, speed). These are hard phonological markers -- a whisper is physically quiet regardless of emotion.
2. **Emotion adjusts only non-conflicting parameters** or adjusts WITHIN the speech-act's range. For example, emotion could modify pitch contour or add reverb effects, not override volume.
3. **Build a parameter resolution function** that takes `(speech_act, scene_mood, line_override)` and returns a single `AdjustmentParams` with resolved values, not three independent adjustments applied sequentially.
4. **Test the edge cases explicitly**: whispered+angry, shouted+fearful, thought+joyful. Listen to the output.

**Warning signs:**
- Two separate functions both modifying the same audio array for different reasons
- Volume or speed adjustments applied in sequence without awareness of each other
- Audio that sounds "compressed" or "flat" after mastering because pre-mastering dynamics were lost to conflicting adjustments
- The mastering limiter activating excessively (indicates clipping from stacked volume boosts)

**Phase to address:**
Phase 2 or 3 (when wiring emotion data into synthesis). Must be designed together with the speech-act system, not bolted on afterward.

---

### Pitfall 4: Voice Matching Quality Regression When Changing Input Data Shape

**What goes wrong:**
The `trait_matcher.py` builds character descriptions using `voice_qualities` fields (pitch, pace, tone, accent). The `embedding_matcher.py` likely uses similar trait text for embedding similarity. If v1.2 changes these fields to use `voice_profile` instead, the LLM prompts and embedding inputs change, which can subtly degrade matching quality:
- LLM prompt format changes alter the casting-director's reasoning patterns
- Embedding vectors from different input text produce different similarity scores
- A unified `voice_profile.description` field (free-text) is harder for the LLM to parse than structured fields like `pitch: "low"`, `pace: "slow"`

**Why it happens:**
Voice matching was tuned and validated with a specific input format. Changing the format changes the results even if the information content is the same.

**How to avoid:**
1. **Keep the structured fields available for matching**. Even if you merge into `voice_profile`, expose the structured sub-fields (pitch, pace, tone, accent, energy, typical_emotion) for the matching prompts. Use `voice_profile.description` for human readability, not for LLM consumption.
2. **A/B test matching quality**. Before committing the new data shape, run matching on 2-3 test books with both old and new input formats. Compare speaker assignments and confidence scores.
3. **Do not change `_build_character_description()` format unless matching improves**. The existing format works. Enhance it with additional data (energy, typical_emotion from voice_baseline), do not restructure it.

**Warning signs:**
- Average matching confidence drops after the change
- Characters getting assigned voices with wrong gender or wildly inappropriate traits
- The LLM returning invalid speaker_ids more frequently (hallucination from confusing prompt format)

**Phase to address:**
Phase 2 (after data model migration is stable). Test matching quality as a separate validation step.

---

### Pitfall 5: Emotion Data Not Reaching Synthesis Loop -- Silent Feature Gap

**What goes wrong:**
The synthesis loop (`synthesizer.py`) currently reads segments from `attributed.json` which contains `speech_act` per segment but NOT emotion data. Emotion data lives in a separate `emotion.json` file. The synthesis loop never loads `emotion.json`. Adding emotion conditioning requires:
1. Loading `emotion.json` alongside `attributed.json`
2. Building a lookup from segment_id to scene mood and line overrides
3. Passing this data through the generation loop to wherever it will be used
4. Handling the case where `emotion.json` does not exist (backward compat with v1.0/v1.1 books)

The pitfall is implementing the emotion-to-audio mapping in isolation (e.g., a new post-processing function) without wiring it into the synthesis loop. The feature "works in tests" but never fires in production because the data flow is incomplete.

**Why it happens:**
The emotion data and synthesis code were built in separate v1.1 phases. They share no runtime connection. The gap is easy to miss because both halves "work" independently.

**How to avoid:**
1. **Wire the data flow first, with no-op processing**. Load `emotion.json` in `run_synthesis()`, build the segment-to-mood lookup, pass mood data to the segment processing code, and log it. Verify the data reaches the right place before implementing any audio modifications.
2. **Add a CLI flag** like `--emotion` or `--expression` that controls whether emotion conditioning is applied. Default OFF initially so it can be tested independently.
3. **Handle missing emotion.json gracefully**. If the file does not exist (older book), default all moods to `NEUTRAL/LOW` and skip overrides. Do not crash.

**Warning signs:**
- Emotion post-processing function exists but is never called from `run_synthesis()`
- No logging output mentioning mood or emotion during synthesis runs
- Test coverage that mocks the data flow instead of testing the actual wiring
- Scene mood annotations generated but never consumed

**Phase to address:**
Phase 2 or 3 (synthesis integration). This is primarily a plumbing task, not an algorithm task.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep both `voice_qualities` AND `voice_profile` fields forever | Zero migration risk | Dual source of truth, confusion about which to use, LLM schema bloat | Acceptable for v1.2, but deprecate old fields with warnings by v1.3 |
| Hardcode emotion-to-audio parameter maps | Quick implementation, easy to tune | Every new emotion or speech-act requires code changes, combinatorial explosion | Acceptable for v1.2 (8 emotions x 4 speech-acts = 32 combinations is manageable) |
| Skip emotion data for narration segments | Simpler implementation (only dialogue gets emotion) | Narration conveys mood too; monotone narration in emotional scenes | Never -- narration is >50% of segments and scene mood applies to all segments |
| Use `emotion.json` as separate file forever | No schema changes to `attributed.json` | Two files to keep in sync, easy to have stale emotion data | Acceptable for v1.2 but consider embedding emotion in attributed.json for v1.3 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| voice_profile in LLM extraction | Changing the LLM output schema to produce `voice_profile` directly | Keep LLM producing `voice_qualities` + `voice_baseline` separately, merge in Python post-processing. LLMs produce better structured output with focused schemas. |
| Emotion data in synthesis | Loading emotion.json once at start, assuming segment IDs match | Segment IDs in emotion.json reference scene ranges, not individual segments. Build a proper `get_mood_for_segment(seg_id, emotion_data)` lookup that handles scene boundaries. |
| voice_profile in voice matching | Passing `voice_profile.description` as the sole input to trait matching | Use both structured fields (pitch, pace, tone, accent, energy) AND the free-text description. Structured fields give the LLM concrete comparison points; description gives context. |
| Checkpoint compatibility | Assuming existing checkpoints work after adding emotion conditioning | Checkpoints record per-segment completion but not which features were active. A segment synthesized without emotion conditioning should be re-synthesized when emotion is enabled. Add a features hash to checkpoint metadata. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading emotion.json per segment instead of once | Synthesis slows down linearly with book size | Load once into a dict at synthesis start, O(1) lookup per segment | Immediate (file I/O per segment adds ~10ms x 2000 segments = 20s overhead) |
| Recomputing voice_profile merge on every access | Wasted CPU on hot path | Cache the merged profile at CharacterProfile construction time | At scale with large casts (50+ characters) |
| Emotion parameter resolution involving LLM calls | Each segment takes 2-5s extra for LLM roundtrip | All emotion-to-audio mappings must be deterministic lookups, never LLM calls | Immediate (would make synthesis 10x slower) |
| Re-synthesizing all segments when enabling emotion | Hours of wasted synthesis time | Checkpoint tracks which features were active; only re-synth segments where emotion would actually change output (non-neutral mood or has line override) | Books with >1000 segments |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No way to preview emotion effect on a single segment | User must re-synthesize entire book to hear if emotion tuning sounds good | Add `--preview-segment N` flag that synthesizes one segment with and without emotion conditioning for A/B comparison |
| Emotion conditioning enabled by default immediately | Existing books that sounded fine now sound different on re-synthesis | Default emotion conditioning OFF, require explicit `--expression` flag. Let users opt in. |
| No indication of which segments have emotion overrides | User cannot find the emotion-affected segments in output | Log segment IDs that received non-neutral mood or line overrides during synthesis, print count in summary |
| voice_profile merge changes matching for existing books | Re-running match phase assigns different voices to characters | voice_map.json is only generated if it does not exist (current behavior). Do not auto-regenerate on re-run. |

## "Looks Done But Isn't" Checklist

- [ ] **voice_profile merge:** VoiceQualities and VoiceBaseline still work when loaded from old characters.json -- verify with actual v1.1 output files
- [ ] **Emotion wiring:** emotion.json data actually reaches the synthesis loop (not just loaded but used) -- add integration test that checks log output for mood data
- [ ] **Speech-act + emotion interaction:** All 32 combinations (8 emotions x 4 speech-acts) produce listenable audio -- spot-check at least the 4 extreme cases (whispered+anger, shouted+fear, thought+joy, spoken+neutral)
- [ ] **Checkpoint compat:** A v1.1 checkpoint.json loads and resumes correctly with v1.2 code -- test with actual checkpoint file
- [ ] **Voice matching stability:** Running match phase with new voice_profile produces same or better assignments as old format -- A/B test on at least 1 book
- [ ] **Missing emotion.json:** Synthesis completes without crash when emotion.json does not exist (v1.0/v1.1 books)
- [ ] **Narrator emotion:** Scene mood is applied to narration segments, not just dialogue -- verify narrator segments get mood data

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Style descriptions silently ignored by Base model | LOW | Remove the instruct code path, redirect effort to post-processing. No data loss, just wasted implementation time. |
| characters.json schema break | MEDIUM | Write a migration script that reads old format, adds voice_profile field, writes new format. Apply to all existing book directories. Test with `model_validate()`. |
| Stacked speech-act + emotion adjustments produce bad audio | LOW | Revert to speech-act-only adjustments (v1.1 behavior), redesign the priority model, re-implement. Only affects the post-processing code, not data. |
| Voice matching quality regression | MEDIUM | Revert `_build_character_description()` to old format, delete voice_map.json for affected books, re-run matching. Synthesis must be re-run for reassigned characters. |
| Emotion data never reaching synthesis | LOW | Pure plumbing fix. Add data loading and lookup in run_synthesis(), no algorithm changes needed. |
| Checkpoint incompatibility after feature change | HIGH | Must re-synthesize from scratch. Archive old wavs/ and checkpoint.json, start fresh. Hours of synthesis time lost per book. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Base model cannot accept style instructions | Phase 1 (Design) | Architecture document explicitly states post-processing-only approach; no instruct parameter in engine API |
| Data model merge breaks artifacts | Phase 1 (Data Model) | Load a v1.1 characters.json with v1.2 code; all fields validate; voice_profile computed correctly |
| Speech-act + emotion conflict | Phase 2 (Emotion Integration) | Parameter resolution function returns single AdjustmentParams; edge-case audio samples reviewed |
| Voice matching quality regression | Phase 2 (Matching Enhancement) | A/B comparison of matching results with old vs new input format on test book |
| Emotion data not reaching synthesis | Phase 2 or 3 (Synthesis Wiring) | Log output confirms mood data loaded and applied; integration test verifies data flow |
| Checkpoint incompatibility | Phase 1 (Data Model) | Resume synthesis on a v1.1 book directory with v1.2 code; no crash, correct behavior |

## Sources

- Qwen3-TTS Base model card: [Hugging Face](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base)
- Qwen3-TTS GitHub repository: [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)
- mlx-audio installed source code: `.venv/lib/python3.11/site-packages/mlx_audio/tts/models/qwen3_tts/qwen3_tts.py` (lines 687-812) -- verified Base model `generate()` routing and `_generate_icl()` parameter list
- Existing codebase: `src/attribution/models.py`, `src/synthesis/synthesizer.py`, `src/synthesis/qwen_engine.py`, `src/synthesis/post_processor.py`, `src/matching/trait_matcher.py`
- FlexiVoice paper on Style-Timbre-Content conflict: [arxiv.org/html/2601.04656v1](https://arxiv.org/html/2601.04656v1)
- Pydantic backward compatibility patterns: [roman.pt/posts/pydantic-as-backward-compatibility-layer](https://roman.pt/posts/pydantic-as-backward-compatibility-layer/)
- F5-TTS-Emotional-CFG research on emotion conditioning conflicts: [GitHub](https://github.com/RaduBolbo/F5-TTS-Emotional-CFG)

---
*Pitfalls research for: v1.2 Voice Expression milestone*
*Researched: 2026-03-06*
