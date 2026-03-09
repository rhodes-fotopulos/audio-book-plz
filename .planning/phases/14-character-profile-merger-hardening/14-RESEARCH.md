# Phase 14: Character Profile Merger Hardening - Research

**Researched:** 2026-03-09
**Domain:** Character name resolution, entity deduplication, LLM-assisted merge decisions
**Confidence:** HIGH

## Summary

Phase 14 hardens the existing 4-stage character merge pipeline (`merger.py`, 697 lines) to eliminate false-positive merges (cross-contamination) and add full audit trail. The core challenge is the "name form problem" -- distinguishing same-person name variants (Lizzie = Elizabeth) from different-person shared surnames (Mrs. Bennet != Elizabeth Bennet). The user explicitly flagged that the current co-occurrence guard is too blunt: aliases like Lizzie/Elizabeth co-occur in the same chapter but SHOULD merge, while Mrs. Bennet and Elizabeth should NOT.

The user upgraded to Qwen 3.5 9B, which has better reasoning capabilities, making an LLM-first merge strategy more viable than patching heuristics. The current architecture runs heuristic stages first (exact, fuzzy, substring) then LLM consolidation last. Research supports restructuring so the LLM makes the primary merge/reject decision with full context, using heuristics only as candidate generation.

**Primary recommendation:** Restructure the merge pipeline to use heuristics for candidate pair generation and the LLM for accept/reject decisions, with merge_audit.json recording every decision at every stage.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Researcher should investigate both approaches: (1) hardened heuristics-first (current approach) and (2) LLM-first where the LLM handles all merge decisions with full context
- User upgraded to Qwen 3.5 9B which has better reasoning -- makes LLM-first more viable
- Research should compare accuracy vs cost tradeoff for 16GB M4 hardware
- Current 4-stage pipeline (exact, fuzzy, substring, LLM) may be restructured based on research findings
- Core problem: distinguishing "Lizzie = Elizabeth" (same person, merge) from "Mrs. Bennet != Elizabeth Bennet" (different people, don't merge)
- Co-occurrence guard is too blunt -- aliases like Lizzie/Elizabeth co-occur in same chapter but should merge
- Each merge should get a confidence score
- merge_audit.json written alongside characters.json in the book's output directory
- Warn and continue -- print console warning, log to audit JSON, but don't block the pipeline
- MERGE-02 thresholds: >5 aliases, >50 traits, or alias matching another character's canonical name
- Cap at 30 traits after merging, keep primary profile's traits, discard overflow with logged warning
- Add explicit negative examples to EXTRACTION_SYSTEM_PROMPT

### Claude's Discretion
- Audit JSON schema and verbosity level
- Whether merge_overrides.yaml fits Phase 14 or defers
- Merge confidence threshold behavior (flag vs skip)
- Specific negative examples for extraction prompt beyond Bennet family

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MERGE-01 | Per-stage logging of every merge decision (which profiles, why, accepted/rejected) | Audit trail architecture below; MergeDecision model captures all fields |
| MERGE-02 | Post-merge validation flags profiles with >5 aliases, >50 traits, or aliases matching other characters' canonical names | Validation pass runs after all merge stages; warn-and-continue pattern |
| MERGE-03 | Write merge_audit.json alongside characters.json for debugging | JSON schema defined below; written by merge_characters() before returning |
| MERGE-04 | Cross-name exclusion -- before adding an alias, check it against canonical names of all other profiles | Guard added to _merge_two_profiles(); requires passing current profile registry |
| MERGE-05 | Co-occurrence guard on all merge stages (not just stage 4) -- reject merge if both characters appear in same chapter | Build co-occurrence map once at start, pass to all stages; BUT must handle name-form aliases correctly |
| MERGE-06 | Trait count cap at 30 -- if exceeded after merge, keep only primary profile's traits | Applied in _merge_two_profiles() after union; truncate with logged warning |
| MERGE-07 | Surname-only exclusion -- block merges where shared token is a surname but profiles have different titles/first-names | Already implemented in _names_share_surname_only(); needs hardening for edge cases |
| MERGE-08 | Extraction prompt hardening with explicit negative examples | Add negative examples to EXTRACTION_SYSTEM_PROMPT in extractor.py |

</phase_requirements>

## Architecture Patterns

### Recommended Merge Pipeline Restructure

The user wants deeper thinking about whether the entire merge architecture needs rethinking. Based on analysis of the current code and the name-form problem:

**Approach: Hybrid with LLM as Arbiter**

Keep heuristic stages for fast, obvious merges (exact name match is always safe) but elevate the LLM to arbiter for anything ambiguous. This balances cost (LLM calls are slow on local hardware) with accuracy.

```
Stage 1: Exact name match (keep as-is, always correct)
          |
Stage 2: Candidate pair generation (fuzzy + substring + alias)
          - Generate candidate pairs but DON'T auto-merge
          - Each candidate gets a merge_reason string
          |
Stage 3: LLM merge arbiter (NEW - replaces separate fuzzy/substring/LLM stages)
          - Batch candidate pairs to LLM with full context
          - LLM sees: both profiles, shared chapters, name forms, literary context
          - LLM returns: accept/reject + confidence + reasoning per pair
          |
Stage 4: Post-merge validation (MERGE-02)
          - Flag anomalies, warn-and-continue
```

**Why this works better than current approach:**
- Current stages 2-3 auto-merge on heuristic match, causing false positives
- LLM "already knows Lizzie = Elizabeth from literary context" (user's insight)
- Qwen 3.5 9B can handle this reasoning task reliably
- Co-occurrence becomes an input signal to LLM, not a binary gate

**Cost analysis for 16GB M4:**
- Current: 1 LLM call for consolidation (stage 4 only, skipped if <=5 profiles)
- Proposed: 1 LLM call with candidate pairs batch (same cost, better placement)
- Qwen 3.5 9B fits comfortably in 16GB with q8_0 KV cache
- Batch all candidates in one call to minimize overhead

### Recommended Project Structure Changes

```
src/attribution/
    merger.py          # Restructured merge pipeline (modify existing)
    models.py          # Add MergeDecision, MergeAudit models (modify existing)
    extractor.py       # Add negative examples to prompt (modify existing)
```

No new files needed -- all changes are modifications to existing files.

### Audit Trail Architecture

**Recommendation: Full accept+reject log (not decisions-only)**

Rationale: The whole point of merge_audit.json is debugging false merges. You need to see WHY a pair was rejected (e.g., "surname-only match blocked") as much as why it was accepted. The file is per-book and written once -- verbosity cost is negligible.

```python
# New models in models.py

class MergeDecision(BaseModel):
    """A single merge decision in the audit trail."""
    stage: str              # "exact", "candidate_generation", "llm_arbiter", "validation"
    profile_a: str          # Name of first profile
    profile_b: str          # Name of second profile
    action: str             # "merged", "rejected", "flagged"
    reason: str             # Human-readable explanation
    confidence: float       # 0.0-1.0 merge confidence
    details: dict = {}      # Stage-specific metadata (fuzzy score, co-occurrence chapters, etc.)

class MergeAudit(BaseModel):
    """Full audit trail for merge pipeline run."""
    book_title: str
    timestamp: str
    total_raw_profiles: int
    total_merged_profiles: int
    stages: dict[str, list[MergeDecision]]  # stage_name -> decisions
    warnings: list[str]                      # Post-merge validation warnings
    final_profiles: list[str]                # List of canonical names in final output
```

### Co-occurrence Guard Fix

The current `_named_pair_cooccurs()` is fundamentally flawed for the name-form problem:

**Problem:** "Lizzie" and "Elizabeth" co-occur in the same chapter but ARE the same person. The current guard blocks merges when both `is_named=True` and they share a chapter. This correctly blocks "Mr. Bennet" + "Elizabeth Bennet" but ALSO blocks "Lizzie" + "Elizabeth Bennet".

**Solution:** Don't use co-occurrence as a binary gate. Instead, pass it as a SIGNAL to the LLM arbiter:

```python
# In the LLM prompt for merge arbitration:
"These two profiles co-occur in chapters [3, 7, 12].
 Co-occurrence of DIFFERENT characters is common.
 Co-occurrence of name VARIANTS of the same person is also common.
 Use your literary knowledge to determine if these are the same person."
```

The LLM knows that Lizzie is a nickname for Elizabeth from literary context. The LLM also knows Mr. Bennet and Elizabeth Bennet are different people. This is the key insight the user emphasized.

**For heuristic-only stages (Stage 1 exact match):** Co-occurrence is irrelevant -- exact name matches are always the same person.

### Cross-Name Exclusion (MERGE-04)

Before adding an alias to a profile during merge, check it against all OTHER profiles' canonical names. This prevents "Elizabeth" becoming an alias of "Mrs. Bennet".

```python
def _merge_two_profiles(
    primary: CharacterProfile,
    secondary: CharacterProfile,
    all_canonical_names: set[str],  # NEW parameter
) -> CharacterProfile:
    # ... existing merge logic ...

    # MERGE-04: Cross-name exclusion
    blocked_aliases = set()
    for alias in all_aliases:
        if alias.lower().strip() in all_canonical_names:
            blocked_aliases.add(alias)
            # Log to audit: "Blocked alias '{alias}' -- matches canonical name of another profile"
    all_aliases -= blocked_aliases
```

This requires threading the canonical name set through all merge stages, which is straightforward since `merge_characters()` has access to all profiles.

### Trait Count Cap (MERGE-06)

Simple and well-defined:

```python
TRAIT_CAP = 30

def _merge_two_profiles(primary, secondary, ...):
    all_traits = list(dict.fromkeys(
        primary.personality_traits + secondary.personality_traits
    ))
    if len(all_traits) > TRAIT_CAP:
        overflow_count = len(all_traits) - TRAIT_CAP
        logger.warning(
            "Trait overflow for '%s': %d traits exceed cap of %d, "
            "discarding %d overflow traits",
            canonical_name, len(all_traits), TRAIT_CAP, overflow_count,
        )
        all_traits = all_traits[:TRAIT_CAP]  # Keep primary's traits (they come first)
    # ... rest of merge
```

### Extraction Prompt Hardening (MERGE-08)

Add explicit negative examples to `EXTRACTION_SYSTEM_PROMPT` in `extractor.py`. The current prompt already has some alias guidance but lacks concrete wrong/right examples.

**Recommended negative examples:**

```
WRONG examples (DO NOT do this):
- Mrs. Bennet with aliases=["Elizabeth", "Jane", "Lydia"]
  (These are her DAUGHTERS, not aliases for Mrs. Bennet)
- Mr. Darcy with aliases=["Miss Darcy", "Georgiana"]
  (Miss Darcy/Georgiana is his SISTER, a separate character)
- Elizabeth with aliases=["Mrs. Bennet"]
  (Mrs. Bennet is Elizabeth's MOTHER, not an alias)

RIGHT examples:
- Elizabeth Bennet with aliases=["Lizzy", "Eliza", "Miss Bennet"]
  (These are all names for the same person)
- Mr. Darcy with aliases=["Fitzwilliam Darcy", "Darcy"]
  (These are all names for the same person)
- Mrs. Bennet with aliases=[] (no aliases -- other Bennets are separate characters)
```

Additional effective negative examples beyond Bennet family:
- **Shared profession:** "the doctor" should not alias with "Dr. Smith" unless confirmed same person
- **Letter recipients:** "Dear Jane" in a letter FROM Elizabeth does not make Jane an alias of Elizabeth
- **Relational references:** "his wife", "her father" are NOT aliases -- they're ambiguous references

### Merge Confidence Scoring

**Recommendation: Apply low-confidence merges but flag them (not skip)**

Rationale: The user stated "better to have duplicates than wrong merges." However, skipping low-confidence merges entirely creates more work downstream (two voice assignments for one character). Applying-but-flagging lets the user review in merge_audit.json and override if needed.

**Confidence scale:**
- 1.0: Exact name match (always correct)
- 0.9+: LLM says merge with high confidence
- 0.7-0.9: LLM says merge with moderate confidence (apply + flag)
- <0.7: LLM says merge with low confidence (SKIP -- better duplicates than wrong merges)

This gives the user's principle teeth: below 0.7, we don't merge. Above 0.7, we merge but flag anything below 0.9 for review.

### merge_overrides.yaml

**Recommendation: Defer to Phase 15**

Rationale: Phase 15 already has `voice_overrides.yaml` (PROF-03). Manual overrides are a single concern -- character identity overrides (force-merge, force-split) and voice overrides are best designed together. Phase 14 focuses on making the automatic pipeline as good as possible; Phase 15 adds manual escape hatches.

The merge_audit.json from Phase 14 gives users visibility into what happened, which is the prerequisite for knowing what to override.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Name similarity scoring | Custom edit distance | `difflib.SequenceMatcher` (already used) | Handles transpositions, well-tested |
| JSON schema for audit | Manual dict construction | Pydantic `BaseModel` + `model_dump()` | Consistent with project patterns, validates structure |
| Literary name resolution | Complex heuristic rules | LLM arbiter (Qwen 3.5 9B) | LLM already knows literary name forms; heuristics can't cover edge cases |

**Key insight:** The user's core observation is correct -- the LLM already has literary knowledge that heuristics can never replicate. "Lizzie = Elizabeth" is trivial for an LLM but requires a lookup table for heuristics. The engineering challenge is making the LLM call efficient and auditable, not building better heuristics.

## Common Pitfalls

### Pitfall 1: Greedy Pairwise Merge Order Sensitivity
**What goes wrong:** When merging A into B, then B into C, the final profile depends on which pair was processed first. The canonical name, traits, and description can differ based on order.
**Why it happens:** The current `_merge_by_fuzzy` and `_merge_by_substring_and_alias` iterate sequentially and merge greedily.
**How to avoid:** For heuristic stage 1 (exact match), order doesn't matter (all instances are identical names). For LLM-arbitrated merges, process all accepted pairs at once using group-based merging (as the current consolidation stage already does).
**Warning signs:** Different results on re-runs with same input (non-deterministic iteration).

### Pitfall 2: Alias Cascading Creates Cross-Contamination
**What goes wrong:** Profile A gets alias "Bob" from a merge. Later, profile C also has alias "Bob". Now A and C merge via alias overlap, even though they're different people.
**Why it happens:** `_alias_overlap()` checks alias sets without considering WHY an alias was added.
**How to avoid:** MERGE-04 cross-name exclusion prevents the worst cases. Additionally, aliases added during merge should be treated with lower confidence than original aliases.
**Warning signs:** Post-merge profiles with >5 aliases (MERGE-02 threshold).

### Pitfall 3: Co-occurrence Guard Blocks Valid Merges
**What goes wrong:** Nicknames co-occur with formal names in the same chapter (Lizzie and Elizabeth both appear in chapter 3). The co-occurrence guard blocks the merge.
**Why it happens:** The guard assumes co-occurrence means different people, but name variants of the same person also co-occur.
**How to avoid:** Use co-occurrence as a signal to the LLM, not a binary gate. The LLM can distinguish "these are two names for the same person" from "these are two different people who both appear."
**Warning signs:** Known-same characters appearing as duplicates in output.

### Pitfall 4: LLM Hallucinating Merge Groups
**What goes wrong:** The LLM proposes merging characters that are clearly distinct because it over-indexes on shared attributes.
**Why it happens:** The consolidation prompt asks "which are the same person?" which biases toward finding duplicates.
**How to avoid:** Frame the prompt as "are these two specific characters the same person? Default to NO." Process pairs, not groups. Require explicit reasoning. Validate against co-occurrence data.
**Warning signs:** Merged profiles with contradictory attributes (e.g., both "male" and "female").

### Pitfall 5: Cache Invalidation After Prompt Changes
**What goes wrong:** After changing the extraction or consolidation prompt (MERGE-08), cached LLM results still use the old prompt.
**Why it happens:** Cache key is based on input text hash, not prompt content.
**How to avoid:** Include a version suffix in the cache key namespace. The current `get_cache_key(summary, "consolidation")` should become `get_cache_key(summary, "consolidation_v2")` after prompt changes. Already partially done -- extraction uses `"extraction_v2"`.
**Warning signs:** No behavior change after prompt updates when cache exists.

## Code Examples

### MergeDecision Recording Pattern
```python
# Source: project patterns from models.py + merger.py
def _record_decision(
    audit: MergeAudit,
    stage: str,
    profile_a: CharacterProfile,
    profile_b: CharacterProfile,
    action: str,
    reason: str,
    confidence: float,
    details: dict | None = None,
) -> None:
    """Record a merge decision in the audit trail."""
    decision = MergeDecision(
        stage=stage,
        profile_a=profile_a.name,
        profile_b=profile_b.name,
        action=action,
        reason=reason,
        confidence=confidence,
        details=details or {},
    )
    audit.stages.setdefault(stage, []).append(decision)
```

### LLM Merge Arbiter Prompt Pattern
```python
# Source: adapted from existing CONSOLIDATION_SYSTEM_PROMPT
MERGE_ARBITER_PROMPT = """\
You are a character identity specialist for novels. For each candidate pair, \
determine if they are the SAME person or DIFFERENT people.

Rules:
- Default to DIFFERENT unless you are confident they are the same person.
- Nicknames and formal names of the same person should be merged \
  (e.g. "Lizzy" and "Elizabeth Bennet" are the same person).
- Characters who share a surname are usually DIFFERENT people \
  (e.g. "Mr. Bennet" and "Elizabeth Bennet" are father and daughter).
- Titles change but the person doesn't: "Miss Darcy" and "Georgiana Darcy" \
  are the same person.
- "Mr. Bennet" and "Mrs. Bennet" are ALWAYS different (husband and wife).

For each pair, return:
- decision: "merge" or "reject"
- confidence: 0.0-1.0
- reasoning: brief explanation
"""
```

### Post-Merge Validation Pattern
```python
# Source: project patterns
def _validate_merged_profiles(
    profiles: list[CharacterProfile],
    audit: MergeAudit,
) -> list[str]:
    """MERGE-02: Validate merged profiles and return warnings."""
    warnings: list[str] = []
    canonical_names = {p.name.lower().strip() for p in profiles}

    for profile in profiles:
        # Check alias count
        if len(profile.aliases) > 5:
            w = f"WARNING: '{profile.name}' has {len(profile.aliases)} aliases (threshold: 5)"
            warnings.append(w)
            logger.warning(w)

        # Check trait count (should already be capped by MERGE-06, but validate)
        if len(profile.personality_traits) > 50:
            w = f"WARNING: '{profile.name}' has {len(profile.personality_traits)} traits (threshold: 50)"
            warnings.append(w)
            logger.warning(w)

        # Check alias-canonical cross-contamination
        for alias in profile.aliases:
            if alias.lower().strip() in canonical_names and alias.lower().strip() != profile.name.lower().strip():
                w = f"WARNING: '{profile.name}' has alias '{alias}' matching another character's canonical name"
                warnings.append(w)
                logger.warning(w)

    return warnings
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 4-stage auto-merge pipeline | LLM-arbitrated merge with heuristic candidate generation | Phase 14 (planned) | Eliminates false-positive merges from heuristic stages |
| Co-occurrence as binary gate | Co-occurrence as signal to LLM | Phase 14 (planned) | Stops blocking valid name-variant merges |
| No audit trail | Full merge_audit.json | Phase 14 (planned) | Every merge decision debuggable |
| Unlimited traits after merge | 30-trait cap | Phase 14 (planned) | Prevents profile bloat |

## Open Questions

1. **LLM batch size for merge arbitration**
   - What we know: Current consolidation sends ALL profiles in one call. Candidate pair approach could have many pairs.
   - What's unclear: Whether Qwen 3.5 9B can reliably reason about 20+ candidate pairs in a single call within the 32K context window.
   - Recommendation: Start with batching all pairs in one call (most efficient). If accuracy drops, split into batches of 10 pairs. The audit trail will reveal if batch size affects quality.

2. **Exact threshold for confidence-based skip**
   - What we know: User wants "better duplicates than wrong merges." LLM confidence scores are not perfectly calibrated.
   - What's unclear: Where exactly the confidence threshold should be (0.7 recommended above, but may need tuning).
   - Recommendation: Start at 0.7, log all decisions to audit. Tunable via constant, adjust after reviewing real merge_audit.json outputs.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none (discovered via pyproject.toml, no pytest section) |
| Quick run command | `python -m pytest tests/test_merger.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MERGE-01 | Per-stage logging of merge decisions | unit | `python -m pytest tests/test_merger.py::TestAuditTrail -x` | No -- Wave 0 |
| MERGE-02 | Post-merge validation flags anomalies | unit | `python -m pytest tests/test_merger.py::TestPostMergeValidation -x` | No -- Wave 0 |
| MERGE-03 | merge_audit.json written alongside characters.json | unit | `python -m pytest tests/test_merger.py::TestAuditOutput -x` | No -- Wave 0 |
| MERGE-04 | Cross-name exclusion blocks alias-canonical conflicts | unit | `python -m pytest tests/test_merger.py::TestCrossNameExclusion -x` | No -- Wave 0 |
| MERGE-05 | Co-occurrence signal passed to all stages | unit | `python -m pytest tests/test_merger.py::TestCooccurrenceSignal -x` | No -- Wave 0 |
| MERGE-06 | Trait cap at 30, overflow discarded with warning | unit | `python -m pytest tests/test_merger.py::TestTraitCap -x` | No -- Wave 0 |
| MERGE-07 | Surname-only exclusion blocks different-title merges | unit | `python -m pytest tests/test_merger.py::TestSurnameExclusion -x` | No -- Wave 0 |
| MERGE-08 | Extraction prompt contains negative examples | unit | `python -m pytest tests/test_merger.py::TestExtractionPrompt -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_merger.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_merger.py` -- new file covering MERGE-01 through MERGE-08
- [ ] Test fixtures for CharacterProfile, VoiceProfile creation helpers (follow pattern from test_dedup.py)
- [ ] No framework install needed (pytest already in project)

## Sources

### Primary (HIGH confidence)
- `src/attribution/merger.py` -- full existing merge pipeline (697 lines), all 4 stages analyzed
- `src/attribution/models.py` -- CharacterProfile, VoiceProfile, ConsolidationResult, DuplicateGroup models
- `src/attribution/extractor.py` -- EXTRACTION_SYSTEM_PROMPT (current version, line 43)
- `src/attribution/llm_client.py` -- call_llm_structured, Qwen 3.5 9B configuration, 32K context window
- `src/attribution/cache.py` -- cache key patterns (namespace-based)
- `tests/test_dedup.py` -- existing test patterns for voice dedup (analogous problem domain)

### Secondary (MEDIUM confidence)
- User's CONTEXT.md decisions -- Qwen 3.5 9B upgrade, LLM-first viability, co-occurrence guard limitations
- PROJECT.md -- hardware constraints (16GB M4), tech stack (Ollama, Pydantic)

### Tertiary (LOW confidence)
- Merge confidence threshold of 0.7 -- reasonable starting point but needs empirical tuning per real book runs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new dependencies needed
- Architecture: HIGH -- restructure is well-defined, existing code thoroughly analyzed
- Pitfalls: HIGH -- identified from actual code analysis and user-reported issues
- Confidence thresholds: MEDIUM -- 0.7 threshold needs empirical validation

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable domain, no external dependency changes)
