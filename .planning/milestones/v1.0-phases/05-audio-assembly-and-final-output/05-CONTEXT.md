# Phase 5: Audio Assembly and Final Output - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Concatenate per-segment WAV files into chapter-level and full-book MP3s with appropriate silence spacing, volume normalization, and ID3 metadata. Cover art extraction, chapter markers, and chapter announcement TTS are in scope. New pipeline phases, additional TTS features, or playback functionality are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Silence spacing
- Scene breaks: ~2-3 seconds of silence, no audio cue or chime
- Chapter transitions: Silence gap + TTS-read chapter announcement ("Chapter X: [Title]") before each chapter begins
- Chapter announcement uses the narrator voice from the voice map

### Output format
- Produce BOTH per-chapter MP3 files (in a chapters/ folder) AND a combined audiobook.mp3
- Per-segment WAV files are kept after assembly (not cleaned up)
- Chapter MP3s named sequentially for proper sorting in basic players

### Volume normalization
- Normalization only — no noise reduction, de-essing, or extra audio processing
- Keep the raw TTS output character intact

### ID3 metadata
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

</decisions>

<specifics>
## Specific Ideas

- Chapter announcements should feel like a professional audiobook — the narrator voice reads "Chapter X: [Title]" before each chapter
- Audiobookshelf compatibility is important — chapter markers and metadata should work with that player
- WAV files preserved so user can re-assemble with different settings without re-running synthesis

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-audio-assembly-and-final-output*
*Context gathered: 2026-03-03*
