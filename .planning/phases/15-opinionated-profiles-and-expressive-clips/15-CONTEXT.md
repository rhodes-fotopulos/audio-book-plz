# Phase 15: Opinionated Profiles and Expressive Clips - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Each character gets a polarized, distinctive voice profile and a reference clip selected for expressiveness and pace alignment. Covers PROF-01 through PROF-03 and CLIP-01 through CLIP-02. Does NOT add new TTS capabilities, new voice matching logic, or multi-clip-per-character support (CLIP-03 is future).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion

User delegated all implementation decisions to Claude. The following areas are all at Claude's discretion, guided by project conventions and prior decisions:

**Opinionated extraction (PROF-01):**
- How --opinionated modifies EXTRACTION_SYSTEM_PROMPT (separate prompt variant vs appended instructions)
- What vocabulary constraints to enforce (ban "moderate", "medium", "average", "unknown" where evidence exists)
- How extreme to push descriptors while keeping them grounded in literary context

**Distinctiveness pass (PROF-02):**
- Whether to use LLM-based review (send all profiles, ask to push apart) or rule-based field comparison
- Prior context: user prefers LLM approaches over heuristics (Phase 14 decision)
- Single pass vs iterative refinement
- What similarity threshold triggers intervention

**Voice overrides (PROF-03):**
- Scope of voice_overrides.yaml (voice_profile fields, speaker_id, or both)
- YAML schema design
- Validation and error handling for invalid overrides
- Where in the pipeline overrides are applied (must be last per success criteria)

**Clip scoring (CLIP-01, CLIP-02):**
- Whether the defined weights (0.4*SNR + 0.3*pitch_var + 0.2*energy_var + 0.1*rate_match) are hardcoded or configurable
- How to compute pitch/energy variance from WAV files (librosa, parselmouth, or simpler approach)
- Fallback behavior when a speaker has few clips or no clips with good expressiveness scores
- How rate_match maps character pace profile to speaker talking speed

</decisions>

<specifics>
## Specific Ideas

No specific requirements — user delegated all decisions. Open to standard approaches guided by:
- Phase 14 pattern: prefer LLM literary knowledge over complex heuristics
- User runs Qwen 3.5 9B — more capable than originally specced 8B/14B
- Conservative philosophy: better slightly similar than absurdly wrong profiles

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/attribution/extractor.py`: EXTRACTION_SYSTEM_PROMPT (line 43) — needs --opinionated variant for PROF-01
- `src/attribution/models.py`: VoiceProfile with 9 fields (pitch, pace, tone, accent, pace_style, tone_style, energy, typical_emotion, description) — target for opinionated extraction and overrides
- `src/matching/clip_selector.py`: select_reference_clip() scores by duration only (line 72: `score = 1.0 / (1.0 + abs(duration - target))`) — needs complete rework for expressiveness scoring
- `src/attribution/cache.py`: LLM result caching with get_cache_key/check_cache/write_cache — reuse for distinctiveness pass caching
- `src/attribution/llm_client.py`: call_llm_structured for Ollama calls — reuse for LLM-based distinctiveness pass

### Established Patterns
- Pydantic models with model_json_schema() for LLM structured output
- Cache key versioning (e.g., "extraction_v3") for invalidation on prompt changes
- Rich console output for progress/stats display
- CLI flags via typer (--speech-act-fx, --batch-by-character patterns)

### Integration Points
- `src/pipeline.py`: run_attribute() needs --opinionated flag threaded through; run_full_pipeline() needs the flag too
- `src/cli.py`: CLI flag registration for --opinionated
- `src/matching/orchestrator.py`: select_reference_clip() called in step 9 — swap for new expressiveness-aware selector
- voice_overrides.yaml loaded from book_dir, applied after extraction+merge+distinctiveness but before voice matching
- characters.json is the handoff point: extraction writes it, distinctiveness modifies it, overrides patch it, matching reads it

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 15-opinionated-profiles-and-expressive-clips*
*Context gathered: 2026-03-09*
