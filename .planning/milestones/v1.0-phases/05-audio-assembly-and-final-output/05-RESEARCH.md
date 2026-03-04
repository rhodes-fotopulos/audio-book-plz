# Phase 5: Audio Assembly and Final Output - Research

**Researched:** 2026-03-03
**Domain:** Audio concatenation, MP3 encoding, loudness normalization, ID3 metadata
**Confidence:** HIGH

## Summary

Phase 5 assembles per-segment WAV files from synthesis into chapter-level and full-book MP3s. The Python audio ecosystem has mature, well-tested libraries for every piece: **pydub** for WAV concatenation and silence insertion, **pyloudnorm** for LUFS-based loudness normalization, **mutagen** for ID3 metadata and chapter markers, and **ebooklib** (already a dependency) for extracting EPUB cover art and metadata. FFmpeg is the required backend for pydub's MP3 encoding.

The pipeline is straightforward: load WAVs in segment order, insert silence gaps by boundary type, normalize loudness per-chapter to a consistent LUFS target, encode to MP3, then tag with ID3 metadata including CHAP/CTOC frames for Audiobookshelf chapter support. Chapter announcements ("Chapter X: Title") are synthesized via the existing Chatterbox TTS engine using the narrator voice.

**Primary recommendation:** Use pydub + pyloudnorm + mutagen as the assembly stack. Export chapter WAVs first, normalize each chapter independently for consistent loudness, encode to MP3, then apply ID3 tags including chapter markers on the combined file.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Scene breaks: ~2-3 seconds of silence, no audio cue or chime
- Chapter transitions: Silence gap + TTS-read chapter announcement ("Chapter X: [Title]") before each chapter begins
- Chapter announcement uses the narrator voice from the voice map
- Produce BOTH per-chapter MP3 files (in a chapters/ folder) AND a combined audiobook.mp3
- Per-segment WAV files are kept after assembly (not cleaned up)
- Chapter MP3s named sequentially for proper sorting in basic players
- Normalization only -- no noise reduction, de-essing, or extra audio processing
- Keep the raw TTS output character intact
- Source title/author from EPUB OPF metadata; allow CLI flags (--title, --author) to override
- Cover art: auto-extract from EPUB if available, allow --cover flag to override with custom image
- Embed ID3 chapter markers (chapter frames) in the combined audiobook.mp3 for players like Audiobookshelf
- Genre tag set to "Audiobook"

### Claude's Discretion
- Sentence gap duration (within natural audiobook range)
- Paragraph gap duration (clearly longer than sentence gaps)
- MP3 bitrate selection for spoken word
- Output directory structure (where audiobook.mp3 and chapters/ live relative to book output dir)
- Narrator vs character volume balance approach
- Whether to apply brief crossfade at segment boundaries for smooth transitions
- Track number embedding and additional metadata tags
- Chapter announcement voice parameters (speed, tone)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUDIO-01 | User gets a single full-audiobook MP3 file as final output | pydub concatenation + MP3 export with ffmpeg backend |
| AUDIO-02 | Appropriate silence inserted between segments (300ms sentences, 800ms paragraphs, 1500ms chapters) | pydub AudioSegment.silent() with boundary-type-based durations |
| AUDIO-03 | Audio normalized for consistent volume across different voices | pyloudnorm LUFS normalization to -19 LUFS target |
| AUDIO-04 | MP3 files include ID3 metadata (title, author, chapter names) | mutagen ID3 with CHAP/CTOC frames, APIC cover art, TIT2/TPE1/TALB tags |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydub | >=0.25.1 | WAV loading, concatenation, silence insertion, MP3 export | De facto Python audio manipulation library; simple operator-based API for segment joining |
| pyloudnorm | >=0.2.0 | LUFS loudness measurement and normalization (ITU-R BS.1770-4) | Only Python library implementing broadcast-standard LUFS normalization; NumPy/SciPy only |
| mutagen | >=1.47.0 | ID3 tag writing including CHAP/CTOC chapter markers and APIC cover art | Most complete Python ID3 library; only one with CHAP/CTOC frame support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| ebooklib | >=0.20 (already dep) | Extract title, author, cover image from EPUB OPF metadata | Phase 5 metadata extraction from source EPUB |
| numpy | (already dep via chatterbox) | Audio array conversion for pyloudnorm | Bridge between pydub AudioSegment and pyloudnorm ndarray |
| scipy | (already dep via chatterbox) | Required by pyloudnorm | Transitive dependency |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pydub | soundfile + raw ffmpeg | More control but much more boilerplate; pydub abstracts ffmpeg cleanly |
| pyloudnorm | pydub normalize() | pydub only does peak normalization (dBFS), not perceptual loudness (LUFS) |
| mutagen | eyeD3 | eyeD3 lacks CHAP/CTOC support; mutagen is the only option for chapter markers |

