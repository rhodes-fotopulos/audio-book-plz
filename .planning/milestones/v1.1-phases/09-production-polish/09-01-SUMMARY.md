---
phase: 09-production-polish
plan: 01
status: complete
requirements-completed: [POL-01, POL-02, POL-05]
---

## Summary

Added Gaussian-randomized pause timing, segment crossfades, and a pedalboard mastering effects chain to the assembly pipeline.

### Changes

**src/assembly/models.py**
- Added `PauseConfig` dataclass with Gaussian parameters (mean, std, min, max) for 5 boundary types: sentence, paragraph, speaker change, scene break, chapter break
- Added `pause_config: PauseConfig` field to `AssemblyConfig` (default `PauseConfig()`)
- Updated `mp3_bitrate` default from `"64k"` to `"192k"` for ACX compliance
- Added `export_sample_rate: int = 44100` field for ACX compliance
- Marked legacy fixed silence fields as deprecated

**src/assembly/concatenator.py**
- Added `gaussian_pause_ms(mean, std, min_val, max_val) -> int` using `numpy.random.normal` + `np.clip`
- Refactored `_get_silence_ms()` to accept `PauseConfig` with Gaussian sampling and speaker change detection
- Added `_apply_crossfade(segment_audio, fade_ms) -> AudioSegment` with guard for short segments (clamps fade to half segment length)
- Updated `assemble_chapter()` to use PauseConfig and crossfades on every segment

**src/assembly/effects.py** (new)
- `create_mastering_chain() -> Pedalboard`: NoiseGate(-40dB) -> Compressor(-20dB, 3:1) -> HighpassFilter(80Hz) -> Limiter(-3dB)
- `measure_audio_metrics(audio, sample_rate) -> dict`: LUFS + peak dB measurement via pyloudnorm
- `apply_effects_chain(chapter_audio, board) -> (AudioSegment, metrics)`: A/B validation with regression detection, ACX peak ceiling enforcement at -3dB
- Hard peak ceiling clip at -3dB (0.7079) after pedalboard processing to enforce ACX compliance despite Limiter makeup gain

**pyproject.toml**
- Added `pedalboard>=0.9.19` dependency

**tests/test_pause_timing.py** (new) - 6 tests
**tests/test_effects_chain.py** (new) - 5 tests

### Verification

All 11 tests pass. Gaussian pause values stay within bounds, crossfade guards work for short segments, effects chain has 4 effects in correct order, limiter reduces peak below -3dB.
