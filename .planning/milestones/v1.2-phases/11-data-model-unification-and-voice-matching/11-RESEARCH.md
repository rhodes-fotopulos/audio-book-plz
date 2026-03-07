# Phase 11: Data Model Unification and Voice Matching - Research

**Researched:** 2026-03-06
**Domain:** Pydantic data model refactoring, LLM prompt engineering, embedding-based matching
**Confidence:** HIGH

## Summary

Phase 11 replaces two overlapping voice descriptor models (`VoiceQualities` with 4 fields and `VoiceBaseline` with 5 fields) with a single flat `VoiceProfile` model containing 9 fields. This is a pure refactoring phase -- no new libraries, no new external dependencies. The work touches 6 source files (models, extractor, merger, trait_matcher, embedding_matcher, orchestrator) and 2-3 test files.

The CONTEXT.md explicitly states no migration is needed -- the user has no existing users and will regenerate all data. This simplifies the work to a clean break: delete old classes, add new one, update all references. The merger needs the most significant rework since it must intelligently reconcile VoiceProfile fields across chapters instead of simple keep-first logic.

**Primary recommendation:** Implement as a bottom-up refactor: define VoiceProfile first, update extraction prompt + merger, then update both matchers. All changes are within existing patterns (Pydantic BaseModel, LLM structured output, embedding text composition).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Flat model with both coarse and rich descriptor fields (no nesting)
- Coarse traits (pitch, pace, tone, accent) align with LibriTTS-P annotation vocabulary for embedding matching
- Rich descriptors (energy, typical_emotion, description, pace_style, tone_style) provide nuance for LLM casting
- Single field per concept -- when overlap exists (pace, tone), prefer the richer descriptor but keep coarse version with distinct naming convention
- All information preserved from both old models -- no data loss
- No migration needed -- delete VoiceQualities and VoiceBaseline entirely
- CharacterProfile gets a single `voice_profile: VoiceProfile` field replacing both `voice_qualities` and `voice_baseline`
- Clean break, no backward compatibility code
- trait_matcher (LLM): Send full VoiceProfile to LLM casting prompt
- Update extraction prompt and Pydantic schema to produce VoiceProfile directly in one pass
- Single-pass extraction -- 9 fields is reasonable for Qwen 3.5 9B/4B
- Use "unknown" defaults for fields the LLM can't determine from text
- Merger logic: redesign to intelligently combine VoiceProfile fields across chapters (not just keep-first)

### Claude's Discretion
- Embedding matcher text composition (coarse-only vs full profile vs concatenation)
- Whether to include LibriTTS-P vocabulary examples in extraction prompt or normalize afterward
- Matching log verbosity level
- Exact VoiceProfile field names for coarse vs rich disambiguation

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MODEL-01 | VoiceProfile unifies VoiceQualities and VoiceBaseline into single model with all unique attributes | VoiceProfile flat model design with 9 fields -- 4 coarse + 5 rich. Replace both old classes. |
| MODEL-02 | Existing characters.json files load into new VoiceProfile schema without re-extraction | CONTEXT.md overrides this: no backward compatibility needed. Clean break, delete old classes. User will regenerate. |
| MATCH-01 | trait_matcher uses unified VoiceProfile fields for richer character-to-speaker descriptions | Update `_build_character_description()` to include all 9 VoiceProfile fields in LLM prompt |
| MATCH-02 | embedding_matcher uses unified VoiceProfile fields for better embedding-based matching | Update `_build_character_text()` -- recommend coarse traits only for embedding alignment with LibriTTS-P vocabulary |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | (existing) | VoiceProfile model definition | Already used for all models with ConfigDict(strict=True) |
| ollama | (existing) | LLM structured output via format parameter | Already used for extraction and matching |
| sentence-transformers | (existing) | Embedding-based voice matching | Already used, all-MiniLM-L6-v2 on CPU |

### Supporting
No new libraries needed. This phase is purely refactoring existing code.

### Alternatives Considered
None -- all decisions locked in CONTEXT.md.

## Architecture Patterns

### Recommended Change Map
```
src/
├── attribution/
│   ├── models.py          # DELETE VoiceQualities, VoiceBaseline; ADD VoiceProfile; UPDATE CharacterProfile
│   ├── extractor.py       # UPDATE EXTRACTION_SYSTEM_PROMPT for VoiceProfile schema
│   └── merger.py          # REWRITE _merge_voice_qualities() -> _merge_voice_profiles()
├── matching/
│   ├── trait_matcher.py   # UPDATE _build_character_description() for VoiceProfile
│   ├── embedding_matcher.py  # UPDATE _build_character_text() for VoiceProfile
│   └── orchestrator.py    # UPDATE narrator fallback CharacterProfile construction
└── tests/
    ├── test_trait_matcher.py      # UPDATE fixtures (VoiceQualities -> VoiceProfile)
    └── test_embedding_matcher.py  # UPDATE fixtures (VoiceQualities -> VoiceProfile)
```