**Installation:**
```bash
pip install pydub pyloudnorm mutagen
```

**System dependency:** FFmpeg must be installed (`brew install ffmpeg` on macOS). Required by pydub for MP3 encoding/decoding.

## Architecture Patterns

### Recommended Module Structure
```
src/
├── assembly/
│   ├── __init__.py          # Public API exports
│   ├── models.py            # AssemblyConfig, ChapterInfo, AssemblyStats
│   ├── concatenator.py      # WAV loading, silence insertion, chapter assembly
│   ├── normalizer.py        # LUFS measurement and normalization
│   ├── encoder.py           # MP3 encoding via pydub
│   ├── tagger.py            # ID3 metadata, CHAP/CTOC, cover art via mutagen
│   ├── metadata.py          # EPUB metadata extraction (title, author, cover)
│   └── assembler.py         # Orchestrator: concat -> normalize -> encode -> tag
```

### Pattern 1: Boundary-Based Silence Insertion
**What:** Different silence durations based on segment boundary type
**When to use:** Between every pair of adjacent segments

```python
from pydub import AudioSegment

# Silence durations by boundary type
SILENCE_SENTENCE_MS = 400      # Between sentences within a paragraph
SILENCE_PARAGRAPH_MS = 900     # Between paragraphs
SILENCE_SCENE_BREAK_MS = 2500  # Scene breaks (~2-3s per user decision)
SILENCE_CHAPTER_MS = 1500      # Before chapter announcement

def get_silence_duration(prev_segment, next_segment) -> int:
    """Determine silence gap based on boundary type."""
    if next_segment["type"] == "chapter_heading":
        return SILENCE_CHAPTER_MS
    if prev_segment["type"] == "scene_break" or next_segment["type"] == "scene_break":
        return SILENCE_SCENE_BREAK_MS
    # Paragraph break: different chapter or non-adjacent IDs suggest paragraph
    if prev_segment.get("chapter") != next_segment.get("chapter"):
        return SILENCE_CHAPTER_MS
    return SILENCE_PARAGRAPH_MS  # Default to paragraph gap

silence = AudioSegment.silent(duration=duration_ms)
combined = audio1 + silence + audio2
```

### Pattern 2: LUFS Normalization Pipeline
**What:** Measure and normalize loudness per chapter to consistent target
**When to use:** After concatenating all segments for a chapter, before MP3 encoding

```python
import numpy as np
import pyloudnorm as pyln

def normalize_audio(audio_segment: AudioSegment, target_lufs: float = -19.0) -> AudioSegment:
    """Normalize an AudioSegment to target LUFS."""
    samples = np.array(audio_segment.get_array_of_samples(), dtype=np.float32)
    # Normalize to [-1, 1] range
    samples = samples / (2 ** (audio_segment.sample_width * 8 - 1))

    meter = pyln.Meter(audio_segment.frame_rate)
    current_lufs = meter.integrated_loudness(samples)

    if current_lufs == float('-inf'):
        return audio_segment  # Silent audio, skip

    normalized = pyln.normalize.loudness(samples, current_lufs, target_lufs)

    # Convert back to int16
    normalized = np.clip(normalized, -1.0, 1.0)
    normalized_int = (normalized * (2 ** 15 - 1)).astype(np.int16)

    return audio_segment._spawn(normalized_int.tobytes())
```

### Pattern 3: ID3 Chapter Markers (CHAP/CTOC)
**What:** Embed chapter markers in combined audiobook MP3 for player support
**When to use:** After encoding combined audiobook.mp3

