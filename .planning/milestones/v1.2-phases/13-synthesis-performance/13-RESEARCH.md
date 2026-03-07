# Phase 13: Synthesis Performance - Research

**Researched:** 2026-03-06
**Domain:** TTS synthesis optimization (voice reference caching, batch ordering)
**Confidence:** HIGH

## Summary

Phase 13 implements two synthesis performance optimizations: reference encoding caching (SYNTH-05) and batch-by-character ordering (SYNTH-06). Both are pure performance optimizations with no output changes.

The mlx-audio Qwen3-TTS model processes reference audio through `speech_tokenizer.encode(ref_audio)` on every `generate()` call, producing codec codes of shape `[1, 16, ref_time]`. This encoding is the expensive per-segment operation that caching targets. The mlx-audio API does not expose a way to pass pre-encoded reference codes directly -- the encode step happens internally in `_generate_icl()` via `_prepare_icl_generation_inputs()`. This means caching must be implemented either by (a) caching the loaded `mx.array` audio (post-`load_audio`, saving I/O) and accepting the re-encode cost, or (b) monkey-patching/wrapping the engine to intercept the encode step.

**Primary recommendation:** Implement a two-layer cache in the synthesizer: cache the loaded audio `mx.array` per character (eliminates file I/O), and wrap the engine's `speech_tokenizer.encode` method with a cache keyed on character name to eliminate redundant neural codec encoding. Batch-by-character is a straightforward reorder of the existing synthesis loop with segment ID tracking for correct reassembly.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Cache the encoded reference representation per character so the reference audio is processed once per character, not once per segment
- Cache lives in memory during the synthesis run (not persisted to disk)
- Cache key: character name or speaker ID (maps 1:1 to voice reference clip)
- The cache must work transparently -- no user action required, always enabled
- Visible in logs: "Cached reference encoding for {character}" on first use, "Using cached reference for {character}" on subsequent
- Add `--batch-by-character` CLI flag (default OFF -- chapter-by-chapter remains default)
- When enabled: group all segments by speaker, synthesize all segments for each character consecutively, then reorder output back into chapter/segment order for assembly
- Final audiobook output must be byte-identical regardless of synthesis order
- Progress display when batching: show character name + segment count instead of chapter progress
- Checkpoint/resume must work correctly with batch ordering -- completed segment IDs tracked by segment_id, not position
- `--batch-by-character` flag added to CLI `synthesize` and `convert` commands
- Wired through `run_synthesize()` and `run_full_pipeline()` in pipeline.py
- SynthesisConfig gets `batch_by_character: bool = False` field

### Claude's Discretion
- Exact MLX/mlx-audio API for extracting and reusing encoded reference representations
- Whether reference caching requires engine-level changes or can be done at synthesizer level
- Progress display layout details for batch-by-character mode
- Whether to add timing logs showing reference cache hit savings

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SYNTH-05 | Precomputed reference encoding cached per character, reused across all segments for that character | Reference caching architecture documented below; two-layer approach (load_audio cache + encode cache) addresses both I/O and computation costs |
| SYNTH-06 | `--batch-by-character` flag for per-character synthesis ordering with post-hoc chapter stitching | Batch ordering pattern documented; checkpoint system already uses segment_id keys so reordering is safe |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mlx-audio | latest | TTS engine (Qwen3-TTS) | Already in use; provides `model.generate()` with ref_audio/ref_text |
| mlx | latest | Apple Silicon ML framework | Already in use; provides mx.array, Metal cache management |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| typer | existing | CLI framework | Already used for all CLI commands; add --batch-by-character flag |
| rich | existing | Progress display | Already used for SynthesisProgress; needs character-mode variant |

No new dependencies required for this phase.

## Architecture Patterns

### Recommended Changes Structure
```
src/synthesis/
  models.py           # Add batch_by_character field to SynthesisConfig
  qwen_engine.py      # Add reference cache (load_audio + encode wrapper)
  synthesizer.py      # Add batch-by-character iteration path
  progress.py         # Add character-mode progress display
src/cli.py            # Add --batch-by-character to synthesize + convert
src/pipeline.py       # Wire batch_by_character through run_synthesize + run_full_pipeline
```

### Pattern 1: Reference Encoding Cache (SYNTH-05)

**What:** Cache voice reference data per character to avoid redundant processing.

**Where to cache:** The engine level (qwen_engine.py) is the right place. The mlx-audio `model.generate()` API accepts `ref_audio` as either a string path or an `mx.array`. Passing a pre-loaded `mx.array` eliminates the `load_audio()` file I/O. For the heavier `speech_tokenizer.encode()` step, wrap it with a cache.

