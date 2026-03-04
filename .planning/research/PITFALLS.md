# Pitfalls Research: v1.1 Pipeline Quality Improvements

**Domain:** Adding 9 features to existing EPUB-to-audiobook pipeline (TTS swap, emotion, post-processing, consistency)
**Researched:** 2026-03-04
**Confidence:** MEDIUM-HIGH -- MLX memory and Qwen3-TTS pitfalls verified via GitHub issues, official docs, and community reports. Post-processing and consistency pitfalls draw from audio engineering best practices and TTS research. Emotion system pitfalls synthesized from Dopamine Audiobook paper and community experience.

---

## Critical Pitfalls

### Pitfall 1: MLX Metal Cache Accumulation Kills Overnight Runs

**What goes wrong:**
MLX's Metal backend does not release GPU buffer memory automatically between inference runs. Instead, it caches buffers for reuse. During long audiobook synthesis (hundreds or thousands of segments), this cache grows monotonically until the system hits the 16GB unified memory ceiling. Unlike Chatterbox's PyTorch/MPS where `torch.mps.empty_cache()` and `gc.collect()` are well-understood, MLX requires calling `mx.metal.clear_cache()` -- a different API entirely. If the existing `cleanup_memory()` method in `TTSEngine` continues calling `torch.mps.empty_cache()` after the swap to MLX, memory will never be freed.

**Why it happens:**
The current `TTSEngine.cleanup_memory()` method is tightly coupled to PyTorch's memory API (`torch.mps.empty_cache()`). Developers performing the TTS swap will focus on getting generation working and forget to update the memory cleanup path. MLX's lazy evaluation compounds the problem -- memory pressure builds silently because allocations accumulate as cached buffers, and `get_cache_memory()` must be called explicitly to even notice the issue.

**How to avoid:**
- Replace `torch.mps.empty_cache()` with `mx.metal.clear_cache()` in the cleanup method on day one of the TTS swap
- Call `mx.metal.clear_cache()` every N segments (start with `cleanup_interval=10`, tune from there)
- Add a memory pressure check: `mx.metal.get_active_memory() + mx.metal.get_cache_memory()` -- if it exceeds ~12GB (leaving 4GB for macOS), force a clear and log a warning
- Consider `mx.metal.set_cache_limit(bytes)` to cap the buffer cache (e.g., 4GB) so it self-evicts
- Test with a full chapter (50+ segments) before running a full book

**Warning signs:**
- System memory pressure goes yellow/red in Activity Monitor during synthesis
- Generation speed slows progressively over time (swap thrashing)
- macOS becomes unresponsive during long runs
- Segment generation time increases from ~3s to 10s+ over the course of a chapter

**Phase to address:**
TTS Engine Swap phase -- the very first phase, since all subsequent features depend on stable MLX operation.

---

### Pitfall 2: Qwen3-TTS Reference Audio Sweet Spot Is 10-15s, NOT 20-30s

**What goes wrong:**
The v1.1 plan calls for increasing voice reference clips from 10s to 20-30s, assuming "more reference audio = better cloning." In reality, Qwen3-TTS quality peaks at 10-15 seconds and actively degrades beyond that. Clips longer than ~15 seconds cause: (1) generation hangs/infinite loops, (2) the model gets "confused" by the longer context it was not trained to handle, and (3) increased memory consumption from longer audio embeddings without quality improvement.

**Why it happens:**
Chatterbox and Qwen3-TTS have fundamentally different architectures. Chatterbox may have benefited from longer references, leading to the assumption that the same applies to Qwen3-TTS. The Qwen3-TTS documentation states "3-second voice cloning" as a feature, meaning the model was optimized for short references. The community has confirmed that "quality scales roughly linearly from 3 to 15 seconds, then plateaus and eventually degrades."

**How to avoid:**
- Target 10-15s reference clips, not 20-30s
- Keep the existing `_MIN_CLIP_BYTES` threshold in `clip_selector.py` but add a MAX: approximately 15s = ~720KB at 24kHz/16-bit/mono
- When selecting clips, prefer the clip closest to 12-15s rather than the longest available
- Provide the transcript of the reference audio alongside the WAV file -- community testing shows speaker similarity scores jump from ~0.75 to ~0.89 when including the text
- Add SNR filtering: Qwen3-TTS docs recommend "valid speech should occupy at least 60% of total audio duration" with pauses no longer than 2 seconds

