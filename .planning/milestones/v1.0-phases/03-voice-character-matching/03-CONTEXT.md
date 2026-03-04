# Phase 3: Voice-Character Matching - Context

**Gathered:** 2026-03-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Match each character to a real human voice from LibriTTS-P and lock the voice map before synthesis begins. Users review assignments via CLI table and confirm or edit voice_map.json. No two major characters share a speaker. Synthesis, audio assembly, and voice cloning tuning are separate phases.

</domain>

<decisions>
## Implementation Decisions

### Voice matching priorities
- Balanced blend of gender, age, and vocal quality — no single factor dominates
- Distinctiveness between characters is prioritized — swap a less-perfect individual match for more contrast when two characters sound too similar
- Under-described characters: infer traits from scene context, dialogue style, and relationships (best effort)
- LLM includes brief reasoning for each assignment (e.g., "Matched because gruff, older male, authoritative tone")

### Narrator voice
- Narrator voice matches the book's tone — a dark thriller gets a lower/tense narrator, a comedy gets a lighter voice
- Narrator gender: Claude decides per book based on content and tone
- Smart narrator default: first-person novels → protagonist's voice IS the narrator; third-person → separate dedicated narrator voice
- Narrator sourced from same LibriTTS-P speaker pool as characters (not a fixed/external voice)

### Review experience
- CLI table printed before locking: shows character name, LibriTTS-P speaker ID, and LLM reasoning per row
- User confirms with y/n prompt before voice_map.json is written
- No interactive override — user edits voice_map.json directly, then re-runs match to validate
- Rejection flow: exit with instructions telling user to edit voice_map.json and re-run

### Cast grouping
- Major vs minor defined by dialogue line count
- Minor characters can share a voice, but never two characters who appear in the same chapter
- When speaker pool runs out of good matches: assign with a warning flag in voice_map.json so user knows which matches are weak

### Claude's Discretion
- Exact dialogue count threshold for major/minor classification (tuned per book size)
- Narrator gender selection logic per book
- Embedding similarity fallback implementation details
- Confidence scoring methodology

</decisions>

<specifics>
## Specific Ideas

- Voice assignments should feel like casting — the reasoning should read like "this actor for this role because..."
- First-person narrator = protagonist voice is a strong UX signal that the book "sounds right"
- Warning flags on weak matches let the user decide if they care enough to manually fix

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-voice-character-matching*
*Context gathered: 2026-03-03*
