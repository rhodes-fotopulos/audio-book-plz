# Phase 11: Data Model Unification and Voice Matching - Context

**Gathered:** 2026-03-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Merge duplicated voice fields (VoiceQualities + VoiceBaseline) into a single VoiceProfile model on CharacterProfile. Update LLM extraction to produce the unified schema directly. Feed the richer unified data to both trait_matcher (LLM) and embedding_matcher. No migration needed — old characters.json files will be regenerated.

</domain>

<decisions>
## Implementation Decisions

### VoiceProfile field design
- Flat model with both coarse and rich descriptor fields (no nesting)
- Coarse traits (pitch, pace, tone, accent) align with LibriTTS-P annotation vocabulary for embedding matching
- Rich descriptors (energy, typical_emotion, description, pace_style, tone_style) provide nuance for LLM casting
- Single field per concept — when overlap exists (pace, tone), prefer the richer descriptor but keep coarse version with distinct naming convention
- All information preserved from both old models — no data loss

### Migration strategy
- No migration needed — user has no existing users and will regenerate all data
- Delete VoiceQualities and VoiceBaseline classes entirely
- CharacterProfile gets a single `voice_profile: VoiceProfile` field replacing both `voice_qualities` and `voice_baseline`
- Clean break, no backward compatibility code

### Matcher description richness
- trait_matcher (LLM): Send full VoiceProfile to LLM casting prompt — all coarse traits AND rich descriptors. Same casting-director prompt style, just more character info in the character block
- embedding_matcher: Claude's discretion on whether to embed coarse traits only (aligned with LibriTTS-P vocabulary) or full profile
- Keep character descriptions concise even with more fields — minimize input tokens to LLM
- Matching logs: Claude's discretion on verbosity level

### LLM extraction update
- Update extraction prompt and Pydantic schema to produce VoiceProfile directly in one pass (no post-hoc merge of old formats)
- Single-pass extraction — Qwen 3.5 9B/4B handles structured output well, 9 fields is reasonable
- Use "unknown" defaults for fields the LLM can't determine from text
- Vocabulary guidance for coarse traits: Claude's discretion on whether to include LibriTTS-P example vocabulary in the prompt or normalize afterward
- Merger logic: redesign to intelligently combine VoiceProfile fields across chapters (not just keep-first — weight or reconcile conflicting descriptions)

### Claude's Discretion
- Embedding matcher text composition (coarse-only vs full profile vs concatenation)
- Whether to include LibriTTS-P vocabulary examples in extraction prompt or normalize afterward
- Matching log verbosity level
- Exact VoiceProfile field names for coarse vs rich disambiguation

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/attribution/models.py`: VoiceQualities (lines 22-43), VoiceBaseline (lines 49-73), CharacterProfile (lines 75-110) — all getting replaced/updated
- `src/attribution/llm_client.py`: call_llm_structured() — reusable for updated extraction schema
- `src/matching/trait_matcher.py`: _build_character_description() (line 100) — needs update to use VoiceProfile
- `src/matching/embedding_matcher.py`: _build_character_text() (line 66) — needs update to use VoiceProfile
- `src/matching/models.py`: SpeakerAnnotation with trait_text field — the target vocabulary for coarse traits

### Established Patterns
- Pydantic BaseModel with ConfigDict(strict=True) for all value objects
- LLM structured output via Ollama format parameter + model_json_schema()
- Per-chapter extraction → merger → final characters.json pipeline
- Two-tier matching: LLM for major characters, embedding fallback for minor/overflow

### Integration Points
- `src/attribution/extractor.py`: LLM extraction prompts — need schema update
- `src/attribution/merger.py`: Character profile merging — needs new merge strategy for VoiceProfile fields
- `src/matching/orchestrator.py`: Consumes CharacterProfile, passes to matchers
- `src/attribution/emotion/`: Scene mood and overrides system — will consume VoiceProfile in Phase 12+

</code_context>

<specifics>
## Specific Ideas

- LibriTTS-P speakers use annotation vocabulary like "masculine", "tensed", "slightly clear", "cool", "intellectual", "calm", "slightly reassuring" — coarse traits should align with this style
- User is running Qwen 3.5 9B/4B (newer than the Qwen3 14B/8B noted in PROJECT.md) — better structured output reliability
- User wants to minimize LLM input/output tokens while still getting richer matching data

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 11-data-model-unification-and-voice-matching*
*Context gathered: 2026-03-06*