**Warning signs:**
- TTS generation hanging on certain characters (infinite loop on long reference)
- Voice quality worse for characters with longer reference clips
- Inconsistent voice timbre across segments for the same character

**Phase to address:**
Voice Reference Selection phase -- must be updated before TTS synthesis runs.

---

### Pitfall 3: Breaking the Working Pipeline During TTS Engine Swap

**What goes wrong:**
Swapping Chatterbox for Qwen3-TTS touches every layer of the synthesis pipeline: model loading, generation API, WAV output format, sample rate, memory management, error handling, and checkpoint compatibility. If all changes are made simultaneously, there is no working fallback. Old checkpoints (which reference Chatterbox-specific state) become invalid. The `SynthesisConfig` fields (`narration_exaggeration`, `dialogue_exaggeration`, `cfg_weight`) are Chatterbox-specific and meaningless for Qwen3-TTS, which uses natural language emotion prompts instead.

**Why it happens:**
The temptation is to do a "clean swap" -- rip out Chatterbox, drop in Qwen3-TTS. But the integration surface is much larger than just the `TTSEngine` class. The `synthesizer.py` module references Chatterbox-specific parameters, the checkpoint format stores Chatterbox-era metadata, and tests (if any) are Chatterbox-specific.

**How to avoid:**
- Create a `TTSEngineBase` abstract class (or Protocol) that both Chatterbox and Qwen3-TTS implement
- Implement Qwen3-TTS engine as a new class alongside the existing one, gated by a config flag (e.g., `engine: "chatterbox" | "qwen3-tts"`)
- Keep Chatterbox working until Qwen3-TTS passes the same test cases (A/B comparison on 5-10 segments)
- Migrate `SynthesisConfig` to use engine-neutral parameters:
  - `exaggeration` (float) -> `emotion_prompt` (str) for Qwen3-TTS
  - `cfg_weight` -> not applicable for Qwen3-TTS (remove or ignore)
- Add a checkpoint version field so old checkpoints are recognized as Chatterbox-era and either migrated or invalidated gracefully
- Sample rate may change (Chatterbox 24kHz vs Qwen3-TTS potentially different) -- the normalizer and concatenator must handle this

**Warning signs:**
- `python main.py convert` fails where it used to succeed
- Old checkpoints cause crashes instead of graceful re-synthesis
- Test segments sound wrong but pipeline reports success

**Phase to address:**
TTS Engine Swap phase -- must be the first phase, with explicit rollback capability.

---

### Pitfall 4: Ollama 14B Model Causes Swap Thrashing on 16GB Mac

**What goes wrong:**
The v1.1 plan considers upgrading from `qwen3:8b` Q4_K_M to `qwen3:14b` Q4_K_M or `qwen3:8b` Q8_0. On a 16GB M4 Mac, `qwen3:14b` at Q4_K_M requires ~10GB for weights alone, plus 2GB+ for KV cache at 32K context, totaling ~12GB. With macOS overhead of 4-6GB, this pushes into swap territory. The sequential pipeline design (LLM then TTS, not simultaneously) helps, but Ollama's lazy unloading means the model may still be resident when TTS tries to load.

**Why it happens:**
Developers test the 14B model in isolation (Ollama CLI) where it fits, but forget the system overhead from macOS, background processes, and the memory that will be needed when TTS loads later. Even with explicit `unload_model()`, Ollama may not release memory immediately. The `qwen3:8b` Q8_0 option (same parameter count, higher precision) is ~8GB, which is more manageable but still tight.

**How to avoid:**
- Stick with `qwen3:8b` but upgrade quantization: Q8_0 (~8GB) gives noticeably better quality than Q4_K_M (~4.5GB) without risking swap
- If testing 14B, reduce `num_ctx` from 32768 to 8192 or 16384 to shrink KV cache
- Add memory monitoring before TTS phase: check available memory, warn if less than 6GB free after Ollama unload
- Verify Ollama unload actually freed memory (current code does `keep_alive=0` but does not verify) -- add a sleep(2) + memory check after unload
- The existing `ensure_ollama_unloaded()` in `tts_engine.py` is good but needs enhancement: verify memory actually dropped

