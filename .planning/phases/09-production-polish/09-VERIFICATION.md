---
phase: 09-production-polish
status: passed
verified: 2026-03-04
---

# Phase 9 Verification: Production Polish

## Requirement Coverage

All 5 Phase 9 requirements (POL-01 through POL-05) verified against codebase.

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| POL-01 | Gaussian-randomized pause timing for natural narrator feel | PASS | `PauseConfig` dataclass in `src/assembly/models.py` (lines 22-69) defines Gaussian parameters (mean, std, min, max) for 5 boundary types: sentence (350ms mean), paragraph (450ms mean, 300-600ms range per user decision), speaker change (600ms mean), scene break (2200ms mean), chapter break (3500ms mean). `gaussian_pause_ms()` in `src/assembly/concatenator.py` (lines 25-43) samples from `numpy.random.normal()` with `np.clip()` to clamp values. `_get_silence_ms()` (lines 46-107) dispatches to the correct boundary type based on segment metadata: chapter_heading -> chapter params, scene_break -> scene params, different speakers -> speaker_change params, default -> paragraph params. `assemble_chapter()` (lines 137-195) calls `_get_silence_ms()` for every inter-segment gap. |
| POL-02 | Professional mastering effects chain with A/B validation | PASS | `create_mastering_chain()` in `src/assembly/effects.py` (lines 34-66) returns a `Pedalboard` with 4 effects in order: `NoiseGate(threshold_db=-40.0, ratio=10.0, attack_ms=1.0, release_ms=100.0)` -> `Compressor(threshold_db=-20.0, ratio=3.0, attack_ms=10.0, release_ms=150.0)` -> `HighpassFilter(cutoff_frequency_hz=80.0)` -> `Limiter(threshold_db=-3.0, release_ms=100.0)`. `apply_effects_chain()` (lines 106-199) converts AudioSegment to float32 numpy, measures before metrics via `measure_audio_metrics()` (LUFS + peak dB), applies pedalboard, enforces hard peak ceiling at -3dB via `np.clip(processed, -_ACX_PEAK_CEILING, _ACX_PEAK_CEILING)` (line 153), measures after metrics, checks for regressions (peak increase >1dB or LUFS drop >6dB triggers warning), returns processed audio + metrics dict. Effects chain is called from `src/assembly/assembler.py` `run_assembly()` (line 257): `chapter_audio, effects_metrics = apply_effects_chain(chapter_audio, board)` -- inserted between `assemble_chapter()` (concatenation) and `normalize_audio()` (LUFS normalization). Chain created once before chapter loop (line 216). |
| POL-03 | ACX-compliant MP3 export (44.1kHz 192kbps CBR mono) | PASS | `export_chapter_mp3()` in `src/assembly/encoder.py` (lines 33-61) has defaults `bitrate="192k"` and `sample_rate=44100`. FFmpeg parameters include `["-ac", "1", "-ar", str(sample_rate)]` (line 58) for mono resampling to 44.1kHz. `combine_chapter_mp3s()` (lines 64-103) uses same defaults. `AssemblyConfig` in `src/assembly/models.py` has `mp3_bitrate: str = "192k"` (line 108) and `export_sample_rate: int = 44100` (line 111). `run_assembly()` in assembler.py passes `config.mp3_bitrate` and `config.export_sample_rate` to both `export_chapter_mp3()` (lines 274-277) and `combine_chapter_mp3s()` (lines 329-332). |
| POL-04 | Voice consistency verification with Resemblyzer speaker embeddings | PASS | `VoiceConsistencyVerifier` class in `src/synthesis/voice_verifier.py` (lines 103-270) uses Resemblyzer GE2E voice encoder for 256-dim speaker embeddings. `build_reference_embeddings()` (lines 136-188) loads reference clips via `preprocess_wav()` and `embed_utterance()`. `check_segment()` (lines 241-263) computes cosine similarity between segment and reference embedding. `cosine_similarity()` (lines 224-239) implements standard dot-product similarity. Threshold default is 0.60 (line 118), max regen attempts is 3 (line 119), segments < 2.0s skipped (line 120). `run_voice_consistency()` (lines 278-427) orchestrates full check with optional regeneration. `run_voice_check()` in `src/pipeline.py` (lines 556-620) orchestrates the verification from pipeline level. **CLI fix from Plan 10-01 confirmed:** `main.py` `assemble` command (lines 347-349) calls `run_voice_check(book_dir, voice_threshold=voice_threshold)` before `run_assemble()`, making `--voice-threshold` flag functional. `verify_voices` standalone CLI command (lines 357-384) also wired correctly. `run_full_pipeline()` (lines 783-789) includes voice check as Phase 4.5 between synthesis and assembly. |
| POL-05 | Crossfade at segment boundaries (5-10ms fade-in/fade-out) | PASS | `_apply_crossfade()` in `src/assembly/concatenator.py` (lines 110-134) applies `fade_in(safe_fade)` and `fade_out(safe_fade)` to each segment. Guard clause clamps fade to `min(fade_ms, len(segment_audio) // 2)` for short segments (line 130). Returns unmodified segment if length is 0 (line 126). `PauseConfig.crossfade_ms = 8` in `src/assembly/models.py` (line 68) -- within the 5-10ms spec range. `assemble_chapter()` calls `_apply_crossfade(segment_audio, fade_ms)` for every segment at line 180, before concatenation. |

