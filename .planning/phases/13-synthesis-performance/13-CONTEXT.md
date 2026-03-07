# Phase 13: Synthesis Performance - Context

**Gathered:** 2026-03-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Synthesis runs faster by caching voice reference encodings per character and enabling per-character batch ordering. This is the final phase of v1.2 — pure performance optimization with no output changes.

Two requirements:
- SYNTH-05: Precomputed reference encoding cached per character, reused across all segments
- SYNTH-06: `--batch-by-character` flag for per-character synthesis ordering with post-hoc chapter stitching

</domain>

<decisions>
## Implementation Decisions

### Reference encoding cache (SYNTH-05)
- Currently `qwen_engine.py` receives `ref_clip_path` and `ref_transcript` per segment and re-processes the reference audio every call
- Cache the encoded reference representation per character so the reference audio is processed once per character, not once per segment
- Cache lives in memory during the synthesis run (not persisted to disk) — synthesis already has checkpoint/resume for crash recovery
- Cache key: character name or speaker ID (maps 1:1 to voice reference clip)
- The cache must work transparently — no user action required, always enabled
- Visible in logs: "Cached reference encoding for {character}" on first use, "Using cached reference for {character}" on subsequent

### Batch-by-character ordering (SYNTH-06)
- Add `--batch-by-character` CLI flag (default OFF — chapter-by-chapter remains default)
- When enabled: group all segments by speaker, synthesize all segments for each character consecutively, then reorder output back into chapter/segment order for assembly
- Benefit: keeps MLX model "warmed" for each voice's reference encoding, reduces memory thrashing between different voice profiles
- Final audiobook output must be byte-identical regardless of synthesis order — ordering is purely a synthesis-time optimization
- Progress display when batching: show character name + segment count instead of chapter progress (e.g., "Character: Alice [15/42 segments]")
- Checkpoint/resume must work correctly with batch ordering — completed segment IDs are tracked by segment_id, not position

### Flag wiring
- `--batch-by-character` flag added to CLI `synthesize` and `convert` commands
- Wired through `run_synthesize()` and `run_full_pipeline()` in pipeline.py
- SynthesisConfig gets `batch_by_character: bool = False` field
- Synthesizer reads config to determine iteration order

### Claude's Discretion
- Exact MLX/mlx-audio API for extracting and reusing encoded reference representations
- Whether reference caching requires engine-level changes or can be done at synthesizer level
- Progress display layout details for batch-by-character mode
- Whether to add timing logs showing reference cache hit savings

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/synthesis/qwen_engine.py`: `generate()` method (line 84) — takes ref_clip_path per call, needs caching layer
- `src/synthesis/synthesizer.py`: Main loop (line 245) iterates chapter-by-chapter — needs batch-by-character alternative path
- `src/synthesis/checkpoint.py`: Segment-based checkpoint tracking — already uses segment IDs, should work with reordered synthesis
- `src/synthesis/models.py`: SynthesisConfig dataclass — add batch_by_character field here
- `src/synthesis/progress.py`: SynthesisProgress class — needs character-mode display variant

### Established Patterns
- Feature flags wired through CLI -> pipeline.py -> SynthesisConfig -> synthesizer (established in Phase 12 with speech_act_fx)
- Engine abstraction via TTSEngineBase / create_engine() — changes may need to go in base class
- Voice lookup dict built from VoiceMap at synthesizer.py line 130 — maps speaker name to clip_path + transcript
- MLX Metal cache limit already managed in qwen_engine.py (line 57-61)

### Integration Points
- `src/synthesis/synthesizer.py:run_synthesis()` — main entry point, receives SynthesisConfig
- `src/synthesis/qwen_engine.py:generate()` — per-segment generation, ref_clip_path passed each time
- `src/cli.py` — synthesize and convert commands need --batch-by-character flag
- `src/pipeline.py` — run_synthesize() and run_full_pipeline() need batch_by_character parameter

</code_context>

<specifics>
## Specific Ideas

- Reference caching is the higher-impact optimization — every segment currently re-encodes the same voice reference
- Batch-by-character may compound the benefit by reducing MLX cache thrashing between different voice encodings
- The voice_lookup dict (synthesizer.py line 130) already maps speakers to clips — natural place to build the reference cache
- Prior phases established: Qwen3-TTS Base model via mlx-audio, 16GB M4 Mac, sequential LLM/TTS phases

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 13-synthesis-performance*
*Context gathered: 2026-03-07*