**Warning signs:**
- Attribution phase completes but system is sluggish
- Memory Pressure indicator is yellow/red after attribution
- TTS synthesis is much slower than expected (swap thrashing)
- Ollama logs show model being evicted mid-inference

**Phase to address:**
LLM Upgrade phase -- test memory profile before committing to 14B.

---

### Pitfall 5: Emotion System Creates "Emotional Whiplash" Between Segments

**What goes wrong:**
The three-layer emotion system (character baseline + scene mood + line-level overrides) can produce jarring tonal shifts between adjacent segments. Example: a tense scene has line-level override "whispered, frightened" for dialogue, followed immediately by narrator text with only the scene mood "tense" -- the narrator suddenly sounds dramatically different from the character even though they are in the same moment. Or worse: a character has baseline "gruff, stoic" but a line override says "sobbing, heartbroken" -- the voice timbre shifts so drastically it sounds like a different person.

**Why it happens:**
The three-layer system is designed for granularity, but human audiobook narrators modulate emotion gradually. They do not snap between emotional states. The system as designed computes a final emotion prompt per segment independently without considering what the adjacent segments sound like. Research from the Dopamine Audiobook paper explicitly identifies this: TTS models "tend to produce an 'averaged emotion' instead of accurately capturing the difference," and the solution requires emotion-level sub-sentence awareness.

**How to avoid:**
- Use the "intensity dial" pattern: define emotion intensity as a float (0.0 to 1.0), not binary presence/absence. Scene mood at 0.3 intensity is a gentle coloring, not a dramatic shift
- Implement emotion smoothing: the final emotion prompt for segment N should consider segments N-1 and N+1 (a 3-segment sliding window)
- Limit line-level overrides to a curated set of modifiers that DO NOT contradict character baseline: "slightly louder," "more urgent," "softened" -- not complete personality changes
- Cap emotional contrast: if the emotion distance between adjacent segments exceeds a threshold, dampen the override
- Start with scene-level only: do not implement line-level overrides in the first iteration. Add them only after scene-level proves stable
- Narration segments should be emotionally neutral or very lightly colored -- they are the anchor

**Warning signs:**
- Listening to chapter audio reveals jarring tonal shifts between adjacent segments
- The same character sounds like different people in consecutive lines
- Narrator voice changes dramatically at dialogue/narration boundaries
- Generated audio sounds worse than the v1.0 (no emotion) version

**Phase to address:**
Emotion System phase -- and only after TTS engine swap is stable. Build incrementally: scene mood first, then line overrides in a later iteration.

---

### Pitfall 6: Consistency Pass Creates Infinite Regeneration Loops

**What goes wrong:**
The voice consistency pass compares speaker embeddings of generated segments against a reference embedding. If a segment's cosine similarity falls below a threshold, it gets regenerated. But TTS generation is non-deterministic -- regenerating the same text with the same reference audio produces a different voice timbre each time. If the threshold is set too tight, legitimate segments get flagged, regenerated, and the new version may also fail the check. This creates a loop: flag -> regenerate -> flag -> regenerate, potentially forever.

**Why it happens:**
The natural variance of TTS generation is larger than developers expect. Community testing of Qwen3-TTS reports "zero-shot instability -- regenerating identical text produces variable timbre." A cosine similarity threshold of 0.85 (which seems reasonable) may reject 20-30% of perfectly acceptable segments because TTS variance inherently produces similarity scores in the 0.70-0.90 range even for the same speaker.

**How to avoid:**
- Set a maximum regeneration count per segment (e.g., 3 attempts), then accept the best one
- Use a lenient threshold: 0.60 cosine similarity is the established baseline for same-speaker verification, so start there, not at 0.85
- Compare against the median embedding of ALL segments for that speaker (not just the reference clip), since the "population mean" is more stable than any single reference
- Track which segments were regenerated and their scores -- if more than 15% of segments for a character are flagged, the problem is the reference clip, not the segments
- Never auto-regenerate: first pass should only FLAG segments with scores and let the user (or a heuristic) decide which to regenerate
- Store all regeneration attempts and pick the one with highest similarity, rather than discarding and trying again

