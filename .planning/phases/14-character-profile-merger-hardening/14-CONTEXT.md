# Phase 14: Character Profile Merger Hardening - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Eliminate false-positive merges in the character profile merger, add full audit trail, and harden all merge stages. Covers MERGE-01 through MERGE-08. Does NOT add opinionated profiles, expressive clips, or voice overrides (those are Phase 15).

</domain>

<decisions>
## Implementation Decisions

### Merge strategy
- Researcher should investigate both approaches: (1) hardened heuristics-first (current approach) and (2) LLM-first where the LLM handles all merge decisions with full context
- User upgraded to Qwen 3.5 9B which has better reasoning — makes LLM-first more viable
- Research should compare accuracy vs cost tradeoff for 16GB M4 hardware
- Current 4-stage pipeline (exact → fuzzy → substring → LLM) may be restructured based on research findings

### Name form intelligence
- Core problem: distinguishing "Lizzie = Elizabeth" (same person, merge) from "Mrs. Bennet ≠ Elizabeth Bennet" (different people, don't merge)
- Co-occurrence guard is too blunt — aliases like Lizzie/Elizabeth co-occur in same chapter but should merge
- Researcher should investigate what signals reliably distinguish same-person name forms from different-person shared surnames
- The existing `is_named` flag and `_names_share_surname_only` heuristics are starting points but insufficient

### Merge confidence scoring
- Each merge should get a confidence score
- Claude's Discretion: decide whether low-confidence merges are applied-but-flagged or skipped entirely, based on what research reveals about accuracy tradeoffs
- Principle: better to have duplicates (two voices for one character) than wrong merges (one voice for two characters)

### Audit trail
- merge_audit.json written alongside characters.json in the book's output directory
- Claude's Discretion: decide verbosity level (decisions-only vs full accept+reject log) based on what downstream debugging needs

### Post-merge validation
- Warn and continue — print console warning, log to audit JSON, but don't block the pipeline
- User reviews audit after the run
- MERGE-02 thresholds: >5 aliases, >50 traits, or alias matching another character's canonical name

### Manual merge overrides
- Claude's Discretion: decide whether merge_overrides.yaml belongs in Phase 14 or should be deferred (Phase 15 already has voice_overrides.yaml — may make sense to bundle or keep separate)

### Trait overflow (MERGE-06)
- Cap at 30 traits after merging
- Keep primary profile's traits, discard overflow with logged warning (per requirement)

### Extraction prompt hardening (MERGE-08)
- Add explicit negative examples to EXTRACTION_SYSTEM_PROMPT
- Include Bennet family example and other edge cases (research should identify the most impactful negative examples)

### Claude's Discretion
- Audit JSON schema and verbosity level
- Whether merge_overrides.yaml fits Phase 14 or defers
- Merge confidence threshold behavior (flag vs skip)
- Specific negative examples for extraction prompt beyond Bennet family

</decisions>

<specifics>
## Specific Ideas

- User explicitly flagged that co-occurrence is fundamentally flawed as a merge signal — "Lizzie and Elizabeth will be in the same chapter but should be merged, and others should not like Mrs. Bennet and Elizabeth"
- User wants the merge problem thought about more deeply rather than patching the current approach — research should explore whether the entire merge architecture needs rethinking
- User is now on Qwen 3.5 9B (not 14B/8B listed in PROJECT.md) — this affects what the LLM can handle in merge decisions
- The LLM "already knows Lizzie = Elizabeth from literary context" — leveraging the model's literary knowledge is preferred over building complex heuristics

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/attribution/merger.py`: Full 4-stage merge pipeline (697 lines) — exact, fuzzy, substring, LLM consolidation
- `src/attribution/models.py`: CharacterProfile, VoiceProfile, ConsolidationResult, DuplicateGroup models
- `src/attribution/cache.py`: LLM result caching (check_cache, get_cache_key, write_cache)
- `src/attribution/llm_client.py`: call_llm_structured for Ollama calls
- `src/attribution/extractor.py`: EXTRACTION_SYSTEM_PROMPT (line 43) — needs MERGE-08 negative examples

### Established Patterns
- SequenceMatcher for fuzzy matching (threshold 0.85, 0.90 for short names)
- `_names_share_surname_only()` for surname-based merge prevention
- `_named_pair_cooccurs()` for co-occurrence guard (only blocks when both is_named=True)
- `_merge_two_profiles()` for combining two profiles (longer name as canonical, union aliases/traits)
- Pydantic models with `model_json_schema()` for LLM structured output

### Integration Points
- `merge_characters()` called from pipeline with `chapter_characters` dict and `cache_dir`
- Output is `list[CharacterProfile]` written to `characters.json`
- merge_audit.json will be a new output file alongside characters.json
- CONSOLIDATION_SYSTEM_PROMPT (line 365) feeds the LLM consolidation stage

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 14-character-profile-merger-hardening*
*Context gathered: 2026-03-09*
