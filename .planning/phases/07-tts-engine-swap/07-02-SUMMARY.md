---
phase: 07-tts-engine-swap
plan: 02
status: complete
commit: dd1caea
---

## Summary

Created the text chunking pipeline for engine-appropriate segment sizes and the voice reference preparation system with SNR scoring and transcript bundling.

## Changes

### src/synthesis/chunker.py (new)
- `chunk_text_qwen(text, max_chars=580, min_chars=200)`: 500-600 char chunks at sentence boundaries via NLTK sent_tokenize. Merges tiny trailing chunks. Never breaks mid-sentence.
- `chunk_text_chatterbox(text, max_chars=280)`: Preserved v1.0 chunking logic for Chatterbox fallback.
- `chunk_segments_by_speaker(segments, engine_type)`: Applies chunking to attributed segment dicts while preserving speaker metadata. Multi-chunk segments get sub-IDs like "42.0", "42.1".
- `_ensure_nltk_data()`: punkt_tab/punkt bootstrap matching Phase 1 pattern.

### src/synthesis/voice_prep.py (new)
- `VoiceReference` dataclass: clip_path, transcript, duration_s, snr_score
- `_compute_snr_rms(audio_path)`: Frame-based RMS SNR computation (30ms frames, 1% threshold). Returns SNR in dB or None on failure.
- `prepare_voice_reference(speaker_id, clip_path, libritts_root)`: Single character voice prep with SNR, transcript lookup from .normalized.txt, and duration computation.
- `prepare_all_voice_references(voice_map, libritts_root)`: All characters + narrator. Logs summary with transcript and SNR warning counts.

### src/matching/clip_selector.py (rewritten)
- `select_reference_clip()`: Now targets 10-15s clips (score = 1/(1+abs(duration-12.5))) instead of just longest. Filters clips to 5-25s range. Falls back to longest clip under 25s.
- `select_reference_clip_with_transcript()`: Returns (clip_path, transcript) tuple by looking up .normalized.txt companion files in LibriTTS-R.

## Verification
- All imports verified: chunker, voice_prep, clip_selector
- chunk_text_qwen produces correct single-element list for short text
- 134 existing tests pass with zero regressions