**Warning signs:**
- Consistency pass takes longer than synthesis itself
- The same segments keep getting regenerated (check logs for repeated segment IDs)
- Total regeneration count exceeds 20% of total segments
- Audio quality actually gets WORSE after consistency pass (new generations introduce new problems)

**Phase to address:**
Voice Consistency phase -- must be the LAST feature implemented, after all other audio quality improvements are in place. Its threshold depends on the output quality of everything upstream.

---

### Pitfall 7: Post-Processing That Makes Audio Sound WORSE

**What goes wrong:**
The v1.1 plan calls for "trim, de-click, normalize, crossfade, compress, EQ, 44.1kHz 192kbps export." Each step individually seems beneficial, but stacking them creates cumulative artifacts: (1) aggressive de-clicking removes intentional breath sounds that make speech natural, (2) dynamic compression flattens the emotional range the emotion system just added, (3) crossfading between segments with different pitches/volumes creates audible "swoops," (4) resampling from Qwen3-TTS native sample rate to 44.1kHz introduces aliasing if not done with a quality resampler, (5) EQ applied uniformly to all speakers reduces voice distinctiveness.

**Why it happens:**
Post-processing chains designed for music or podcast production do not transfer directly to TTS audio. Professional audiobook post-production emphasizes restraint: "you don't need to remove all breaths and pauses -- narrations sound unnatural and inhuman without them." TTS audio already lacks many human imperfections, so removing more makes it sound robotic. Compression, in particular, fights against the emotion system's dynamic range variations.

**How to avoid:**
- Apply the Hippocratic principle: each processing step must demonstrate improvement via A/B comparison before being committed
- Order matters critically: normalize FIRST (LUFS), then trim silence, then gentle de-click, then encode. Skip EQ and compression entirely in the first iteration
- Keep breath sounds: do NOT use aggressive silence/breath removal. TTS already underproduces breaths
- Crossfade only at silence boundaries: never crossfade into speech. The current `concatenator.py` inserts silence gaps -- this is correct. Only crossfade within those silence regions
- Use high-quality resampling: `soxr` (via `soundfile` or `librosa`) for sample rate conversion, not simple linear interpolation
- Compression is almost certainly counterproductive for single-listener audiobooks. Skip it unless listening tests demand it
- Per-speaker EQ is dangerous -- voices were selected from LibriTTS-P specifically for their distinct characteristics

**Warning signs:**
- Processed audio sounds "flatter" or more robotic than raw TTS output
- Breaths between sentences are completely gone
- Voices sound more similar to each other after processing (EQ homogenization)
- Volume differences between dialogue and narration are gone (over-compression)
- Audible artifacts at segment boundaries (crossfade swoops)

**Phase to address:**
Post-Processing phase -- implement incrementally with A/B testing at each step. LUFS normalization already exists in v1.0 and works. Add one step at a time.

---

## Moderate Pitfalls

### Pitfall 8: mlx-audio split_pattern Bug Blocks Long Text Generation

**What goes wrong:**
The mlx-audio library has a documented bug where the `split_pattern` option is ignored for VoiceDesign and CustomVoice models -- only voice cloning (Base model) properly handles automatic text chunking for large chunks. If you rely on mlx-audio's built-in text splitting for the CustomVoice model (which is needed for emotion prompts), long text will either fail silently or produce garbled output.

**Why it happens:**
This is a library bug in mlx-audio (documented as of February 2026). The CustomVoice and VoiceDesign model implementations do not pass the `split_pattern` parameter through to the text processing pipeline.

