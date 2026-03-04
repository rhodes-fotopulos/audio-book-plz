# Phase 7: TTS Engine Swap - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace Chatterbox TTS with Qwen3-TTS 1.7B via mlx-audio for all speech synthesis. Larger text chunks (500-600 chars), better voice references (10-15s SNR-filtered with transcripts), and memory-stable full-book synthesis. Chatterbox remains available as a configurable fallback. Emotion system and post-processing are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Voice reference preparation
- Claude's discretion on clip selection strategy (single best clip vs multiple combined)
- Keep existing LibriVox voice bank for Phase 7 — reprocess clips for Qwen3-TTS requirements, upgrade bank later
- Claude's discretion on SNR filter failure strategy (skip vs use with warning)
- Claude's discretion on transcript generation method (Whisper vs manual)

### Fallback policy
- Auto-fallback on Qwen3-TTS failure — if a segment fails with Qwen3, automatically retry with Chatterbox
- Claude's discretion on retry-before-fallback strategy
- Log each fallback event as it happens AND show a summary when the run completes
- Warn user if fallback rate exceeds a threshold, but continue the run (don't abort)

### Chunk splitting
- Never break mid-sentence — always split at sentence boundaries, even if chunk is shorter than 500 chars
- Claude's discretion on merging short paragraphs vs keeping separate
- Split by speaker — separate chunks when speaker changes, even within a paragraph
- Keep both chunking strategies available — new chunker for Qwen3-TTS, old chunker accessible for Chatterbox fallback

### Migration experience
- Auto-archive old v1.0 checkpoints — move to backup folder automatically, then start fresh
- Tag each checkpoint with engine name, version, and settings used (full metadata)
- Full re-run only — don't mix engines in a single audiobook, archive old and re-synthesize everything
- TTS engine configurable as global default with per-project override

### Claude's Discretion
- Voice reference clip selection strategy (single vs multiple)
- SNR filter failure handling
- Transcript generation method
- Retry-before-fallback logic
- Short paragraph merging strategy
- Memory management approach for MLX Metal cache

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-tts-engine-swap*
*Context gathered: 2026-03-04*
