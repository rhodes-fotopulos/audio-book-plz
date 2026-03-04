# Phase 8: LLM Intelligence and Emotion - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Upgrade LLM to 14B with automatic fallback, add hybrid regex+LLM dialogue detection with speech-act subtype tagging (spoken/thought/shouted/whispered), and build a three-layer emotion system (voice baseline, scene mood, line-level override) that feeds post-processing parameters into synthesis. New capability types (e.g., singing detection, narrator style switching) are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Speech-act detection
- Four speech-act types only: spoken, thought, shouted, whispered — no additional subtypes
- Internal monologue (thoughts) rendered in character's own voice with softer tone, not switched to narrator
- Indirect dialogue stays as narration — only directly quoted speech gets character voices
- When regex and LLM disagree on a tag, LLM wins — it understands context better than pattern matching

### Emotion layer design
- Layer 1 (voice baselines): Rich personality descriptions per character — 3-5 descriptors covering pace, tone, energy, typical emotion
- Layer 2 (scene mood): Every scene gets a mood+intensity annotation, including neutral scenes — neutral is useful information
- Layer 3 (line-level overrides): High threshold only — triggered by extreme emotional shifts (e.g., joke at a funeral, scream in calm scene). Most lines follow scene mood without override.
- Emotion taxonomy: Fixed predefined set of emotion categories (6-10) that map cleanly to post-processing parameters. No free-form descriptions.

### Post-processing parameters
- Whispered lines: Subtle volume reduction (-3 to -6 dB) — noticeably quieter but still clearly audible
- Shouted lines: Volume boost (+3 to +6 dB) with slight speed increase — feels urgent without being harsh
- Thought lines: Slightly slower pace + quieter volume — reflective, introspective feel
- Spoken lines: No adjustments (baseline)
- Adjustments are absolute per speech-act type, NOT cumulative with scene mood — simpler and more predictable

### LLM model handling
- Pre-check available RAM before loading — if below threshold, go straight to 8B without attempting 14B load
- Warn user when fallback to 8B occurs: clear message about reduced attribution quality
- Model stays resident by default (load once, reuse across LLM phases), with --low-memory config toggle to unload between phases
- Config option (--model flag or config setting) to override model selection — power users can force 8B or specify custom Ollama model name

### Claude's Discretion
- Exact fixed emotion set (which 6-10 emotions to include)
- RAM threshold for 14B vs 8B decision
- Regex patterns for initial dialogue detection pass
- How voice baseline descriptions are structured in output JSON
- Scene boundary detection heuristics

</decisions>

<specifics>
## Specific Ideas

- Thoughts should feel like the character talking to themselves, not a narrator describing what they think
- Post-processing should be noticeable but not jarring — the listener shouldn't feel like the volume is being manually adjusted
- The whole system should degrade gracefully: if emotion tagging fails for a line, it should just play as normal spoken dialogue

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-llm-intelligence-and-emotion*
*Context gathered: 2026-03-04*