**How to avoid:**
- Keep the existing `_split_long_text()` function in `synthesizer.py` -- do not delegate text splitting to mlx-audio
- Increase `CHAR_LIMIT` in `segmenter.py` from 280 to ~500-600, but always split text BEFORE passing to the TTS engine
- Pin your mlx-audio version and test text splitting explicitly
- Watch the [mlx-audio issue tracker](https://github.com/Blaizzy/mlx-audio/issues) for a fix to this bug

**Warning signs:**
- Audio generation hangs on long text inputs
- Output audio is truncated or garbled for segments over ~300 characters
- Working fine for short segments but failing on longer ones

**Phase to address:**
TTS Engine Swap phase -- text chunking must be handled by our pipeline, not delegated to mlx-audio.

---

### Pitfall 9: Sample Rate Mismatch Between Qwen3-TTS and Assembly Pipeline

**What goes wrong:**
Chatterbox outputs 24kHz audio. Qwen3-TTS may output at a different sample rate (the model's `sample_rate` property). The assembly pipeline (`normalizer.py`, `concatenator.py`, `encoder.py`) assumes a consistent sample rate throughout. If Qwen3-TTS outputs at a different rate and the assembly pipeline is not updated, LUFS normalization will use the wrong meter rate, concatenation will produce chipmunk/slow-motion artifacts, and the final MP3 encoding will be at the wrong bitrate.

**Why it happens:**
Sample rate is invisible when you are testing individual segments (WAV files play correctly regardless). It only manifests when segments are concatenated or processed. The current code uses `self.model.sr` from Chatterbox but does not enforce or validate the sample rate at the assembly boundary.

**How to avoid:**
- Read the sample rate from every WAV file header at assembly time (do not assume 24kHz)
- Resample all segments to a target rate (e.g., 24kHz) before concatenation if they differ
- Store the sample rate in the checkpoint so the assembly phase knows what to expect
- Add a validation step: before assembly, scan all WAVs in the chapter and verify they share the same sample rate

**Warning signs:**
- Chapter audio plays at wrong speed (chipmunk or slow)
- LUFS normalization produces bizarre loudness values
- Final MP3 has artifacts or strange pitch

**Phase to address:**
TTS Engine Swap phase -- validate sample rate compatibility as part of the initial integration test.

---

### Pitfall 10: LLM Dialogue Detection Over-Engineering

**What goes wrong:**
Replacing regex-based dialogue detection with LLM-based detection seems like an obvious upgrade. But the LLM introduces: (1) non-determinism (same text classified differently on re-runs, breaking reproducibility), (2) latency (each segment now requires an LLM call for classification, not just attribution), (3) context window pressure (dialogue detection prompts compete with attribution prompts for context), and (4) false confidence (the LLM will confidently classify ambiguous cases with made-up rationale).

**Why it happens:**
The regex-based dialogue detection in `segmenter.py` works correctly for >95% of cases (any text with quotes is dialogue). The remaining 5% are edge cases (indirect speech, thought quotes, embedded quotes within narration) where the LLM may not reliably do better than regex. But the improvement feels "free" since the LLM is already running for attribution.

**How to avoid:**
- Run LLM dialogue detection as a SECOND pass over regex results, not a replacement
- Regex catches the obvious cases (quotes present = dialogue). LLM only re-classifies segments the regex already marked as dialogue to add subtypes (spoken/thought/shouted/whispered)
- Cache LLM dialogue classification results the same way attribution is cached
- Do not run LLM dialogue detection on narration segments -- it is wasted compute
- Set a clear quality bar: if LLM detection does not improve attribution accuracy by >5% on a test chapter, revert to regex

**Warning signs:**
- Attribution phase takes 2x longer than v1.0
- Dialogue segments get re-classified between runs (non-determinism)
- LLM classifies narration as dialogue more than regex did (false positives)
- Memory pressure increases because LLM is called more often

**Phase to address:**
Dialogue Detection phase -- implement as an enhancement layer on top of regex, not a replacement.

---

### Pitfall 11: Randomized Pauses That Sound Artificial

**What goes wrong:**
The v1.1 plan adds randomized pause timing (instead of fixed silence durations in `concatenator.py`). Naive randomization (e.g., `random.uniform(200, 400)` ms) produces pauses that are uniformly distributed, which is NOT how human speech works. Human pauses follow a log-normal distribution -- mostly short pauses with occasional longer ones. Uniform randomization sounds "twitchy" and unnatural, while fixed pauses (v1.0) sound mechanical. Both are bad, but uniform random is actively worse because it draws attention to itself.

**Why it happens:**
"Randomize" is the instinctive solution to "fixed feels robotic." But the uncanny valley of randomness is real: too-perfect randomness is itself unnatural. Real pause patterns depend on context (end of sentence vs. end of paragraph vs. scene break vs. speaker change) and are not random at all -- they follow consistent contextual rules with small natural variance.

**How to avoid:**
- Use context-aware BASE durations (the current `_get_silence_ms` in `concatenator.py` already does this), then add a small Gaussian perturbation (sigma = 10-15% of the base duration)
- Sentence boundary: 300ms +/- 45ms (Gaussian, not uniform)
- Paragraph boundary: 500ms +/- 75ms
- Scene break: 1200ms +/- 120ms
- Speaker change: 400ms +/- 60ms
- Seed the random generator per book (so re-runs produce the same pauses)
- Never let a pause go below 100ms (imperceptible) or above 2000ms (awkward dead air)
- A/B test against fixed pauses -- if randomized does not clearly win, keep fixed

**Warning signs:**
- Listeners notice the pauses (good pauses are invisible)
- Pauses feel "jittery" or inconsistent within a paragraph
- Some pauses are conspicuously long while adjacent ones are conspicuously short

**Phase to address:**
Pause Timing phase -- can be done independently from other features, but test with final audio, not raw segments.

---

### Pitfall 12: Qwen3-TTS Voice Cloning Accent Regression

**What goes wrong:**
mlx-audio v0.3.0 introduced a regression where voice clones lost their accents (e.g., British English defaulted to American English) due to streaming decode changes. This was fixed in PR #461, but it demonstrates that mlx-audio is actively evolving and breaking changes affect voice quality in subtle ways that are hard to detect automatically.

**Why it happens:**
The mlx-audio library is young (released January 2026) and under active development. Encoder configuration changes, streaming optimizations, and codec parameter adjustments can silently alter voice quality. The accent loss was caused by hardcoding the stream decode to 25 tokens, which affected the voice embedding.

**How to avoid:**
- Pin mlx-audio to a known-good version and do not upgrade mid-book
- Create a voice quality regression test: generate a fixed 3-sentence test passage for each reference voice, compute speaker embedding similarity to the reference, and store the baseline scores. Re-run after any library upgrade
- If using streaming, set `streaming_interval=4` as recommended by the maintainers
- For maximum quality, disable streaming entirely and generate in batch mode
- Track the mlx-audio changelog and test each upgrade before adopting

**Warning signs:**
- Characters with distinct accents suddenly sound American/neutral
- Voice quality changes after a `pip install --upgrade mlx-audio`
- Speaker similarity scores drop across the board

**Phase to address:**
TTS Engine Swap phase -- pin library version and create regression tests.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcoding Qwen3-TTS model path | Fast integration | Cannot swap models or quantizations | Never -- use config |
| Skipping reference audio transcript | Fewer dependencies | ~15% lower voice similarity | Never -- quality is too important |
| Single emotion prompt for all segment types | Simpler code | Narration and dialogue sound the same | MVP only -- must differentiate by v1.1 release |
| No memory monitoring | Faster development | Silent OOM on longer books | MVP only -- add before full-book runs |
| Deleting Chatterbox engine code before Qwen3-TTS is proven | Cleaner codebase | No fallback if Qwen3-TTS has issues | Never -- keep until v1.1 is validated |
| Fixed cosine similarity threshold | Simple implementation | Too many false positives or missed drift | MVP only -- needs tuning per voice |
| Processing all segments through consistency check | Completeness | 2x longer pipeline on every run | Never -- only check segments with low confidence or flagged by user |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| mlx-audio + Ollama | Both loaded simultaneously | Explicit Ollama unload + memory verification before loading mlx-audio TTS model. Current `ensure_ollama_unloaded()` is necessary but verify memory actually freed |
| mlx-audio CustomVoice model | Relying on built-in text splitting | Always pre-split text before passing to mlx-audio. The `split_pattern` bug means our chunker is the only reliable splitter |
| Qwen3-TTS voice cloning + emotion | Passing emotion prompt to Base model (cloning) | Emotion prompts only work with CustomVoice model. For voice cloning with emotion, you need CustomVoice with a reference audio, not Base with an emotion string |
| MLX + PyTorch in same process | Importing both frameworks | MLX and PyTorch both claim Metal resources. Do not import torch if using MLX. Remove all PyTorch imports when switching engines |
| WAV output + assembly | Assuming sample rate matches v1.0 | Read sample rate from WAV header at assembly time. Never assume 24kHz |
| Checkpoint compatibility | Old checkpoints with new engine | Add engine version to checkpoint. Old checkpoints should be invalidated or migrated, not silently reused |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| LLM called for every segment (dialogue detection) | Attribution phase 2-3x slower | Only call LLM on regex-flagged dialogue segments for subtype classification | Books with >500 segments |
| No MLX cache limit set | Memory grows to 16GB, swap thrashing | `mx.metal.set_cache_limit(4 * 1024**3)` | Books with >100 segments in a chapter |
| Consistency pass regenerates too many segments | Pipeline runtime doubles or triples | Max 3 regen attempts per segment, 15% regen cap per character | Any book -- threshold miscalibration affects all |
| Post-processing applied per-segment instead of per-chapter | N operations * M segments = slow | Apply post-processing at chapter level (after concatenation), not per-segment | All books -- v1.0 already does this correctly for normalization |
| Speaker embedding computed per segment during consistency | O(n) embedding model loads | Load embedding model once, compute all embeddings in batch, then compare | Books with >200 segments |

## "Looks Done But Isn't" Checklist

- [ ] **TTS Engine Swap:** Generation works but `cleanup_memory()` still calls PyTorch MPS API instead of MLX Metal API
- [ ] **TTS Engine Swap:** Checkpoint format unchanged -- old Chatterbox checkpoints cause silent failures on resume
- [ ] **TTS Engine Swap:** Sample rate assumed to be 24kHz but Qwen3-TTS may output differently
- [ ] **TTS Engine Swap:** `PYTORCH_ENABLE_MPS_FALLBACK=1` env var still being set (unnecessary for MLX, potential confusion)
- [ ] **Emotion System:** Emotion prompts work on individual segments but sound jarring when played sequentially
- [ ] **Emotion System:** Narration segments get emotional coloring that makes them sound biased/opinionated
- [ ] **Voice References:** Clips selected but transcript not provided alongside audio (drops quality ~15%)
- [ ] **Dialogue Detection:** LLM detection works but results are not cached, causing re-classification on resume
- [ ] **Post-Processing:** Processing chain applied but no A/B comparison against raw output to verify improvement
- [ ] **Consistency Pass:** Embedding comparison works but threshold not tuned -- either everything passes or everything fails
- [ ] **Consistency Pass:** Regenerated segments not re-checked against consistency (infinite loop possible)
- [ ] **Pause Timing:** Pauses randomized but not seeded -- re-runs produce different audio (breaks reproducibility)
- [ ] **LLM Upgrade:** Model upgraded but `num_ctx` not adjusted -- 14B model at 32K context causes OOM

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| MLX memory leak during synthesis | LOW | Stop synthesis, resume from checkpoint. Clear cache in `cleanup_memory()`, reduce `cleanup_interval` |
| Broken pipeline after TTS swap | MEDIUM | Revert to Chatterbox engine via config flag. Requires keeping dual-engine support |
| Emotional whiplash in audio | LOW | Disable emotion overrides (set all to neutral), re-synthesize affected chapters |
| Consistency pass regeneration loop | LOW | Set max regen count, accept best attempt. Re-run with looser threshold |
| Post-processing degradation | LOW | Skip post-processing, use raw TTS output + LUFS normalization only (v1.0 approach) |
| 14B model OOM | LOW | Switch back to 8B Q4_K_M (current working model). No re-synthesis needed |
| Voice quality regression from mlx-audio update | MEDIUM | Downgrade mlx-audio to pinned version, re-synthesize affected segments |
| Sample rate mismatch | HIGH | Must re-synthesize all segments OR resample all WAVs to target rate |
| Accent loss in voice clones | MEDIUM | Disable streaming, set `streaming_interval=4`, or downgrade mlx-audio |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| MLX memory accumulation | TTS Engine Swap | Run 100-segment chapter, monitor `mx.metal.get_active_memory()` stays under 12GB |
| Reference audio too long | Voice Reference Selection | All selected clips are 10-15s, transcripts present, SNR filtered |
| Breaking working pipeline | TTS Engine Swap | Chatterbox engine still works via config flag; A/B test 10 segments |
| 14B model OOM | LLM Upgrade | Memory profiling during full attribution run; stays green in Activity Monitor |
| Emotional whiplash | Emotion System | Listen to 3 consecutive dialogue+narration segments; transitions sound natural |
| Infinite regeneration loop | Voice Consistency | Max regen count enforced; consistency pass completes in <50% of synthesis time |
| Over-processing audio | Post-Processing | A/B blind test: 5 people prefer processed over raw, or revert |
| mlx-audio split_pattern bug | TTS Engine Swap | Test 600-char text input; output is complete (not truncated or garbled) |
| Sample rate mismatch | TTS Engine Swap | All WAVs in wavs/ dir share same sample rate; assembly produces correct-speed audio |
| LLM detection over-engineering | Dialogue Detection | Attribution phase takes <1.5x v1.0 time; dialogue accuracy improves >5% on test chapter |
| Artificial pauses | Pause Timing | Pauses seeded for reproducibility; A/B test vs fixed pauses |
| Voice cloning accent regression | TTS Engine Swap | Regression test: 3-sentence passage per voice, similarity score stored and compared |

## Sources

- [MLX Unified Memory Documentation](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html) -- MLX memory architecture (HIGH confidence)
- [mlx.core.metal.clear_cache documentation](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.metal.clear_cache.html) -- MLX memory cleanup API (HIGH confidence)
- [MLX GitHub Issue #742: GPU Memory Management](https://github.com/ml-explore/mlx/issues/742) -- Memory accumulation discussion (HIGH confidence)
- [MLX GitHub Issue #1262: Active memory continues to rise](https://github.com/ml-explore/mlx-examples/issues/1262) -- Memory leak patterns (HIGH confidence)
- [mlx-audio Qwen3-TTS README](https://github.com/Blaizzy/mlx-audio/blob/main/mlx_audio/tts/models/qwen3_tts/README.md) -- API reference, model variants (HIGH confidence)
- [mlx-audio Issue #439: Voice clones lost accents](https://github.com/Blaizzy/mlx-audio/issues/439) -- Accent regression (HIGH confidence)
- [qwen3-tts-apple-silicon README](https://github.com/kapi2800/qwen3-tts-apple-silicon) -- M4 memory usage, performance (MEDIUM confidence)
- [Qwen3-TTS Voice Cloning Guide](https://ocdevel.com/blog/20260302-qwen-tts-voice-cloning) -- Reference audio length, transcript importance (MEDIUM confidence)
- [Qwen3-TTS with MLX-Audio on macOS](https://mybyways.com/blog/qwen3-tts-with-mlx-audio-on-macos) -- split_pattern bug, generation speed (MEDIUM confidence)
- [Ollama Qwen3:14B memory usage issue](https://github.com/ollama/ollama/issues/10994) -- 14B memory requirements (HIGH confidence)
- [Dopamine Audiobook paper](https://arxiv.org/html/2504.11002v1) -- Emotion control, averaged emotion problem (MEDIUM confidence)
- [Audiobook Post-Production Guide](https://www.lucentaudio.com/blog/audiobook-post-production-explained) -- Over-processing risks (MEDIUM confidence)
- [Outspoken Voices: Audio Post-Production](https://www.outspokenvoices.com/blog/the-various-steps-of-the-audio-post-production-process-in-voice-over) -- Breath preservation (MEDIUM confidence)
- [Cosine Similarity Thresholds for Speaker Verification](https://www.researchgate.net/figure/The-distribution-of-cosine-similarity-of-speaker-embeddings-in-three-conditions_fig3_360792905) -- 0.6 threshold baseline (MEDIUM confidence)
- [MLX GitHub PR #390: Metal buffer cache limit](https://github.com/ml-explore/mlx/pull/390) -- Cache limit API (HIGH confidence)
- [mlx-community Metal resource limit exceeded](https://huggingface.co/mlx-community/Fun-CosyVoice3-0.5B-2512-fp16/discussions/1) -- Metal allocation errors on Apple Silicon (HIGH confidence)

---
*Pitfalls research for: v1.1 audiobook pipeline improvements*
*Researched: 2026-03-04*