### Pattern 1: VoiceProfile Model Design
**What:** Single flat Pydantic model replacing VoiceQualities (4 fields) + VoiceBaseline (5 fields)
**When to use:** The only voice descriptor model going forward

**Field mapping from old to new:**

| Old Model | Old Field | New Field | Naming Rationale |
|-----------|-----------|-----------|------------------|
| VoiceQualities | pitch | pitch | No overlap -- keep as-is |
| VoiceQualities | pace | pace | Coarse version (fast/moderate/slow) |
| VoiceQualities | tone | tone | Coarse version (warm/gruff/etc) |
| VoiceQualities | accent | accent | No overlap -- keep as-is |
| VoiceBaseline | pace | pace_style | Rich version (measured/rapid/languid) -- distinct name |
| VoiceBaseline | tone | tone_style | Rich version (gravelly/melodic/breathy) -- distinct name |
| VoiceBaseline | energy | energy | No overlap -- keep as-is |
| VoiceBaseline | typical_emotion | typical_emotion | No overlap -- keep as-is |
| VoiceBaseline | description | description | No overlap -- keep as-is |

**Recommended implementation:**
```python
class VoiceProfile(BaseModel):
    """Unified voice description for a character.

    Combines coarse traits (aligned with LibriTTS-P annotation vocabulary
    for embedding matching) with rich descriptors (for LLM casting and
    emotion baseline). All fields default to "unknown" when text provides
    no evidence.
    """

    model_config = ConfigDict(strict=True)

    # Coarse traits (LibriTTS-P aligned)
    pitch: str
    """Vocal pitch: "high", "medium", "low", or "unknown"."""

    pace: str
    """Speech pace: "fast", "moderate", "slow", or "unknown"."""

    tone: str
    """Vocal tone: e.g. "warm", "gruff", "silky", "monotone", "unknown"."""

    accent: str
    """Accent if mentioned: e.g. "British", "Southern American", "unknown"."""

    # Rich descriptors (LLM casting + emotion baseline)
    pace_style: str
    """Nuanced speaking pace: e.g. "measured", "rapid", "languid", "clipped", "unknown"."""

    tone_style: str
    """Nuanced vocal quality: e.g. "gravelly", "melodic", "breathy", "flat", "unknown"."""

    energy: str
    """Energy level: e.g. "restrained", "animated", "intense", "subdued", "unknown"."""

    typical_emotion: str
    """Default emotional register: e.g. "sardonic", "cheerful", "weary", "unknown"."""

    description: str
    """One-sentence voice summary: e.g. "A slow, gravelly voice with weary patience"."""
```

### Pattern 2: Merger Redesign for VoiceProfile
**What:** Intelligent reconciliation of VoiceProfile fields across chapters
**When to use:** When merging per-chapter character extractions into final characters.json

The current `_merge_voice_qualities()` uses a simple prefer-non-unknown strategy with longer-description-wins tiebreaker. The new merger should:

1. For each field: prefer non-"unknown" over "unknown" (same as before)
2. When both have non-unknown values for the same field: weight by description length (evidence proxy) -- same heuristic but applied to all 9 fields
3. The `description` field: prefer the longer/more detailed one (most evidence)

**Key insight:** The merger strategy does not need to be dramatically different. The main change is handling 9 fields instead of 4, and removing the separate voice_baseline merge path. The evidence-based tiebreaker (longer description = more textual evidence) is sound and should carry forward.