## Must-Have Truths (from Plan Frontmatter)

### Plan 09-01 (POL-01, POL-02, POL-05: Gaussian Pauses, Crossfades, Effects Chain)

- [x] Pauses between segments vary naturally with Gaussian randomization -- no two runs produce identical silence durations (POL-01)
- [x] Segment boundaries use 5-10ms fade-in/fade-out instead of hard cuts (POL-05)
- [x] Post-processing effects chain applies noise gate, compressor, high-pass EQ at 80Hz, and limiter in correct order (POL-02)
- [x] A/B metrics (LUFS, peak dB) are logged before and after effects chain, and regressions are flagged (POL-02)

### Plan 09-02 (POL-04: Voice Consistency Verifier)

- [x] Every synthesized segment is checked against its character's reference voice embedding (POL-04)
- [x] Segments below cosine similarity threshold trigger TTS regeneration up to 3 attempts (POL-04)
- [x] When all 3 regeneration attempts fail, the best-scoring attempt is kept and flagged as a warning (POL-04)
- [x] Voice consistency results are written to a separate report file (POL-04)
- [x] Segments shorter than 2 seconds are skipped for voice consistency (too short for reliable embeddings) (POL-04)

### Plan 09-03 (POL-03, POL-04: ACX Export, Pipeline Wiring, CLI Flags)

- [x] Final MP3 export is 44.1kHz 192kbps CBR mono meeting ACX specifications (POL-03)
- [x] Per-chapter MP3 files use descriptive naming from EPUB chapter titles (POL-03)
- [x] Both per-chapter and combined audiobook files are generated (POL-03)
- [x] Effects chain is wired into assembly between concatenation and LUFS normalization (POL-02)
- [x] Voice consistency verification runs between synthesis and assembly in the pipeline (POL-04)
- [x] --output-dir and --voice-threshold CLI flags are available (POL-04)
- [x] Full pipeline runs end-to-end with all Phase 9 features integrated

## Artifact Verification

### Plan 09-01 Artifacts

| Artifact | Expected | Actual |
|----------|----------|--------|
| src/assembly/models.py | PauseConfig with Gaussian parameters per boundary type | Present, `class PauseConfig` with 5 boundary types (sentence, paragraph, speaker_change, scene_break, chapter), each with mean/std/min/max fields |
| src/assembly/concatenator.py | Gaussian pause sampling and crossfade application | Present, `gaussian_pause_ms()` using numpy.random.normal, `_apply_crossfade()` with fade_in/fade_out |
| src/assembly/effects.py | Pedalboard mastering chain with A/B validation | Present, `create_mastering_chain()` returns 4-effect Pedalboard, `apply_effects_chain()` with before/after metrics |
| tests/test_pause_timing.py | Tests for Gaussian pause and crossfade behavior | Present, 6 tests covering bounds, variation, speaker change detection, scene breaks, crossfade guards |
| tests/test_effects_chain.py | Tests for effects chain application and A/B metrics | Present, 5 tests covering chain structure, audio processing, peak reduction, metric keys |

### Plan 09-02 Artifacts