```python
from mutagen.id3 import ID3, CTOC, CHAP, TIT2, TPE1, TALB, TCON, APIC, CTOCFlags

def add_chapter_markers(mp3_path, chapters):
    """Add CHAP/CTOC frames to MP3 for audiobook player support."""
    audio = ID3(mp3_path)

    child_ids = [f"chp{i}" for i in range(len(chapters))]

    # Table of contents
    audio.add(CTOC(
        element_id="toc",
        flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
        child_element_ids=child_ids,
        sub_frames=[TIT2(text=["Table of Contents"])]
    ))

    # Individual chapters
    for i, ch in enumerate(chapters):
        audio.add(CHAP(
            element_id=f"chp{i}",
            start_time=ch.start_ms,
            end_time=ch.end_ms,
            sub_frames=[TIT2(text=[ch.title])]
        ))

    audio.save()
```

### Pattern 4: EPUB Metadata Extraction
**What:** Extract title, author, and cover image from EPUB using ebooklib
**When to use:** Before tagging MP3 files

```python
from ebooklib import epub

def extract_epub_metadata(epub_path):
    """Extract title, author, cover image from EPUB."""
    book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})

    title = book.get_metadata("DC", "title")
    title = title[0][0] if title else "Unknown Title"

    creator = book.get_metadata("DC", "creator")
    author = creator[0][0] if creator else "Unknown Author"

    # Cover image extraction
    cover_data = None
    cover_mime = None
    # Method 1: OPF cover metadata
    cover_meta = book.get_metadata("OPF", "cover")
    if cover_meta:
        cover_id = cover_meta[0][1].get("content", "")
        cover_item = book.get_item_with_id(cover_id)
        if cover_item:
            cover_data = cover_item.get_content()
            cover_mime = cover_item.media_type

    return title, author, cover_data, cover_mime
```

