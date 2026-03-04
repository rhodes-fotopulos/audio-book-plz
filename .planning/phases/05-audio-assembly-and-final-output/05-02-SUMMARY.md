---
phase: 05-audio-assembly-and-final-output
plan: 02
started: 2026-03-03
completed: 2026-03-03
duration_minutes: 3
---

# Plan 05-02 Summary: LUFS normalizer, MP3 encoder, chapter announcer

## What Was Built

Created three assembly components: LUFS loudness normalizer for consistent voice volume, MP3 encoder with FFmpeg validation and chapter combining, and chapter announcement WAV generator using the narrator's Chatterbox voice.

## Key Files

### Created
- `src/assembly/normalizer.py` — normalize_audio() using pyloudnorm ITU-R BS.1770-4 with -19.0 LUFS target; handles silent and short audio edge cases
- `src/assembly/encoder.py` — check_ffmpeg() validation, export_chapter_mp3() with mono/64k CBR, combine_chapter_mp3s() for full audiobook assembly
- `src/assembly/announcer.py` — generate_announcements() using TTSEngine with narrator ref clip, 0.2 exaggeration, atomic writes, resume-safe

## Decisions

- LUFS normalization target -19.0 (within audiobook standard range -23 to -18, slightly louder for personal listening)
- Minimum 400ms audio for valid LUFS measurement (one ITU-R BS.1770 gating block); shorter audio returned unchanged
- MP3 bitrate 64k CBR mono (ACX/Audible standard for spoken word)
- Chapter announcements use exaggeration=0.2 and cfg_weight=0.3 for neutral narrator tone
- Late import pattern for announcer: torch/chatterbox only loaded when generate_announcements() is called

## Self-Check: PASSED

- [x] normalize_audio imports without error
- [x] check_ffmpeg, export_chapter_mp3, combine_chapter_mp3s import without error
- [x] generate_announcements imports without torch at module level
- [x] All tasks committed individually
