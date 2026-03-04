# Phase 4: TTS Synthesis with Checkpoint/Resume - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Synthesize per-segment WAV files using Chatterbox on Apple Silicon MPS, with crash recovery and progress tracking for overnight unattended runs. Each segment is voiced by its assigned character's reference clip from the voice map. Assembly into chapter/book MP3s is Phase 5.

</domain>

<decisions>
## Implementation Decisions

### Progress display
- Default: chapter-level progress bar ("Chapter 3/24 — segment 47/312")
- Verbose mode (-v): adds per-segment detail (character name, duration, time taken) as scrolling log
- Show ETA based on rolling average time per segment, updating as it goes
- On completion: Rich stats table — chapters completed, total segments, total audio duration, failures, wall-clock time
- Always write a synthesis.log file alongside WAVs for morning-after debugging

### Voice tuning parameters
- Exaggeration: Claude's discretion for sensible audiobook default
- Per-character overrides supported in voice_map.json, with global defaults as fallback
- CFG/guidance weight: lean natural — prioritize natural-sounding speech over precise text adherence
- Different defaults for narration vs dialogue: lower exaggeration for narration, higher for dialogue, automatic based on segment type

### Failure behavior
- Segment failure: retry 2-3 times, then skip. Collect failures for a retry pass at end of run
- Hard crash (GPU OOM, MPS error): auto-restart Chatterbox once and resume from last checkpoint. If second crash, exit cleanly with checkpoint saved
- Partial/corrupted WAVs: delete and re-queue for synthesis (minimum duration check)
- Failure threshold: configurable — stop the entire run if failure rate exceeds threshold (prevents burning hours on a broken run)

### Run modes
- Single-chapter mode: `synthesize --chapter 3` to process just one chapter (useful for voice testing)
- Dry run mode: `synthesize --dry-run` shows segment count, estimated time, disk space needed
- Re-synthesis: delete the WAV file and re-run — checkpoint detects missing file and regenerates (no special segment-ID flag)
- Ollama auto-unload: automatically detect running Ollama, unload models to free GPU memory before Chatterbox loads

### Claude's Discretion
- Exact Chatterbox exaggeration default value
- CFG/guidance weight default value
- Narration vs dialogue exaggeration split values
- Failure threshold default percentage
- Retry count (2 or 3)
- Checkpoint file format and naming
- WAV file naming convention
- synthesis.log format

</decisions>

<specifics>
## Specific Ideas

- Overnight unattended operation is the primary use case — everything should work without user intervention
- Progress display inspired by build tools: chapter-level bar by default, verbose for debugging
- The "morning after" experience matters: clear summary table + log file to understand what happened

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-tts-synthesis-with-checkpoint-resume*
*Context gathered: 2026-03-03*