### Anti-Patterns to Avoid
- **Building one giant AudioSegment in memory:** For a full audiobook (8+ hours), this can consume many GB of RAM. Process chapter by chapter, normalize, and write to disk incrementally.
- **Peak normalization instead of LUFS:** Peak normalization (pydub's built-in) makes loud peaks equal but doesn't equalize perceived loudness. Different voices will still sound uneven. Use LUFS.
- **Writing chapter markers before final MP3 is complete:** CHAP frames reference absolute millisecond offsets. Calculate all chapter start/end times from the concatenation pass, then apply to the finished file.
- **Ignoring pydub MP3 export truncation:** Known bug where last segment can be chopped. Workaround: append 100ms silence at the very end before MP3 export.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Audio concatenation | Custom WAV byte manipulation | pydub AudioSegment + operator | WAV format has headers, sample alignment, channel handling |
| Loudness normalization | Custom RMS/dBFS normalization | pyloudnorm LUFS | ITU-R BS.1770-4 is perceptually weighted; hand-rolling misses frequency weighting |
| MP3 encoding | Calling ffmpeg directly | pydub.export(format="mp3") | pydub handles temp files, format detection, parameter passing |
| ID3 chapter markers | Raw ID3 byte manipulation | mutagen CHAP/CTOC | Frame ordering, encoding, padding are complex; mutagen handles all edge cases |
| EPUB metadata parsing | Manual XML/OPF parsing | ebooklib get_metadata() | EPUB2 vs EPUB3 differences, namespace handling, cover image resolution |

**Key insight:** Audio file formats have intricate binary structures. Every "simple" operation (concatenation, normalization, encoding, tagging) has edge cases that mature libraries handle and hand-rolled solutions miss.

## Common Pitfalls

### Pitfall 1: Memory Exhaustion on Full-Book Assembly
**What goes wrong:** Loading all WAV segments into one AudioSegment for a 10-hour book consumes 10+ GB of RAM (24kHz 16-bit mono = ~172 MB/hour).
**Why it happens:** pydub keeps everything in memory as raw PCM.
**How to avoid:** Process chapter by chapter. Concatenate segments within a chapter, normalize, export to chapter MP3, then concatenate chapter MP3s into the final audiobook. Never hold more than one chapter's audio in memory at once.
**Warning signs:** Process killed by OOM; system swap usage spikes during assembly.

### Pitfall 2: pydub MP3 Export Truncation
**What goes wrong:** The last fraction of a second of audio gets chopped off when exporting to MP3.
**Why it happens:** Known pydub issue with MP3 frame alignment -- ffmpeg's MP3 encoder pads/trims to frame boundaries.
**How to avoid:** Append 100ms of silence to the end of any AudioSegment before MP3 export. This sacrificial padding absorbs the truncation.
**Warning signs:** Last word of a chapter sounds cut off in the MP3 but plays fine in WAV.

### Pitfall 3: Chapter Marker Ordering in Audiobookshelf
**What goes wrong:** Chapters display out of order in audiobook players.
**Why it happens:** Known mutagen issue where CHAP frames may sort by title length instead of element ID.
**How to avoid:** Use zero-padded element IDs (chp001, chp002) and verify the written file with a tag reader before declaring success. Alternatively, add CHAP frames in strict chronological order.
**Warning signs:** Chapters appear shuffled in Audiobookshelf or other ID3 chapter-aware players.

### Pitfall 4: LUFS Measurement on Short Audio
**What goes wrong:** pyloudnorm returns -inf or unreliable values for very short audio clips.
**Why it happens:** ITU-R BS.1770 uses 400ms gating blocks; audio shorter than 400ms has no valid measurement.
**How to avoid:** Only normalize at the chapter level (always >400ms), never per-segment. If a chapter is extremely short, fall back to peak normalization.
**Warning signs:** Normalized audio is silent or has extreme volume spikes.

### Pitfall 5: Missing FFmpeg
**What goes wrong:** pydub silently produces 0-byte or corrupt MP3 files, or raises CouldntDecodeError.
**Why it happens:** FFmpeg is a system dependency, not a pip package. CI/CD and fresh machines often lack it.
**How to avoid:** Check for ffmpeg at assembly start: `shutil.which("ffmpeg")`. Fail early with a clear error message if missing.
**Warning signs:** MP3 files are 0 bytes; pydub raises vague exceptions.

### Pitfall 6: Cover Art MIME Type Mismatch
**What goes wrong:** Cover art doesn't display in audiobook players.
**Why it happens:** APIC frame mime type doesn't match actual image format, or image data is corrupt.
**How to avoid:** Detect image type from magic bytes (JPEG: FF D8, PNG: 89 50 4E 47) rather than trusting EPUB metadata.
**Warning signs:** Players show no cover; some players show a broken image icon.

## Code Examples

### Complete Chapter Assembly Flow
```python
from pydub import AudioSegment

def assemble_chapter(wav_paths, segment_metadata, chapter_title, narrator_announcement_wav=None):
    """Assemble a single chapter from WAV segments with silence insertion."""
    chapter_audio = AudioSegment.empty()

    # Prepend chapter announcement if provided
    if narrator_announcement_wav:
        announcement = AudioSegment.from_wav(narrator_announcement_wav)
        chapter_audio += announcement
        chapter_audio += AudioSegment.silent(duration=800)

    for i, (wav_path, meta) in enumerate(zip(wav_paths, segment_metadata)):
        segment = AudioSegment.from_wav(wav_path)

        if i > 0:
            prev_meta = segment_metadata[i - 1]
            silence_ms = determine_silence(prev_meta, meta)
            chapter_audio += AudioSegment.silent(duration=silence_ms)

        chapter_audio += segment

    # Anti-truncation padding
    chapter_audio += AudioSegment.silent(duration=100)

    return chapter_audio
```

### MP3 Export with Proper Settings
```python
def export_mp3(audio_segment, output_path, bitrate="64k"):
    """Export AudioSegment to MP3 with spoken-word optimized settings."""
    audio_segment.export(
        output_path,
        format="mp3",
        bitrate=bitrate,
        parameters=["-ac", "1"],  # Force mono for spoken word
    )
```

### Full ID3 Tagging
```python
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TRCK, APIC, CTOC, CHAP, CTOCFlags
from mutagen.id3 import Encoding

def tag_audiobook(mp3_path, title, author, chapters, cover_data=None, cover_mime="image/jpeg"):
    """Apply complete ID3 tags to audiobook MP3."""
    audio = ID3(mp3_path)

    # Basic tags
    audio.add(TIT2(encoding=Encoding.UTF8, text=[title]))
    audio.add(TPE1(encoding=Encoding.UTF8, text=[author]))
    audio.add(TALB(encoding=Encoding.UTF8, text=[title]))
    audio.add(TCON(encoding=Encoding.UTF8, text=["Audiobook"]))

    # Cover art
    if cover_data:
        audio.add(APIC(
            encoding=Encoding.UTF8,
            mime=cover_mime,
            type=3,  # Front cover
            desc="Cover",
            data=cover_data,
        ))

    # Chapter markers
    child_ids = [f"chp{i:03d}" for i in range(len(chapters))]
    audio.add(CTOC(
        element_id="toc",
        flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
        child_element_ids=child_ids,
        sub_frames=[TIT2(encoding=Encoding.UTF8, text=["Table of Contents"])]
    ))

    for i, ch in enumerate(chapters):
        audio.add(CHAP(
            element_id=f"chp{i:03d}",
            start_time=ch["start_ms"],
            end_time=ch["end_ms"],
            sub_frames=[TIT2(encoding=Encoding.UTF8, text=[ch["title"]])]
        ))

    audio.save()
```

## Discretion Recommendations

Based on research, these are recommendations for areas left to Claude's discretion:

| Area | Recommendation | Rationale |
|------|---------------|-----------|
| Sentence gap | 400ms | Standard audiobook range (300-500ms); 400ms feels natural without dragging |
| Paragraph gap | 900ms | Clearly longer than sentence (2x+); standard audiobook convention |
| MP3 bitrate | 64k mono | ACX/Audible standard for spoken word; 128k adds file size with no perceptible quality gain for speech |
| Output directory | `{book_dir}/chapters/` for chapter MP3s, `{book_dir}/audiobook.mp3` for combined | Keeps all outputs in existing book directory structure |
| Crossfade | No crossfade | Silence gaps are explicit design decisions; crossfade would blur intentional boundaries |
| Track numbers | Embed TRCK (1/N, 2/N...) in chapter MP3s | Helps basic players sort correctly alongside sequential naming |
| Chapter announcement | Normal speed, narrator's natural tone | Match the narrator's reading voice for continuity; no special effects |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Peak/RMS normalization | LUFS (ITU-R BS.1770-4) | 2020+ industry adoption | Perceptually consistent loudness across voices |
| ID3v2.3 only | ID3v2.4 with CHAP/CTOC | mutagen 1.42+ | Chapter markers supported by modern players |
| MP3 VBR for speech | CBR 64k mono | Industry standard | Consistent quality, accurate seeking, smaller files |

**Deprecated/outdated:**
- pydub `normalize()` effect: Only does peak normalization, not perceptual loudness. Use pyloudnorm instead.
- eyeD3 for chapter markers: Does not support CHAP/CTOC frames. Use mutagen.

## Open Questions

1. **Chapter announcement synthesis timing**
   - What we know: Chatterbox TTS engine from Phase 4 can synthesize the announcement text using the narrator voice reference
   - What's unclear: Whether to synthesize announcements during the assembly phase (Phase 5) or pre-generate them as a sub-step. Synthesizing during assembly means importing Chatterbox again.
   - Recommendation: Pre-generate chapter announcement WAVs as the first step of assembly, then unload TTS before the main concatenation loop. This keeps memory usage bounded.

2. **FFmpeg availability guarantee**
   - What we know: FFmpeg is required for pydub MP3 encoding. Chatterbox (Phase 4 dep) may have already pulled it in via torchaudio.
   - What's unclear: Whether the user's environment has ffmpeg in PATH.
   - Recommendation: Check `shutil.which("ffmpeg")` at assembly start and fail with a clear install instruction if missing.

## Sources

### Primary (HIGH confidence)
- [mutagen ID3 frames API](https://mutagen.readthedocs.io/en/latest/api/id3_frames.html) - CHAP, CTOC, APIC frame constructors verified
- [mutagen ID3 user guide](https://mutagen.readthedocs.io/en/latest/user/id3.html) - Chapter marker examples
- [pyloudnorm GitHub](https://github.com/csteinmetz1/pyloudnorm) - API, version 0.2.0, ITU-R BS.1770-4 implementation
- [pydub GitHub](https://github.com/jiaaro/pydub) - AudioSegment API, silence insertion, MP3 export

### Secondary (MEDIUM confidence)
- [mutagen CHAP ordering issue #506](https://github.com/quodlibet/mutagen/issues/506) - Chapter tag write sequence bug
- [pydub MP3 truncation issue #530](https://github.com/jiaaro/pydub/issues/530) - MP3 export end truncation
- [pydub silence concatenation #215](https://github.com/jiaaro/pydub/issues/215) - Silence insertion pattern

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries verified on PyPI with current versions and Python 3.11 support
- Architecture: HIGH - Patterns derived from official documentation and verified API signatures
- Pitfalls: HIGH - Confirmed via GitHub issues with reproduction steps and community verification

**Research date:** 2026-03-03
**Valid until:** 2026-04-03 (stable domain, mature libraries)
