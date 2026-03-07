# Phase 12: Expression System Core (Revised: Emotion Removal and LLM Optimization) - Research

**Researched:** 2026-03-06
**Domain:** Pipeline simplification, feature flag wiring, LLM result caching
**Confidence:** HIGH

## Summary

Phase 12 has been fundamentally rescoped from its original "Expression System Core" design. Research during the context session confirmed that Qwen3-TTS Base model cannot combine voice cloning with emotion/style instructions -- this is an architectural limitation of the model. The LUFS normalization at -19.0 in the mastering chain further undermines volume-based expression deltas. Consequently, the emotion annotation system (scene moods + line overrides) is being removed entirely, speech-act post-processing is being made opt-in (default OFF), the speech-act LLM refinement pass is being made optional (default regex-only), and trait matcher LLM results are being cached.

This phase is primarily a deletion and simplification phase. The codebase has clear, well-structured modules with known file locations. The existing `src/attribution/cache.py` provides a proven caching pattern (SHA-256 content hash + JSON file cache with atomic writes) that will be reused for trait matcher caching. The ROADMAP.md and REQUIREMENTS.md also need updates to reflect the milestone restructure from 5 phases (11-15) down to 3 phases (11-13).

**Primary recommendation:** Execute as sequential deletions, then flag additions, then cache implementation, then doc updates. Each step is independently testable.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Delete `src/attribution/emotion/` directory entirely (scene_mood.py, overrides.py, models.py, __init__.py)
- Remove emotion annotation block from `src/pipeline.py` (lines 223-306): scene mood LLM calls, line override LLM calls, emotion.json writing, failure reporting
- Remove `from src.attribution.emotion import annotate_scene_moods, detect_overrides` from pipeline.py
- Remove emotion.json output -- no longer produced by the attribution phase
- Remove any references to emotion.json in CLI, docs, or other modules
- Existing emotion.json files in output directories are simply ignored (no cleanup needed)
- Delete `tests/test_emotion.py`
- Add `--speech-act-fx` CLI flag to enable speech-act post-processing (volume/speed adjustments for whispered/shouted/thought)
- Default: OFF -- the TTS engine's natural prosody is trusted; LUFS normalization undoes most volume deltas anyway
- When OFF: speech-act tags still present in attributed.json (tagging is cheap), but no audio modification in synthesis
- Keep `src/synthesis/post_processor.py` -- code stays, just gated behind the flag
- Keep `src/attribution/speech_acts.py` -- regex+LLM tagging still runs (tags are useful metadata)
- Make the speech-act LLM pass optional -- add flag or config to skip LLM refinement and use regex-only classification
- Default: regex-only (skip LLM). Since post-processing is off by default, the precision gain from LLM refinement is marginal
- Cache trait_matcher LLM results based on character profile hash
- Re-running `match` on the same book with unchanged characters skips LLM casting calls
- Collapse remaining phases from 5 (11-15) to 3 (11-13)
- Phase 11: Data Model Unification (COMPLETE)
- Phase 12: Emotion Removal and LLM Optimization (THIS PHASE)
- Phase 13: Synthesis Performance (reference caching + batch-by-character, formerly Phase 14)
- Drop original Phase 13 (Synthesis Wiring -- no emotion data to wire)
- Drop original Phase 15 (Text-cue injection doesn't work with Base model; A/B preview has less value without expression)
- Update ROADMAP.md and REQUIREMENTS.md to reflect restructure

### Claude's Discretion
- Exact implementation of speech-act LLM skip (flag vs config vs removing the LLM code path)
- Cache key format for trait matching (character profile hash strategy)
- How to handle the `--expression` flag references in REQUIREMENTS.md (SYNTH-04) -- may need to be repurposed or removed
- Whether to update pipeline.py phase comments/docstrings to reflect removed emotion phase

### Deferred Ideas (OUT OF SCOPE)
- CustomVoice model integration as an alternative engine mode (blocked by only 2 English voices -- revisit if Qwen expands preset library)
- VoiceDesign model for unlimited voices with emotion (blocked by per-generation voice inconsistency -- revisit if deterministic generation is added)
- Text-cue injection (prepending emotion cues to text before TTS) -- doesn't work with Base model (cues get spoken aloud)
- Re-evaluate emotion expression if a future TTS model supports voice cloning + emotion instructions simultaneously
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EXPR-01 | Expression resolver combines three layers (character baseline + scene mood + line override) into single ExpressionParams | SUPERSEDED by emotion removal. The three-layer resolver is no longer being built. REQUIREMENTS.md should be updated to reflect that EXPR-01/02/03 are replaced by emotion removal + LLM optimization tasks. |
| EXPR-02 | Emotion-category parameter tables map mood types to volume/speed/pitch deltas with intensity scaling | SUPERSEDED. Emotion parameter tables are not needed since the Base model cannot use them with voice cloning. |
| EXPR-03 | Clear precedence rules resolve conflicts between speech-act adjustments and emotion conditioning | PARTIALLY superseded. Emotion conditioning is removed. Speech-act adjustments become opt-in via `--speech-act-fx` flag. No conflict resolution needed since only one layer remains. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typer | (existing) | CLI flag addition (`--speech-act-fx`) | Already used for all CLI commands |
| pydantic | (existing) | Model updates if SynthesisConfig needs flag | Already used for all data models |
| hashlib | stdlib | SHA-256 cache keys for trait matcher | Already used in attribution/cache.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pathlib | stdlib | File deletion, directory operations | Emotion directory removal |
| json | stdlib | Cache file read/write | Trait matcher cache |

No new dependencies are needed. This phase only uses existing libraries.

## Architecture Patterns

### Recommended Change Structure
```
DELETE:
  src/attribution/emotion/          # Entire directory (4 files + __init__)
  tests/test_emotion.py             # Emotion tests

MODIFY:
  src/pipeline.py                   # Remove emotion import + annotation block (lines 34, 223-306)
  src/attribution/__init__.py       # Remove classify_speech_acts if unused after changes
  src/synthesis/synthesizer.py      # Gate speech-act post-processing behind flag
  src/synthesis/models.py           # Add speech_act_fx field to SynthesisConfig
  src/attribution/speech_acts.py    # Make LLM pass optional (line 304 area)
  src/matching/trait_matcher.py     # Add caching layer
  src/cli.py                        # Add --speech-act-fx flag, wire through

DOC UPDATES:
  .planning/ROADMAP.md              # Restructure phases 12-15 -> 12-13
  .planning/REQUIREMENTS.md         # Update EXPR-* requirements, update traceability
```

### Pattern 1: Feature Flag via SynthesisConfig
**What:** Pass boolean flags through the existing SynthesisConfig dataclass
**When to use:** Gating synthesis behavior (speech-act post-processing)
**Example:**
```python
# In src/synthesis/models.py
@dataclass
class SynthesisConfig:
    # ... existing fields ...
    speech_act_fx: bool = False
    """Apply speech-act audio adjustments (volume/speed). Default OFF."""
```

```python
# In src/synthesis/synthesizer.py (two locations: main loop + restart fallback)
if config.speech_act_fx:
    speech_act = seg.get("speech_act", "spoken")
    if speech_act != "spoken":
        adj_audio, _ = apply_speech_act_adjustments(...)
```

### Pattern 2: Cache Wrapper for LLM Calls
**What:** Wrap trait_matcher LLM calls with check_cache/write_cache using character profile hash
**When to use:** Trait matcher caching
**Example:**
```python
# In src/matching/trait_matcher.py
from src.attribution.cache import check_cache, write_cache, get_cache_key

def match_character_llm(character, candidates, assigned_ids=None, cache_dir=None):
    if cache_dir is not None:
        # Build cache key from character profile + available candidates
        profile_str = character.model_dump_json()
        available_ids = sorted(c.speaker_id for c in candidates if c.speaker_id not in (assigned_ids or set()))
        cache_content = f"{profile_str}|{','.join(available_ids)}"
        key = get_cache_key(cache_content, "trait_match")

        cached = check_cache(cache_dir, key)
        if cached is not None:
            return VoiceAssignment(**cached)

    # ... existing LLM call logic ...

    if cache_dir is not None and result is not None:
        write_cache(cache_dir, key, result.model_dump())

    return result
```

### Pattern 3: Optional LLM Pass in Speech Acts
**What:** Skip LLM refinement in classify_speech_acts when configured
**When to use:** Making speech-act LLM pass optional

**Recommendation (Claude's Discretion):** Add a `use_llm` parameter to `classify_speech_acts()` with default `False`. This is simpler than a config file and aligns with how the function is called from `pipeline.py`. The function already has a natural separation between regex and LLM passes.

```python
def classify_speech_acts(segments, chapter_num, use_llm=False):
    # ... regex pass (unchanged) ...

    # Pass 2: LLM for low-confidence regex results (only if enabled)
    llm_results = {}
    if use_llm and needs_llm:
        llm_results = classify_speech_acts_llm(needs_llm, chapter_num)

    # ... merge pass (unchanged) ...
```

### Anti-Patterns to Avoid
- **Leaving dead imports:** After deleting emotion module, grep for ALL imports referencing it. The `from src.attribution.emotion import ...` in pipeline.py line 34 is the known one, but also check `src/attribution/__init__.py` and any other files.
- **Breaking the unload_model() call:** The `unload_model()` call at line 309 of pipeline.py comes AFTER the emotion block. When removing lines 223-306, ensure `unload_model()` (and the stats summary) remain intact.
- **Hardcoding cache paths:** Use the existing `cache_dir = book_dir / ".cache"` pattern established in pipeline.py.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cache key generation | Custom hash function | `src/attribution/cache.get_cache_key()` | Proven SHA-256 pattern, atomic writes, error handling |
| CLI flags | Custom arg parsing | Typer `typer.Option()` | Already used for all CLI commands |
| Config propagation | Environment variables | SynthesisConfig dataclass fields | Existing pattern, type-safe |

## Common Pitfalls

### Pitfall 1: Incomplete Emotion Reference Removal
**What goes wrong:** Leftover imports or references to emotion.json cause ImportError or runtime failures
**Why it happens:** The emotion system touches multiple files across attribution, synthesis, and CLI
**How to avoid:** After deletion, run `grep -r "emotion" src/ tests/` to find ALL remaining references. Known locations:
- `src/pipeline.py` line 6 docstring mentions "emotion.json"
- `src/pipeline.py` line 34 import
- `src/pipeline.py` lines 223-306 emotion annotation block
- `src/synthesis/post_processor.py` line 11 docstring mentions "scene mood"
- `src/attribution/__init__.py` may export emotion-related symbols indirectly
**Warning signs:** ImportError on `from src.attribution.emotion import ...`

### Pitfall 2: Breaking Pipeline Phase Numbering
**What goes wrong:** The pipeline.py run_attribute function currently produces emotion.json as part of its output. Removing this changes what "Phase 2: Attribute" produces.
**Why it happens:** The function's docstring and return values reference emotion.json
**How to avoid:** Update run_attribute docstring, update the pipeline module docstring (line 6), verify run_full_pipeline still works end-to-end
**Warning signs:** Users expecting emotion.json in book output directory

### Pitfall 3: Speech-Act Flag Not Propagated Through Full Pipeline
**What goes wrong:** `--speech-act-fx` flag added to CLI synthesize command but not wired through `run_full_pipeline` and `convert` command
**Why it happens:** Multiple code paths invoke synthesis (standalone `synthesize` command + full `convert` pipeline)
**How to avoid:** Add flag to both `synthesize` CLI command AND `convert` CLI command, propagate through `run_full_pipeline` -> `run_synthesize` -> `SynthesisConfig`
**Warning signs:** Flag works with `synthesize` but not with `convert`

### Pitfall 4: Trait Matcher Cache Key Sensitivity
**What goes wrong:** Cache returns stale results when candidate pool changes (e.g., speakers already assigned to other characters)
**Why it happens:** Cache key doesn't include the assigned_ids exclusion set
**How to avoid:** Include sorted available candidate IDs in the cache key, not just the character profile
**Warning signs:** Multiple characters assigned to the same speaker on re-runs

### Pitfall 5: Two Post-Processing Locations in Synthesizer
**What goes wrong:** Only one of the two `apply_speech_act_adjustments` call sites gets gated behind the flag
**Why it happens:** `src/synthesis/synthesizer.py` has TWO locations where speech-act post-processing is applied: the main synthesis loop (~line 294) and the restart-fallback path (~line 358)
**How to avoid:** Search for ALL occurrences of `apply_speech_act_adjustments` in synthesizer.py and gate both behind `config.speech_act_fx`
**Warning signs:** Post-processing applied inconsistently (works on normal segments, not on restart segments, or vice versa)

## Code Examples

### Emotion Block Removal from pipeline.py

The exact lines to remove from `run_attribute()`:
```python
# Line 34 - DELETE this import:
from src.attribution.emotion import annotate_scene_moods, detect_overrides

# Lines 223-306 - DELETE the entire emotion annotation block
# From "# --- Emotion annotation ---" through the failed_chapters warning

# Keep line 308+ intact (unload_model, stats summary)
```

### SynthesisConfig Flag Addition
```python
# src/synthesis/models.py - add to SynthesisConfig
speech_act_fx: bool = False
"""Apply speech-act audio post-processing (volume/speed adjustments).
Default OFF -- TTS engine natural prosody is trusted."""
```

### CLI Flag Addition
```python
# src/cli.py - add to synthesize command
speech_act_fx: bool = typer.Option(
    False,
    "--speech-act-fx",
    help="Enable speech-act audio adjustments (whispered/shouted/thought volume/speed changes)",
),
```

### Trait Matcher Cache Integration
```python
# The cache key must include:
# 1. Character profile (serialized via model_dump_json)
# 2. Available candidate speaker IDs (sorted, after excluding assigned_ids)
# This ensures cache invalidation when either the character or candidate pool changes
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Three-layer expression resolver (baseline + mood + override) | Emotion system removed; trust TTS natural prosody | Phase 12 (this phase) | Eliminates 2-3 LLM calls per chapter, removes complex expression resolution code |
| Speech-act post-processing always ON | Opt-in via `--speech-act-fx` flag, default OFF | Phase 12 (this phase) | LUFS normalization undoes volume deltas; natural prosody preferred |
| Speech-act LLM refinement always runs | Regex-only by default, LLM pass optional | Phase 12 (this phase) | Saves 0-1 LLM calls per chapter |
| No trait matcher caching | Cache LLM results by character profile hash | Phase 12 (this phase) | Saves N LLM calls on re-runs (N = major characters) |
| 5 phases remaining (11-15) | 3 phases remaining (11-13) | Phase 12 (this phase) | Phases 13 (synthesis wiring) and 15 (text-cue/preview) dropped |

**Deprecated/outdated:**
- `src/attribution/emotion/` module: Being deleted entirely
- `emotion.json` output: No longer produced
- EXPR-01, EXPR-02, EXPR-03 requirements: Superseded by emotion removal
- SYNTH-01 through SYNTH-04: Superseded (no emotion data to wire)
- CUE-01, CUE-02, PREV-01: Dropped (text-cue injection doesn't work with Base model)

## Open Questions

1. **How should REQUIREMENTS.md handle superseded requirements?**
   - What we know: EXPR-01/02/03 are no longer being implemented as designed. SYNTH-01 through SYNTH-04, CUE-01/02, PREV-01 are also being dropped or restructured.
   - What's unclear: Should superseded requirements be marked with strikethrough, moved to a "Dropped" section, or replaced with new requirement IDs?
   - Recommendation: Mark as dropped with brief explanation, add new requirement IDs for the replacement work (emotion removal, LLM optimization). Keep the traceability table accurate.

2. **Should `--expression` flag references (SYNTH-04) be repurposed as `--speech-act-fx`?**
   - What we know: SYNTH-04 originally defined `--expression` for enabling emotion conditioning. Now speech-act post-processing is the only expression-like feature remaining.
   - What's unclear: Whether `--speech-act-fx` is effectively the successor to `--expression` or a separate concept.
   - Recommendation: Treat `--speech-act-fx` as the replacement. Update SYNTH-04 or replace it.

3. **Should pipeline.py docstrings/comments be updated to remove emotion phase references?**
   - What we know: The module docstring (line 6) mentions "emotion.json" as Phase 2 output. Phase comments in run_full_pipeline reference the 5-phase structure.
   - Recommendation: Yes, update docstrings to reflect the simplified pipeline. This is low-risk and prevents confusion.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | None (uses defaults) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXPR-01 (superseded) | Emotion removal: no emotion imports, no emotion.json production | unit | `python -m pytest tests/test_pipeline_no_emotion.py -x` | No -- Wave 0 |
| EXPR-02 (superseded) | Speech-act fx flag gates post-processing | unit | `python -m pytest tests/test_post_processor.py -x` | Yes (needs update) |
| EXPR-03 (superseded) | Trait matcher caching skips LLM on re-run | unit | `python -m pytest tests/test_trait_matcher.py -x` | Yes (needs cache tests) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update `tests/test_post_processor.py` -- verify speech-act adjustments respect flag (no application when disabled)
- [ ] Add cache tests to `tests/test_trait_matcher.py` -- verify cache hit/miss/invalidation
- [ ] Verify `tests/test_speech_acts.py` -- ensure tests pass with LLM pass disabled by default
- [ ] Delete `tests/test_emotion.py` -- corresponds to deleted module

## Sources

### Primary (HIGH confidence)
- Direct codebase inspection: `src/pipeline.py`, `src/attribution/emotion/`, `src/synthesis/synthesizer.py`, `src/synthesis/post_processor.py`, `src/attribution/speech_acts.py`, `src/matching/trait_matcher.py`, `src/attribution/cache.py`, `src/cli.py`
- CONTEXT.md: User decisions from discuss-phase session confirming TTS model limitations

### Secondary (MEDIUM confidence)
- N/A -- all findings are from direct code inspection

### Tertiary (LOW confidence)
- N/A

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new libraries; all changes use existing project patterns
- Architecture: HIGH - Direct code inspection of all affected files; changes are deletions and flag additions
- Pitfalls: HIGH - Identified all import/reference locations via direct file reading; two synthesis locations confirmed

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable -- no external dependencies changing)
