# Phase 2: LLM Character Extraction and Speaker Attribution - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Extract character profiles from novel text and attribute every dialogue line to a speaker via local LLM (Qwen3 8B). Produces `characters.json` (character registry) and `attributed.json` (segments with speaker fields). Voice matching, synthesis, and assembly are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Character profile depth
- Rich descriptions: gender, age range, vocal qualities (pitch, pace, tone), personality traits, and accent if mentioned in text
- Infer traits from context when reasonable (e.g., "the old man grumbled" implies elderly male, gravelly voice) — no need to flag inferences separately
- Single snapshot per character — no evolution tracking across the book
- Include character relationships (e.g., "mother of X", "rival of Y") to help disambiguate dialogue in group scenes

### Unknown speaker policy
- Always assign a best-guess speaker with a confidence score — never leave a line unattributed
- Claude's discretion on the confidence threshold that would flag items for optional review
- Narrator reads ALL internal monologue and thought passages — only spoken-aloud dialogue gets character voices
- Infer turn-taking in rapid untagged back-and-forth dialogue using conversation flow and context

### Minor character handling
- No threshold — every named character gets a full profile regardless of line count
- Unnamed speakers (e.g., "the bartender", "a soldier") get generic profiles with placeholder identities and inferred traits
- Aggressively merge unnamed references that likely refer to the same person (e.g., "the old man" in Ch.1 later revealed as "Mr. Wilson")
- Group dialogue ("they all shouted", "the crowd cheered") attributed to narrator

### User review touchpoints
- No mandatory pause — pipeline continues automatically after attribution completes
- Stats overview printed after completion: character count, dialogue lines attributed, confidence distribution, any unknowns
- JSON output is human-readable (pretty-printed with indentation) for easy spot-checking
- Re-runs overwrite previous results — no versioning or backups

### Claude's Discretion
- Confidence score threshold for flagging low-confidence attributions
- LLM prompting strategy and context window management
- Chapter caching implementation for incremental re-runs
- Alias detection heuristics

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

*Phase: 02-llm-character-extraction-and-speaker-attribution*
*Context gathered: 2026-03-03*