```python
def _merge_voice_profiles(
    vp_a: VoiceProfile,
    vp_b: VoiceProfile,
) -> VoiceProfile:
    """Merge two VoiceProfiles, preferring non-unknown values.

    When both have non-unknown values, prefer the profile with the
    longer description (more textual evidence).
    """
    prefer_a = len(vp_a.description) >= len(vp_b.description)

    def pick(val_a: str, val_b: str) -> str:
        if val_a == "unknown" and val_b != "unknown":
            return val_b
        if val_b == "unknown" and val_a != "unknown":
            return val_a
        if val_a != "unknown" and val_b != "unknown":
            return val_a if prefer_a else val_b
        return "unknown"

    # Description: take the longer one directly
    desc = vp_a.description if len(vp_a.description) >= len(vp_b.description) else vp_b.description

    return VoiceProfile(
        pitch=pick(vp_a.pitch, vp_b.pitch),
        pace=pick(vp_a.pace, vp_b.pace),
        tone=pick(vp_a.tone, vp_b.tone),
        accent=pick(vp_a.accent, vp_b.accent),
        pace_style=pick(vp_a.pace_style, vp_b.pace_style),
        tone_style=pick(vp_a.tone_style, vp_b.tone_style),
        energy=pick(vp_a.energy, vp_b.energy),
        typical_emotion=pick(vp_a.typical_emotion, vp_b.typical_emotion),
        description=desc,
    )
```

### Pattern 3: Embedding Matcher Text Composition
**What:** Compose text for embedding from VoiceProfile fields
**Recommendation:** Use coarse traits only for embedding text, since these align with LibriTTS-P annotation vocabulary

**Rationale:** The SpeakerAnnotation.trait_text contains LibriTTS-P perception words like "masculine", "calm", "intellectual", "deep", "young", "clear", "raspy". Coarse traits (pitch, pace, tone, accent) use a similar vocabulary register. Rich descriptors like "measured", "languid", "sardonic" are more literary and won't embed close to the LibriTTS-P vocabulary in the all-MiniLM-L6-v2 embedding space.

```python
def _build_character_text(character: CharacterProfile) -> str:
    """Build embedding text from character's coarse voice traits."""
    parts = []

    if character.gender != "unknown":
        parts.append(character.gender)
    if character.age_range != "unknown":
        parts.append(character.age_range)

    # Coarse traits only -- aligned with LibriTTS-P vocabulary
    vp = character.voice_profile
    for attr in [vp.pitch, vp.pace, vp.tone, vp.accent]:
        if attr != "unknown":
            parts.append(attr)

    # Personality still contributes useful signal
    parts.extend(character.personality_traits)

    return ", ".join(parts) if parts else "neutral voice"
```

### Pattern 4: Trait Matcher Character Description
**What:** Include full VoiceProfile in LLM casting prompt
**When to use:** When building the character description for trait_matcher LLM calls

```python
def _build_character_description(character: CharacterProfile) -> str:
    """Build a natural language description of a character's voice traits."""
    parts = [f"Character: {character.name}"]
    parts.append(f"Gender: {character.gender}")
    parts.append(f"Age: {character.age_range}")

    vp = character.voice_profile
    voice_parts = []
    if vp.pitch != "unknown":
        voice_parts.append(f"{vp.pitch} pitch")
    if vp.pace != "unknown":
        voice_parts.append(f"{vp.pace} pace")
    if vp.tone != "unknown":
        voice_parts.append(f"{vp.tone} tone")
    if vp.accent != "unknown":
        voice_parts.append(f"{vp.accent} accent")
    if voice_parts:
        parts.append(f"Voice: {', '.join(voice_parts)}")

    # Rich descriptors for casting nuance
    style_parts = []
    if vp.pace_style != "unknown":
        style_parts.append(f"{vp.pace_style} speaking style")
    if vp.tone_style != "unknown":
        style_parts.append(f"{vp.tone_style} vocal quality")
    if vp.energy != "unknown":
        style_parts.append(f"{vp.energy} energy")
    if vp.typical_emotion != "unknown":
        style_parts.append(f"typically {vp.typical_emotion}")
    if style_parts:
        parts.append(f"Style: {', '.join(style_parts)}")

    if vp.description and vp.description != "unknown":
        parts.append(f"Voice summary: {vp.description}")

    if character.personality_traits:
        parts.append(f"Personality: {', '.join(character.personality_traits)}")
    if character.description:
        parts.append(f"Description: {character.description}")

    return "\n".join(parts)
```

### Anti-Patterns to Avoid
- **Nested VoiceProfile models:** The user explicitly decided on a flat model. Do not create sub-objects for coarse vs rich traits.
- **Backward compatibility shims:** No migration code, no Optional fields with fallback, no legacy loading. Clean break per CONTEXT.md.
- **Over-engineering the merger:** The current evidence-based tiebreaker (longer description wins) is sufficient. Do not add LLM-based reconciliation or voting systems.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON schema for LLM | Manual schema dict | `VoiceProfile.model_json_schema()` | Pydantic generates correct schemas automatically |
| Field validation | Custom validators | Pydantic strict mode | Already established pattern in codebase |
| Embedding similarity | Manual cosine calc | `sentence_transformers.util.cos_sim()` | Already used, handles tensor operations correctly |