| Artifact | Expected | Actual |
|----------|----------|--------|
| src/synthesis/voice_verifier.py | Voice consistency verification and regeneration loop | Present, `VoiceConsistencyVerifier` class with Resemblyzer embeddings, `run_voice_consistency()` with optional regeneration, `ConsistencyReport` |
| tests/test_voice_verifier.py | Tests for embedding comparison and threshold logic | Present, 10 tests covering cosine similarity, threshold pass/fail, report generation, short segments, placeholders |

### Plan 09-03 Artifacts

| Artifact | Expected | Actual |
|----------|----------|--------|
| src/assembly/encoder.py | ACX-compliant MP3 export (44.1kHz 192kbps CBR) | Present, `export_chapter_mp3()` with bitrate="192k", sample_rate=44100, FFmpeg `-ar` param |
| src/assembly/assembler.py | Effects chain integration, descriptive file naming, voice consistency wiring | Present, imports `create_mastering_chain`/`apply_effects_chain`, `_slugify_title()` helper, `output_dir` parameter |
| src/pipeline.py | Voice consistency pass, --output-dir support | Present, `run_voice_check()` function, `run_full_pipeline()` includes Phase 4.5 voice check |
| main.py | --voice-threshold and --output-dir CLI flags | Present, `voice_threshold` option on assemble/convert/verify-voices commands, `mp3_dir` option on assemble/convert |
| tests/test_acx_export.py | Tests for ACX-compliant export parameters | Present, 7 tests covering bitrate defaults, sample rate, slugify title variants |

## Key Link Verification

### Plan 09-01 Key Links

| From | To | Via | Verified |
|------|----|-----|----------|
| src/assembly/concatenator.py | src/assembly/models.py | `from src.assembly.models import AssemblyConfig, PauseConfig` | Yes (line 20) |
| src/assembly/effects.py | pedalboard | `from pedalboard import Compressor, HighpassFilter, Limiter, NoiseGate, Pedalboard` | Yes (lines 16-22) |

### Plan 09-02 Key Links

| From | To | Via | Verified |
|------|----|-----|----------|
| src/synthesis/voice_verifier.py | resemblyzer | `from resemblyzer import VoiceEncoder` (lazy import in `_get_encoder()`) and `from resemblyzer import preprocess_wav` | Yes (lines 130-131, 152) |
| src/synthesis/voice_verifier.py | src/synthesis/engine_base.py | `from src.synthesis.engine_factory import create_engine` (lazy import in regeneration loop) | Yes (line 369) |

### Plan 09-03 Key Links

| From | To | Via | Verified |
|------|----|-----|----------|
| src/assembly/assembler.py | src/assembly/effects.py | `from src.assembly.effects import apply_effects_chain, create_mastering_chain` | Yes (line 95) |
| src/pipeline.py | src/synthesis/voice_verifier.py | `from src.synthesis.voice_verifier import run_voice_consistency` | Yes (line 576) |
| main.py | src/pipeline.py | `from src.pipeline import ... run_voice_check` and `voice_threshold` CLI flag threading | Yes (lines 15, 349) |

### Plan 10-01 CLI Fix Link (Cross-Phase)

| From | To | Via | Verified |
|------|----|-----|----------|
| main.py assemble command | src/pipeline.py run_voice_check() | `run_voice_check(book_dir, voice_threshold=voice_threshold)` called before `run_assemble()` | Yes (main.py line 349) |

## Test Results

- **225 tests passing** (all existing + Phase 9 additions)
- **Zero test regressions**
- Test breakdown for Phase 9:
  - tests/test_pause_timing.py: 6 tests (Gaussian bounds, variation, speaker change, scene break, crossfade guard, sentence boundary)
  - tests/test_effects_chain.py: 5 tests (chain structure, audio processing, peak reduction, metric keys, empty audio)
  - tests/test_voice_verifier.py: 10 tests (cosine similarity, threshold logic, report generation, short segments, placeholders)
  - tests/test_acx_export.py: 7 tests (bitrate defaults, sample rate, slugify title variants)

## Gaps

None found -- all implementations confirmed by code audit. CLI bugs identified in v1.1 milestone audit were fixed in Plan 10-01 (assemble --voice-threshold wiring, synthesize --libritts-audio wiring), and now formally verified in this document.