**Implementation approach:**
```python
# In QwenTTSEngine -- add a reference cache dict
class QwenTTSEngine(TTSEngineBase):
    def __init__(self, config: SynthesisConfig) -> None:
        super().__init__(config)
        self.model = None
        self._sample_rate: int | None = None
        self._ref_cache: dict[str, mx.array] = {}  # character_name -> loaded audio

    def generate(
        self,
        text: str,
        ref_clip_path: str,
        ref_transcript: str | None = None,
        segment_type: str = "narration",
        character_name: str | None = None,  # NEW: for cache keying
    ) -> AudioResult:
        # Use cached audio array if available
        cache_key = character_name or ref_clip_path
        if cache_key in self._ref_cache:
            ref_audio_array = self._ref_cache[cache_key]
            logger.debug("Using cached reference for %s", cache_key)
        else:
            from mlx_audio.utils import load_audio
            ref_audio_array = load_audio(ref_clip_path, sample_rate=self._sample_rate)
            self._ref_cache[cache_key] = ref_audio_array
            logger.info("Cached reference encoding for %s", cache_key)

        # Pass mx.array directly to model.generate() -- skips load_audio internally
        results = list(self.model.generate(
            text=text,
            ref_audio=ref_audio_array,  # mx.array, not string path
            ref_text=ref_transcript,
        ))
        # ... rest unchanged
```

**For the deeper encode caching:** Wrap `self.model.speech_tokenizer.encode` with a memoizing wrapper after model load:
```python
def load_model(self) -> None:
    # ... existing load code ...
    # Wrap speech_tokenizer.encode with cache
    original_encode = self.model.speech_tokenizer.encode
    encode_cache: dict[int, mx.array] = {}

    def cached_encode(audio):
        # Use hash of audio shape + first/last samples as cache key
        key = (audio.shape, float(audio[0]), float(audio[-1]))
        if key not in encode_cache:
            encode_cache[key] = original_encode(audio)
        return encode_cache[key]

    self.model.speech_tokenizer.encode = cached_encode
```

**Recommendation:** Use both layers. The load_audio cache is clean and safe (keyed by character name). The encode wrapper is more impactful but requires careful key design -- using the `mx.array` identity (same object in memory) is safest since we control the cache and pass the same array object for the same character.

### Pattern 2: Batch-by-Character Ordering (SYNTH-06)

**What:** Reorder synthesis iteration from chapter-by-chapter to character-by-character.

**When to use:** When `--batch-by-character` flag is enabled.

**Implementation approach:**
```python
# In synthesizer.py -- add alternative iteration path
if config.batch_by_character:
    # Group segments by speaker
    speaker_groups: dict[str, list[dict]] = defaultdict(list)
    for seg in segments:
        if seg["id"] in pending_set:
            speaker = seg.get("speaker", "narrator")
            speaker_groups[speaker].append(seg)

    for speaker, speaker_segs in speaker_groups.items():
        # Sort by segment_id within each speaker group
        speaker_segs.sort(key=lambda s: s["id"])
        progress.update_character(speaker, len(speaker_segs))  # NEW method

        for seg in speaker_segs:
            # ... same generation logic as chapter loop ...
            pass
else:
    # ... existing chapter-by-chapter loop (unchanged) ...
```

**Key insight:** The checkpoint system already uses `segment_id` as keys (strings in the `completed` dict), not positional indices. This means synthesis order does not affect checkpoint/resume correctness. A run interrupted during batch-by-character mode can resume correctly because `get_pending_segments()` checks `segment_id` membership, not iteration order.

### Pattern 3: Progress Display for Batch Mode

**What:** Show character-oriented progress instead of chapter progress when batching.

```python
# In SynthesisProgress -- add character mode
def update_character(self, character: str, total_segments: int) -> None:
    """Switch to character-mode progress display."""
    self._progress.update(
        self._chapter_task,
        description=f"Character: {character}",
        info=f"[{total_segments} segments]",
    )
```

### Anti-Patterns to Avoid
- **Modifying mlx-audio source code:** Do not fork or patch the mlx-audio package files. Use the public API and wrapper patterns instead.
- **Disk-based cache:** The CONTEXT.md explicitly says cache lives in memory only. Do not write cached encodings to disk.
- **Changing generate() signature in TTSEngineBase:** Adding `character_name` to the abstract base would break the interface contract. Instead, add it as an optional parameter to QwenTTSEngine.generate() and pass it from the synthesizer where the character name is known. Alternatively, set a "current character" on the engine before calling generate.
- **Changing output ordering in assembly:** Batch-by-character affects synthesis iteration order only. WAV files are still written to the same paths (e.g., `wavs/ch01/seg_0001.wav`), so assembly reads them in the same order regardless.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Audio loading/resampling | Custom WAV loader | `mlx_audio.utils.load_audio` | Handles format detection, resampling, normalization |
| Codec encoding | Custom encoder | `model.speech_tokenizer.encode` | Neural codec specific to Qwen3-TTS architecture |
| Progress bars | Custom terminal output | Rich Progress (existing) | Already used, handles terminal resizing, ETA |