## Common Pitfalls

### Pitfall 1: Forgetting to update the orchestrator narrator fallback
**What goes wrong:** The orchestrator constructs a manual `CharacterProfile` with `VoiceQualities` for narrator embedding fallback (lines 117-128 in orchestrator.py). If not updated to use `VoiceProfile`, it will crash at runtime.
**Why it happens:** This is a fallback path that only triggers when LLM narrator matching fails -- easy to miss in testing.
**How to avoid:** Search for ALL occurrences of `VoiceQualities` and `VoiceBaseline` across the codebase before declaring done.
**Warning signs:** `ImportError` or `TypeError` at runtime when narrator LLM matching fails.

### Pitfall 2: Extraction prompt asking for too many specific values
**What goes wrong:** If the extraction prompt gives overly specific vocabulary guidance for 9 fields, Qwen 3.5 9B may produce formulaic responses (every character gets "medium" pitch and "moderate" pace).
**Why it happens:** Smaller LLMs tend to anchor on example values in prompts.
**How to avoid:** Keep vocabulary guidance minimal. List field names with brief descriptions but avoid exhaustive value enumerations. Let the LLM infer from context.
**Warning signs:** Characters.json shows same values across multiple characters for coarse traits.

### Pitfall 3: Cache invalidation after schema change
**What goes wrong:** Cached extraction results (in `.cache/` within book directories) contain the old schema with `voice_qualities` and `voice_baseline` fields. Loading these cached results with the new `CharacterProfile` (which expects `voice_profile`) will cause `ValidationError`.
**Why it happens:** The extraction cache uses `CharacterProfile.model_validate()` to deserialize cached JSON.
**How to avoid:** Either clear extraction caches before running, or let the `model_validate` failure trigger re-extraction naturally (the extractor already handles cache misses by calling the LLM).
**Warning signs:** `ValidationError` on cached data -- but this is actually fine since re-extraction is expected.

### Pitfall 4: Test fixtures using old model constructors
**What goes wrong:** Existing test files construct `CharacterProfile(voice_qualities=VoiceQualities(...))`. These will all fail after the model change.
**Why it happens:** Multiple test files have fixtures using the old constructors.
**How to avoid:** Update all test fixtures as part of the model change task, not as a separate task.
**Warning signs:** All tests failing with `TypeError` or missing field errors.

### Pitfall 5: Merger import of VoiceQualities
**What goes wrong:** `merger.py` explicitly imports `VoiceQualities` (line 17). This import will break after deletion.
**Why it happens:** Direct import reference to a deleted class.
**How to avoid:** Replace import with `VoiceProfile` when updating merger.

## Code Examples

### Extraction Prompt Update
The extraction system prompt in `extractor.py` currently lists `voice_qualities` and `voice_baseline` as separate sections. The updated prompt should request `voice_profile` as a single object:

```python
# In EXTRACTION_SYSTEM_PROMPT, replace the voice_qualities and voice_baseline sections with:
"""
- voice_profile: Unified voice description with 9 fields:
  - pitch: Vocal pitch ("high", "medium", "low", or "unknown")
  - pace: Speech pace ("fast", "moderate", "slow", or "unknown")
  - tone: Vocal tone (e.g. "warm", "gruff", "silky", "monotone", or "unknown")
  - accent: Accent if mentioned (e.g. "British", "Southern American", or "unknown")
  - pace_style: Nuanced speaking style (e.g. "measured", "rapid", "languid", "clipped", or "unknown")
  - tone_style: Nuanced vocal quality (e.g. "gravelly", "melodic", "breathy", "flat", or "unknown")
  - energy: Energy level (e.g. "restrained", "animated", "intense", "subdued", or "unknown")
  - typical_emotion: Default emotional register (e.g. "sardonic", "cheerful", "weary", or "unknown")
  - description: One-sentence voice summary (e.g. "A slow, gravelly voice with weary patience")
"""
```

### CharacterProfile Field Update
```python
class CharacterProfile(BaseModel):
    # ... existing fields ...
    voice_profile: VoiceProfile
    """Unified voice description for voice matching and emotion baseline."""
    # DELETE: voice_qualities: VoiceQualities
    # DELETE: voice_baseline: VoiceBaseline | None = None
```

### Matching Log Recommendation
For matching logs, add a concise summary at INFO level showing which VoiceProfile fields contributed to the match:

