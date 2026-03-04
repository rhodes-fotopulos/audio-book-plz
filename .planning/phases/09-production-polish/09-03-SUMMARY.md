---
phase: 09-production-polish
plan: 03
status: complete
---

## Summary

Wired all Phase 9 features into the assembly pipeline, encoder, pipeline orchestrator, and CLI: ACX-compliant export, effects chain integration, voice consistency, descriptive file naming, and new CLI flags.

### Changes

**src/assembly/encoder.py**
- Updated `export_chapter_mp3()`: default bitrate `"192k"`, added `sample_rate: int = 44100` parameter, FFmpeg params now include `-ar` for resampling
- Updated `combine_chapter_mp3s()`: same bitrate, sample rate, and FFmpeg resampling changes

**src/assembly/assembler.py**
- Added `_slugify_title(title, ch_num)` helper for descriptive file naming (e.g., "01-the-dark-forest.mp3")
- Imports and applies `create_mastering_chain()` and `apply_effects_chain()` from effects module
- Effects chain created ONCE before chapter loop, applied between concatenation and LUFS normalization
- Chapter MP3s use descriptive filenames from EPUB titles instead of generic `chapter_001.mp3`
- Added `output_dir` parameter for MP3 output location override
- Passes `export_sample_rate` to encoder functions

**src/pipeline.py**
- Added `run_voice_check()` function: loads voice map/attributed segments, calls `run_voice_consistency()`, prints Rich summary
- Updated `run_assemble()`: added `output_dir` parameter, threads through to assembler
- Updated `run_full_pipeline()`: added `voice_threshold` and `mp3_output_dir` parameters, inserted voice consistency check between synthesis and assembly (Phase 4.5)

**main.py**
- Added `--voice-threshold` flag to `convert` and `assemble` commands (default 0.60)
- Added `--mp3-dir` flag to `convert` and `assemble` commands
- Added `verify-voices` CLI command for standalone voice consistency verification
- Imported `run_voice_check` from pipeline

**tests/test_acx_export.py** (new) - 7 tests

### Verification

All 7 tests pass. ACX defaults correct (192k bitrate, 44100 sample rate), slugify produces clean filenames for various inputs. CLI help shows all new flags and commands without conflicts.