## Common Pitfalls

### Pitfall 1: Cache Key Collision
**What goes wrong:** Different characters sharing the same speaker_id could collide if speaker_id is used as cache key.
**Why it happens:** Multiple minor characters may be assigned the same LibriTTS speaker.
**How to avoid:** Use character name as primary cache key. The voice_lookup dict already maps character_name -> clip_path, and multiple characters sharing a clip will correctly share the cache entry (which is desirable -- same clip means same encoding).
**Warning signs:** Audio from wrong voice appearing for a character.

### Pitfall 2: mx.array Cache Invalidation
**What goes wrong:** Cached mx.array objects could become invalid after `mx.metal.clear_cache()` or memory pressure.
**Why it happens:** MLX Metal cache management may evict underlying buffers.
**How to avoid:** The reference audio arrays are small (a few seconds of audio at 24kHz = ~100KB per character). They should survive cache clears since `mx.metal.clear_cache()` clears the Metal compute cache, not MLX array storage. Test this explicitly.
**Warning signs:** Segfault or garbage audio after cleanup_memory() call.

### Pitfall 3: Byte-Identical Output Assumption
**What goes wrong:** Batch-by-character output differs from chapter-by-chapter output due to floating-point non-determinism.
**Why it happens:** MLX Metal operations may have order-dependent floating-point rounding. Each segment is generated independently, so the order should not matter -- but verify this.
**How to avoid:** The requirement says "byte-identical" but this may be aspirational. Test with a small book: generate once in chapter order, once in batch order, compare WAV files. If they differ, document the difference as acceptable (same quality, different bit pattern) or investigate further.
**Warning signs:** WAV file checksums differ between modes.

### Pitfall 4: Progress Display Mode Confusion
**What goes wrong:** Batch-by-character mode still shows chapter progress bars that don't advance meaningfully.
**Why it happens:** SynthesisProgress is initialized with chapter counts that don't apply to character-based iteration.
**How to avoid:** Pass a mode flag to SynthesisProgress and initialize differently for batch mode (character count instead of chapter count).

### Pitfall 5: Engine Base Class Signature Change
**What goes wrong:** Adding `character_name` to `TTSEngineBase.generate()` abstract method breaks the interface for any future engines.
**Why it happens:** Trying to pass cache context through the abstract interface.
**How to avoid:** Two options: (1) Add `character_name` as kwargs only in QwenTTSEngine, not the base. (2) Use a `set_current_character(name)` method on the engine that the synthesizer calls before `generate()`. Option 2 is cleaner -- the engine stores state about which character's cache to use.

## Code Examples

### Current generate() call flow (synthesizer.py)
```python
# Source: src/synthesis/synthesizer.py lines 288-290
audio_result = _generate_segment_audio(
    engine, text_chunks, ref_clip, ref_transcript, seg_type
)
```

### Current _generate_segment_audio helper
```python
# Source: src/synthesis/synthesizer.py lines 46-78
def _generate_segment_audio(engine, text_chunks, ref_clip, ref_transcript, seg_type):
    if len(text_chunks) == 1:
        return engine.generate(text_chunks[0], ref_clip, ref_transcript, seg_type)
    # Multi-chunk concatenation...
```

### Voice lookup (where character name is available)
```python
# Source: src/synthesis/synthesizer.py lines 257-261
speaker = seg.get("speaker", "narrator")
voice = voice_lookup.get(speaker, voice_lookup.get("narrator"))
ref_clip = voice["clip_path"] if voice else ""
ref_transcript = voice.get("transcript") if voice else None
char_name = speaker
```

### Existing flag wiring pattern (speech_act_fx, established Phase 12)
```python
# CLI (src/cli.py):
speech_act_fx: bool = typer.Option(False, "--speech-act-fx", help="...")

# Pipeline (src/pipeline.py):
def run_synthesize(..., speech_act_fx: bool = False):
    config = SynthesisConfig(..., speech_act_fx=speech_act_fx)

# Config (src/synthesis/models.py):
speech_act_fx: bool = False
```

