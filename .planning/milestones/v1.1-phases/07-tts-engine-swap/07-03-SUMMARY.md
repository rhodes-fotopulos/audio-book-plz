---
phase: 07-tts-engine-swap
plan: 03
status: complete
commit: 5e67be0
---

## Summary

Wired the engine abstraction, chunker, voice prep, and checkpoint versioning into the full synthesis pipeline with auto-fallback and CLI integration.

## Changes

### src/synthesis/checkpoint.py (modified)
- `create_checkpoint()` now accepts `engine_name`, `engine_version`, `engine_library` params.  Checkpoint JSON includes `"engine"` dict with name, version, library.
- `load_checkpoint()` detects and logs legacy v1.0 checkpoints (no engine metadata).
- New `check_engine_compatibility(checkpoint, engine_name)` returns `(compatible, reason)` tuple.
- New `archive_checkpoint(book_dir)` moves checkpoint.json and wavs/ to `checkpoint_archive/` with timestamp suffix.

### src/synthesis/synthesizer.py (rewritten)
- Replaced `TTSEngine` import with `create_engine()` from engine_factory.
- Removed old `_split_long_text()` (now in chunker.py).
- Engine creation via `create_engine(config)` based on `config.engine_type`.
- Checkpoint engine compatibility check on resume; auto-archives on mismatch.
- Voice reference preparation via `prepare_all_voice_references()` when `libritts_root` provided.
- Text chunking via `chunk_text_qwen()` (500-600 chars) or `chunk_text_chatterbox()` (280 chars).
- Per-segment auto-fallback: Qwen3 failures create lazy Chatterbox fallback engine, re-chunk for Chatterbox, retry.
- Fallback summary logged at end of run with rate warning if >10%.
- Audio concatenation uses numpy instead of torch.cat.
- Added `libritts_root` parameter to `run_synthesis()` signature.

### src/synthesis/__init__.py (rewritten)
- Exports new public API: `create_engine`, `TTSEngineBase`, `AudioResult`, `chunk_text_qwen`, `chunk_text_chatterbox`.
- Removed old `TTSEngine` export.

### src/synthesis/tts_engine.py (converted to shim)
- `TTSEngine` is now a deprecated shim subclass of `ChatterboxEngine`.
- Emits `DeprecationWarning` on instantiation.
- Preserves backward compatibility for `src/assembly/announcer.py`.

### src/pipeline.py (modified)
- `run_synthesize()` accepts `engine_type` and `libritts_audio_dir` params.
- Passes `engine_type` to `SynthesisConfig` and `libritts_root` to `run_synthesis()`.
- `run_full_pipeline()` accepts `engine_type` and passes through to `run_synthesize()`.
- Logs info when `--cpu` is used with qwen3 (MLX manages device selection).

### main.py (modified)
- Added `--engine` option to both `synthesize` and `convert` commands (default: qwen3).
- Updated synthesize docstring from "Chatterbox TTS" to "TTS engine (Qwen3-TTS or Chatterbox)".
- Passes `engine_type` through to `run_synthesize()` and `run_full_pipeline()`.

### pyproject.toml (modified)
- Added `mlx-audio>=0.3.1` dependency with comment about Qwen3-TTS.
- Added `soundfile>=0.12` dependency.

### tests/test_synthesizer.py (updated)
- All tests now mock `src.synthesis.synthesizer.create_engine` instead of `TTSEngine`.
- Mock engine returns `AudioResult` (numpy) instead of `FakeTensor` (torch-like).
- Added `test_engine_checkpoint_compatibility` verifying mismatch archival.
- 6 tests, all passing.

## Verification
- All imports verified across synthesis package.
- `python main.py convert --help` shows `--engine` option with qwen3 default.
- `python main.py synthesize --help` shows `--engine` option with qwen3 default.
- 135 tests pass with zero regressions.
- Checkpoint engine versioning works: compatible returns True, mismatch returns False with reason, legacy returns False.
