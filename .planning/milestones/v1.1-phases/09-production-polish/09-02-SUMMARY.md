---
phase: 09-production-polish
plan: 02
status: complete
requirements-completed: [POL-04]
---

## Summary

Built voice consistency verification using Resemblyzer speaker embeddings with regeneration loop and report generation.

### Changes

**src/synthesis/voice_verifier.py** (new)
- `VoiceConsistencyVerifier` class:
  - Lazy-loads Resemblyzer's `VoiceEncoder` on CPU
  - `build_reference_embeddings(voice_map)`: Builds 256-dim embeddings from reference clips, skips `AUDIO_DIR/` placeholder paths
  - `compute_segment_embedding(wav_path)`: Loads WAV, checks duration (skips < 2s), preprocesses via `preprocess_wav()`, computes embedding
  - `cosine_similarity(a, b)`: Standard dot-product cosine similarity
  - `check_segment(wav_path, ref_embedding)`: Returns (similarity, passes_threshold), (1.0, True) for too-short segments
  - Configurable threshold (default 0.60), max_regen (default 3), min_duration_s (default 2.0)

- `ConsistencyReport` dataclass:
  - Tracks segments_checked, segments_passed, segments_regenerated, segments_flagged, segments_skipped
  - `write_report(output_path)`: Writes JSON with summary stats and flagged segment details

- `run_voice_consistency()` function:
  - Iterates all segments, checks each against reference embedding
  - Optional regeneration mode (when engine_config provided): regenerates up to 3 times, keeps best attempt
  - Verification-only mode (no engine_config): flags without regeneration
  - Writes `voice_consistency_report.json` to book_dir

**pyproject.toml**
- Added `Resemblyzer>=0.1.3` dependency

**tests/test_voice_verifier.py** (new) - 10 tests

### Verification

All 10 tests pass. Cosine similarity math correct (identical=1.0, orthogonal=0.0, opposite=-1.0), threshold logic works, report writes valid JSON, short segments skipped, placeholder clips skipped.
