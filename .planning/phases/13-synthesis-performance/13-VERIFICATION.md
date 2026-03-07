---
phase: 13-synthesis-performance
verified: 2026-03-06T23:59:00Z
status: passed
score: 7/7 must-haves verified
---

# Phase 13: Synthesis Performance Verification Report

**Phase Goal:** Synthesis runs faster by caching voice references and enabling per-character batch ordering
**Verified:** 2026-03-06T23:59:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Voice reference encoding is computed once per character and reused across all that character's segments | VERIFIED | `_ref_cache` dict in `qwen_engine.py:46`, cache lookup at L137-146, `load_audio` called only on cache miss |
| 2 | Running with --batch-by-character synthesizes all segments for each character consecutively | VERIFIED | `synthesizer.py:480-508` batch path groups by speaker, sorts by segment count desc, iterates speaker then segments |
| 3 | Final audiobook output is identical regardless of whether --batch-by-character is used | VERIFIED | WAV paths remain chapter-based `wavs/ch{NN}/seg_{NNNN}.wav` at `synthesizer.py:112-113` in `_process_segment`, used by both paths |
| 4 | Log shows cache hit/miss messages | VERIFIED | `qwen_engine.py:146` logs "Cached reference encoding for %s", L140 logs "Using cached reference for %s" |
| 5 | Synthesis output is unchanged (cache is transparent) | VERIFIED | Cached `ref_audio_data` (mx.array) passed to `model.generate(ref_audio=ref_audio_data)` at L148-153, same data whether cached or fresh |
| 6 | Progress display shows character name + segment count when batching | VERIFIED | `progress.py:125-134` `update_character()` sets description to "Character: {character}" with "[{N} segments]" info |
| 7 | Checkpoint/resume works correctly with batch ordering | VERIFIED | `_process_segment` uses `mark_completed(cp, seg_id, ...)` with segment_id-based tracking; `pending_set` check at `_run_segment:440`; test `test_batch_checkpoint_resume` covers this |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/synthesis/qwen_engine.py` | Reference audio cache (load_audio + encode wrapper) | VERIFIED | `_ref_cache` dict at L46, `_encode_cache` at L47, encode wrapper at L79-90, cache clear on unload at L191-193 |
| `src/synthesis/synthesizer.py` | Character name passed through to engine for cache keying | VERIFIED | `_generate_segment_audio` accepts `character_name` at L52, passes as kwarg at L61,71; `_process_segment` at L86 uses it at L136 |
| `tests/test_synthesizer.py` | Tests for reference cache behavior | VERIFIED | 5 cache tests (L608-740) + 4 batch tests (L461-605) = 9 new tests |
| `src/synthesis/models.py` | batch_by_character field on SynthesisConfig | VERIFIED | `batch_by_character: bool = False` at L59 with docstring |
| `src/cli.py` | --batch-by-character flag on synthesize and convert commands | VERIFIED | `synthesize` command at L278-282, `convert` command at L101-105 |
| `src/pipeline.py` | batch_by_character wired through run_synthesize and run_full_pipeline | VERIFIED | `run_synthesize` param at L405, config construction at L507; `run_full_pipeline` param at L738, passed at L785 |
| `src/synthesis/synthesizer.py` | Batch-by-character iteration path in run_synthesis | VERIFIED | `if config.batch_by_character:` at L480, full batch path L480-508, `else:` chapter path L511-528 |
| `src/synthesis/progress.py` | Character-mode progress display | VERIFIED | `update_character()` at L125-134, `complete_character()` at L136-138 |
| `tests/test_synthesizer.py` | Tests for batch-by-character behavior | VERIFIED | 4 batch tests at L461-605: grouping, WAV paths, checkpoint resume, progress display |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/synthesis/synthesizer.py` | `src/synthesis/qwen_engine.py` | engine.generate() called with character_name | WIRED | `_generate_segment_audio` passes `character_name=character_name` at L61,71; `_process_segment` calls at L134-137 |
| `src/synthesis/qwen_engine.py` | mlx_audio model.generate() | Passes cached mx.array instead of file path | WIRED | `ref_audio=ref_audio_data` at L151 where `ref_audio_data` comes from `self._ref_cache[cache_key]` at L139 |
| `src/cli.py` | `src/pipeline.py` | batch_by_character parameter passed to run_synthesize and run_full_pipeline | WIRED | CLI synthesize passes at L308, convert passes at L139; pipeline accepts at L405 and L738 |
| `src/pipeline.py` | `src/synthesis/models.py` | SynthesisConfig(batch_by_character=batch_by_character) | WIRED | Config construction at L507 includes `batch_by_character=batch_by_character` |
| `src/synthesis/synthesizer.py` | `src/synthesis/progress.py` | progress.update_character() called in batch mode | WIRED | `progress.update_character(speaker, len(speaker_segs), char_idx)` at L499 |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SYNTH-05 | 13-01-PLAN | Precomputed reference encoding cached per character, reused across all segments for that character | SATISFIED | Two-layer cache in `qwen_engine.py`: `_ref_cache` for load_audio, `_encode_cache` for speech_tokenizer.encode; 5 tests verify behavior |
| SYNTH-06 | 13-02-PLAN | --batch-by-character flag for per-character synthesis ordering with post-hoc chapter stitching | SATISFIED | CLI flag wired end-to-end through pipeline to synthesizer; batch iteration path groups by speaker; WAV paths chapter-based; 4 tests verify behavior |

No orphaned requirements found. REQUIREMENTS.md maps SYNTH-05 and SYNTH-06 to Phase 13, and both are claimed and satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | No anti-patterns detected |

No TODO/FIXME/placeholder comments, no empty implementations, no stub patterns found in any modified files.

### Human Verification Required

### 1. Reference Cache Performance Improvement

**Test:** Run full synthesis on a multi-character book with and without the cache, compare wall-clock times.
**Expected:** Measurable reduction in per-segment synthesis time (100-500ms saved per segment on M4).
**Why human:** Requires actual MLX hardware execution with real model to measure timing.

### 2. Batch-by-Character Output Equivalence

**Test:** Run synthesis on same book with and without `--batch-by-character`, compare output WAV files.
**Expected:** WAV files at identical paths with same content (or acceptably similar given TTS non-determinism).
**Why human:** Requires running actual TTS engine; non-determinism in model output makes exact comparison complex.

### 3. Character Progress Display

**Test:** Run `--batch-by-character` synthesis and observe Rich progress bar.
**Expected:** Progress bar shows "Character: {name}" with "[N segments]" for each character batch.
**Why human:** Visual display verification requires running the actual CLI.

### Gaps Summary

No gaps found. All observable truths verified, all artifacts exist and are substantive, all key links are wired, both requirements (SYNTH-05, SYNTH-06) are satisfied, and no anti-patterns detected. The `_process_segment` helper successfully eliminates code duplication between chapter and batch paths. The TTSEngineBase abstract interface was not modified (character_name is QwenTTSEngine-only).

---

_Verified: 2026-03-06T23:59:00Z_
_Verifier: Claude (gsd-verifier)_
