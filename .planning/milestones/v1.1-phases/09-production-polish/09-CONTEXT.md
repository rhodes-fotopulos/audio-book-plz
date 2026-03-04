# Phase 9: Production Polish - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Assembled audiobooks sound professionally mastered with natural pause timing, clean audio processing, verified voice consistency, and ACX-compliant export format. This phase does NOT add new pipeline features — it polishes the existing output into production-quality audio.

</domain>

<decisions>
## Implementation Decisions

### Pause timing & rhythm
- Natural narrator feel — pauses should be organic, slightly varied, never metronomic
- Paragraph breaks get a small pause (0.3-0.6s range) to mirror natural narrator breathing
- Chapter breaks are just a longer silence pause — no chimes or audio cues
- Scene break and chapter break durations: Claude's discretion based on audiobook conventions

### Mastering character
- Transparent/clean processing — should be invisible, just removes problems (noise, peaks) without coloring the sound
- Noise gate: aggressive — dead quiet gaps between phrases, studio clean
- Compression: moderate — tighten dynamic range for comfortable listening without constant volume adjusting
- A/B validation runs automatically, logging before/after metrics (loudness, peak, SNR) and flagging any regressions

### Voice consistency handling
- Check every segment — thorough, not periodic sampling
- When 3 regeneration attempts all fail threshold: keep the best-scoring attempt but flag it as a warning for optional manual review
- Cosine threshold (default 0.60) is configurable via `--voice-threshold` CLI flag for stricter matching when quality matters
- Voice consistency results go in a separate report file (not just inline logging)

### Chapter & file structure
- Generate both per-chapter MP3 files AND a single combined file — user picks what to use
- Full ID3 metadata: title, author, chapter name, cover art (if available from EPUB), genre=Audiobook, track numbers
- File naming: sequential + title from EPUB (e.g., `01-chapter-one.mp3`, `02-the-journey.mp3`)
- Output location: configurable via `--output-dir` flag, default alongside the input EPUB

### Claude's Discretion
- Exact scene break and chapter break pause durations (within natural narrator feel)
- Pedalboard effects chain parameter tuning (gate threshold, compressor ratio, EQ curve)
- Voice consistency report format (JSON vs text)
- Combined file chapter marker implementation
- Crossfade curve shape (linear vs equal-power)

</decisions>

<specifics>
## Specific Ideas

- Pauses should feel like a skilled human narrator — organic rhythm, not robotic timing
- "Studio clean" silence between phrases — no TTS artifacts in gaps
- Moderate compression so listeners don't need to ride the volume control
- The voice consistency report should make it easy to find and review flagged segments after a run

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-production-polish*
*Context gathered: 2026-03-04*
