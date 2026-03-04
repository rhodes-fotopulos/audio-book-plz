---
phase: 05-audio-assembly-and-final-output
plan: 01
started: 2026-03-03
completed: 2026-03-03
duration_minutes: 3
---

# Plan 05-01 Summary: Assembly data models, EPUB metadata, WAV concatenator

## What Was Built

Created the `src/assembly/` module foundation with data models, EPUB metadata extraction, and WAV segment concatenation with boundary-aware silence insertion.

## Key Files

### Created
- `src/assembly/__init__.py` — Public API exports (AssemblyConfig, ChapterInfo, EpubMetadata, AssemblyStats, assemble_chapter, extract_epub_metadata)
- `src/assembly/models.py` — Four dataclasses: AssemblyConfig (silence durations, bitrate, LUFS target), ChapterInfo (chapter offsets for CHAP frames), EpubMetadata (title/author/cover), AssemblyStats
- `src/assembly/metadata.py` — extract_epub_metadata() using ebooklib with OPF cover method + filename scan fallback
- `src/assembly/concatenator.py` — assemble_chapter() with _get_silence_ms() boundary resolver

### Modified
- `pyproject.toml` — Added pydub>=0.25.1, pyloudnorm>=0.2.0, mutagen>=1.47.0

## Decisions

- Paragraph silence (900ms) is the default between all segments since Phase 1 segmenter produces paragraph-level segments; sentence_silence_ms (400ms) reserved for future sub-paragraph detection
- Cover image extraction tries OPF metadata first (standard), then scans IMAGE items for "cover" in filename (common EPUB convention)
- Anti-truncation padding (100ms silence) appended to every chapter to prevent pydub MP3 export end truncation

## Self-Check: PASSED

- [x] All four dataclasses importable from src.assembly.models
- [x] extract_epub_metadata imports and accepts Path argument
- [x] assemble_chapter imports with pydub dependency
- [x] pyproject.toml has all three new dependencies
- [x] All tasks committed individually
