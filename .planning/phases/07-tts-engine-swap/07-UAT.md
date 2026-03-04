---
status: complete
phase: 07-tts-engine-swap
source: 07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md
started: 2026-03-04T12:00:00Z
updated: 2026-03-04T12:05:00Z
---

## Current Test

[testing complete]

## Tests

### 1. CLI --engine option on convert command
expected: Running `python main.py convert --help` shows an `--engine` option with choices `qwen3` and `chatterbox`, defaulting to `qwen3`.
result: pass

### 2. CLI --engine option on synthesize command
expected: Running `python main.py synthesize --help` shows the same `--engine` option with qwen3 default.
result: pass

### 3. Text chunking produces 500-600 char segments
expected: Importing `chunk_text_qwen` from `src.synthesis.chunker` and passing a ~1500 char paragraph produces chunks in the 200-600 char range, split at sentence boundaries (no mid-sentence breaks).
result: pass

### 4. Voice clip selector targets 10-15 second clips
expected: `select_reference_clip` in `src/matching/clip_selector.py` scores clips by proximity to 12.5s duration (not just longest), filtering to 5-25s range.
result: pass

### 5. Checkpoint includes engine metadata
expected: `create_checkpoint()` in `src/synthesis/checkpoint.py` accepts engine params and writes an `"engine"` dict with name, version, library into the checkpoint JSON.
result: pass

### 6. Legacy checkpoint detection
expected: `check_engine_compatibility()` returns `(False, reason)` for v1.0 checkpoints that lack engine metadata, preventing silent reuse with wrong engine.
result: pass

### 7. Test suite passes
expected: Running `python -m pytest tests/` completes with 135 tests passing and zero failures.
result: pass

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