### Checkpoint segment tracking (already segment_id based)
```python
# Source: src/synthesis/checkpoint.py lines 243-249
def mark_completed(checkpoint, segment_id, wav_path, duration_s, took_s):
    key = str(segment_id)
    checkpoint["completed"][key] = {
        "wav": wav_path,
        "duration_s": round(duration_s, 3),
        "took_s": round(took_s, 3),
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Re-encode reference per segment | Cache reference encoding | Phase 13 (this phase) | Eliminates redundant neural codec encoding |
| Chapter-by-chapter synthesis only | Optional batch-by-character | Phase 13 (this phase) | Reduces MLX cache thrashing between voices |

**Key technical detail:** The mlx-audio `model.generate()` accepts `ref_audio` as either `str` (file path) or `mx.array` (pre-loaded audio). Passing `mx.array` skips the internal `load_audio()` call. However, the `speech_tokenizer.encode()` call inside `_generate_icl()` is still called every time. Wrapping this encoder with a cache keyed on the audio array identity (Python `id()` for same-object check) provides the deepest optimization.

## Open Questions

1. **Does mx.metal.clear_cache() invalidate mx.array data?**
   - What we know: `mx.metal.clear_cache()` is documented as clearing the Metal compute cache, not MLX tensor storage. The synthesizer calls it every N segments.
   - What's unclear: Whether reference audio arrays (~100KB each) are affected.
   - Recommendation: Test empirically. If they are affected, move cleanup_memory to skip clearing when reference cache is active, or re-populate cache after clear.

2. **Is byte-identical output achievable across synthesis orders?**
   - What we know: Each segment is generated independently with its own reference. Generation order should not affect per-segment output.
   - What's unclear: Whether MLX Metal state (warm caches, memory layout) causes floating-point differences.
   - Recommendation: Test with a small corpus. If not byte-identical, relax requirement to "functionally equivalent audio" and document the finding.

3. **How much time does speech_tokenizer.encode() take per call?**
   - What we know: It runs a neural codec encoder on ~5-15 seconds of reference audio. This should be 100-500ms per call on M4.
   - What's unclear: Exact timing vs. the full generate() call time.
   - Recommendation: Add timing logs to measure the encode step independently. This validates whether the cache provides meaningful speedup.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none (default discovery) |
| Quick run command | `python3 -m pytest tests/test_synthesizer.py tests/test_synthesis_models.py -x -q` |
| Full suite command | `python3 -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SYNTH-05 | Reference encoding cached per character | unit | `python3 -m pytest tests/test_synthesizer.py::test_reference_cache_reuses_encoding -x` | Wave 0 |
| SYNTH-05 | Cache log messages appear | unit | `python3 -m pytest tests/test_synthesizer.py::test_reference_cache_log_messages -x` | Wave 0 |
| SYNTH-06 | batch_by_character flag in SynthesisConfig | unit | `python3 -m pytest tests/test_synthesis_models.py::test_batch_by_character_config_default -x` | Wave 0 |
| SYNTH-06 | Batch mode groups by speaker | unit | `python3 -m pytest tests/test_synthesizer.py::test_batch_by_character_groups_by_speaker -x` | Wave 0 |
| SYNTH-06 | Output identical regardless of batch mode | unit | `python3 -m pytest tests/test_synthesizer.py::test_batch_output_matches_sequential -x` | Wave 0 |
| SYNTH-06 | Checkpoint/resume works with batch ordering | unit | `python3 -m pytest tests/test_synthesizer.py::test_batch_checkpoint_resume -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_synthesizer.py tests/test_synthesis_models.py -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_synthesizer.py::test_reference_cache_reuses_encoding` -- verify engine.generate called with cached ref
- [ ] `tests/test_synthesizer.py::test_reference_cache_log_messages` -- verify log output for cache hits
- [ ] `tests/test_synthesis_models.py::test_batch_by_character_config_default` -- verify default False
- [ ] `tests/test_synthesizer.py::test_batch_by_character_groups_by_speaker` -- verify iteration order
- [ ] `tests/test_synthesizer.py::test_batch_output_matches_sequential` -- verify WAV path consistency
- [ ] `tests/test_synthesizer.py::test_batch_checkpoint_resume` -- verify resume after interrupt

## Sources

### Primary (HIGH confidence)
- mlx-audio GitHub repository (https://github.com/Blaizzy/mlx-audio) -- model.generate() API, ref_audio parameter types
- mlx-audio qwen3_tts.py source -- _generate_icl(), _prepare_icl_generation_inputs(), speech_tokenizer.encode() flow
- Project source code (src/synthesis/) -- existing synthesizer loop, checkpoint system, engine abstraction

### Secondary (MEDIUM confidence)
- mlx-audio Qwen3-TTS README -- API surface for voice cloning with ref_audio + ref_text
- Web search results confirming Qwen3-TTS codec architecture (12.5 Hz, 16 codebooks)

### Tertiary (LOW confidence)
- Byte-identical output claim -- needs empirical testing, floating-point determinism across synthesis orders is unverified

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing code paths understood
- Architecture: HIGH -- mlx-audio internal API verified via source code, cache strategy well-defined
- Pitfalls: MEDIUM -- mx.array lifecycle under Metal cache management needs empirical testing

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable domain, no fast-moving dependencies)