```python
logger.info(
    "Matched %s -> speaker %s (method=%s, confidence=%.2f)",
    character.name, assignment.speaker_id, assignment.method, assignment.confidence,
)
```

Keep DEBUG level for full VoiceProfile dumps -- this avoids flooding logs during normal operation while enabling diagnosis when needed.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate VoiceQualities + VoiceBaseline | Unified VoiceProfile | Phase 11 (this phase) | Eliminates duplication, richer matching data |
| VoiceBaseline optional (None default) | VoiceProfile mandatory | Phase 11 (this phase) | All characters get full voice description |
| Merger handles VoiceQualities only | Merger handles full VoiceProfile | Phase 11 (this phase) | 9 fields merged intelligently instead of 4 |

**Note:** VoiceBaseline was added in Phase 8 but never consumed by any matcher. It was only extracted and stored. This phase is the first time the rich descriptors (energy, typical_emotion, description, pace_style, tone_style) will actually feed into matching.

## Open Questions

1. **LibriTTS-P vocabulary in extraction prompt**
   - What we know: Coarse traits should align with LibriTTS-P vocabulary (per CONTEXT.md). LibriTTS-P uses terms like "masculine", "tensed", "slightly clear", "cool", "intellectual", "calm".
   - What's unclear: Whether to constrain the extraction prompt with example vocabulary from LibriTTS-P, or let the LLM generate freely and normalize afterward.
   - Recommendation: Do NOT include LibriTTS-P vocabulary in the extraction prompt. The coarse traits (pitch, pace, tone) already use simple categorical values that embed well. Adding LibriTTS-P-specific terms to the prompt would confuse the LLM and not help -- the embedding matcher handles vocabulary alignment implicitly via semantic similarity. Keep extraction prompt clean.

2. **Description field merging**
   - What we know: The `description` field is a one-sentence voice summary. When merging across chapters, taking the longer one is the current strategy.
   - What's unclear: Whether a later chapter's description might be more accurate (more character development revealed).
   - Recommendation: Keep the longer-description-wins strategy. It correlates with more textual evidence and avoids needing chapter ordering logic.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >= 7.0 |
| Config file | none (using defaults, pytest in pyproject.toml dev deps) |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MODEL-01 | VoiceProfile model has all 9 fields, validates correctly | unit | `python -m pytest tests/test_models.py -x -q` | No -- Wave 0 |
| MODEL-02 | N/A per CONTEXT.md (no backward compat needed) | N/A | N/A | N/A |
| MATCH-01 | trait_matcher uses VoiceProfile fields in character description | unit | `python -m pytest tests/test_trait_matcher.py -x -q` | Yes -- needs fixture updates |
| MATCH-02 | embedding_matcher uses VoiceProfile fields in character text | unit | `python -m pytest tests/test_embedding_matcher.py -x -q` | Yes -- needs fixture updates |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update `tests/test_trait_matcher.py` -- fixtures use `VoiceQualities`, need `VoiceProfile`
- [ ] Update `tests/test_embedding_matcher.py` -- fixtures use `VoiceQualities`, need `VoiceProfile`
- [ ] Update `tests/test_matching_orchestrator.py` -- if it constructs CharacterProfile objects
- [ ] Any other test files importing `VoiceQualities` or `VoiceBaseline`

*(These are fixture updates, not new test files -- existing test logic remains valid)*

## Sources

### Primary (HIGH confidence)
- Source code analysis: `src/attribution/models.py` -- current VoiceQualities (4 fields) and VoiceBaseline (5 fields) definitions
- Source code analysis: `src/matching/trait_matcher.py` -- `_build_character_description()` at line 100
- Source code analysis: `src/matching/embedding_matcher.py` -- `_build_character_text()` at line 66
- Source code analysis: `src/attribution/merger.py` -- `_merge_voice_qualities()` at line 187, `_merge_two_profiles()` at line 116
- Source code analysis: `src/attribution/extractor.py` -- `EXTRACTION_SYSTEM_PROMPT` at line 43
- Source code analysis: `src/matching/orchestrator.py` -- narrator fallback at lines 117-128
- Source code analysis: `src/matching/speaker_index.py` -- LibriTTS-P trait vocabulary and gender inference

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions on flat model design, field naming, and migration strategy

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries, pure refactoring of existing Pydantic models
- Architecture: HIGH - all changes are within established codebase patterns, full source code reviewed
- Pitfalls: HIGH - identified through direct code analysis of all affected files and their dependencies

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (stable -- internal refactoring, no external dependency changes)
