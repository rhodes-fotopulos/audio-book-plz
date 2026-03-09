# Architecture Research

**Domain:** Merger hardening, opinionated voice profiles, and expressive reference clip selection for EPUB-to-audiobook pipeline (v1.3)
**Researched:** 2026-03-09
**Confidence:** HIGH (all integration points are in existing codebase; no new external dependencies)

## Current Architecture (v1.2 Baseline)

Six sequential phases, each reading from and writing to disk:

```
Phase 1: Parse       EPUB -> segments.json
Phase 2: Attribute   segments.json -> characters.json + attributed.json
                     (extract_all_characters -> merge_characters -> attribute_all_segments)
                     --- Ollama unload boundary ---
Phase 3: Match       characters.json + attributed.json -> voice_map.json
                     (classify_cast -> build_embeddings -> match narrator/major/minor -> dedup -> select_reference_clip)
Phase 4: Synthesize  attributed.json + voice_map.json -> wavs/
                     (voice_prep -> qwen_engine -> checkpoint)
Phase 4.5: Verify    wavs/ + voice_map.json -> voice_consistency_report.json
Phase 5: Assemble    wavs/ -> chapters/*.mp3 + audiobook.mp3
```

### Files That Change in v1.3

| File | Change Type | What Changes |
|------|-------------|--------------|
| `src/attribution/merger.py` | MODIFY | Cross-name exclusion, co-occurrence on all stages, trait cap, merge diagnostics |
| `src/attribution/extractor.py` | MODIFY | Prompt hardening with negative examples |
| `src/attribution/models.py` | NO CHANGE | VoiceProfile model stays as-is (9 fields sufficient) |
| `src/matching/clip_selector.py` | MODIFY | Multi-criteria scoring (SNR + pitch/energy/rate variance) |
| `src/matching/orchestrator.py` | MODIFY | Load voice overrides, pass to clip selector |
| `src/matching/models.py` | MODIFY | Add expressive_score field to VoiceAssignment |
| `src/synthesis/voice_prep.py` | MODIFY | Compute pitch/energy/rate stats for clip scoring |
| `src/pipeline.py` | MODIFY | Wire --opinionated flag, load voice_overrides.yaml |
| `src/cli.py` | MODIFY | Add --opinionated CLI flag |
| NEW: `src/attribution/distinctiveness.py` | NEW | Post-extraction distinctiveness pass |
| NEW: `src/matching/expressive_scorer.py` | NEW | Pitch/energy/rate variance scoring |
| NEW: voice_overrides.yaml (per-book) | NEW | User override file in book_dir |
| NEW: merge_audit.json (per-book) | NEW | Diagnostic output from merger |

## System Overview

```
                        Phase 2: Attribute
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  extractor.py ──► merger.py ──► distinctiveness.py ──► characters.json
│  (per-chapter)    (4 stages)    (push apart)                        │
│                       │                                             │
│                       ▼                                             │
│                  merge_audit.json (NEW)                              │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

                        Phase 3: Match
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  characters.json ──► voice_overrides.yaml ──► trait_matcher.py      │
│  (with distinct      (apply overrides)        (LLM matching)        │
│   profiles)                                                         │
│       │                                           │                 │
│       ▼                                           ▼                 │
│  orchestrator.py ──► expressive_scorer.py ──► clip_selector.py      │
│                      (pitch/energy/rate)      (multi-criteria)      │
│                                                   │                 │
│                                                   ▼                 │
│                                              voice_map.json         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | Integration Point |
|-----------|----------------|-------------------|
| `merger.py` (MODIFY) | Deduplicate per-chapter character profiles into registry | Between extractor output and characters.json write |
| `distinctiveness.py` (NEW) | Push similar VoiceProfile fields apart after merge | Between merge_characters() return and characters.json write |
| `expressive_scorer.py` (NEW) | Score WAV clips on pitch/energy/rate variance | Called by clip_selector before final clip selection |
| `voice_overrides.yaml` (NEW) | Per-character field overrides applied post-extraction | Loaded in pipeline.py, applied before voice matching |
| `merge_audit.json` (NEW) | Diagnostic log of every merge decision | Written by merger.py alongside characters.json |

## Integration Architecture

### Feature 1: Merger Hardening

**Scope:** All changes within `src/attribution/merger.py`, no new files except `merge_audit.json` output.

**Current merger pipeline (4 stages):**
```
Stage 1: _merge_by_exact_name()
Stage 2: _merge_by_fuzzy()
Stage 3: _merge_by_substring_and_alias()
Stage 4: _consolidate_with_llm() (co-occurrence guard exists here only)
```

**Changes per stage:**

| Stage | Current Behavior | v1.3 Change |
|-------|-----------------|-------------|
| 1. Exact name | Groups by case-insensitive name | Add cross-name exclusion check |
| 2. Fuzzy | SequenceMatcher + title/name match, surname-only block | Add co-occurrence guard, cross-name exclusion |
| 3. Substring/alias | Substring match + alias overlap, surname-only block | Add co-occurrence guard, cross-name exclusion |
| 4. LLM consolidation | Co-occurrence guard on named pairs only | Extend guard to unnamed profiles, add cross-name exclusion |
| Post-merge | None | Trait count cap (30), validation pass, merge_audit.json |

**Cross-name exclusion logic:**
Before any merge in stages 1-4, check whether profile_b's canonical name appears as a canonical name (not alias) of any OTHER profile in the current list. If so, block the merge. This prevents "Elizabeth" from being merged into "Mr. Bennet" when "Elizabeth Bennet" exists as a separate character.

```python
def _is_cross_name_blocked(
    profile_a: CharacterProfile,
    profile_b: CharacterProfile,
    all_profiles: list[CharacterProfile],
) -> bool:
    """Block merge if B's name is another character's canonical name."""
    b_name_lower = profile_b.name.lower().strip()
    for other in all_profiles:
        if other is profile_a or other is profile_b:
            continue
        if other.name.lower().strip() == b_name_lower:
            return True
        # Also check if B's name is a substring of another canonical name
        # (catches "Darcy" when "Mr. Darcy" exists separately)
    return False
```

**Co-occurrence guard extension:**
Currently `_named_pair_cooccurs()` only blocks when BOTH profiles have `is_named=True`. The existing guard in Stage 4 is correct but stages 2-3 lack it entirely. Add the guard to `_merge_by_fuzzy()` and `_merge_by_substring_and_alias()` by passing `chapter_characters` and the co-occurrence map through.

**Signature change for `merge_characters()`:**
```python
def merge_characters(
    chapter_characters: dict[int, list[CharacterProfile]],
    cache_dir: Path | None = None,
    diagnostics: bool = True,  # NEW: emit merge_audit.json
) -> tuple[list[CharacterProfile], dict | None]:  # NEW: return audit data
```

The audit dict structure:
```python
{
    "stages": [
        {
            "stage": "exact_name",
            "merges": [
                {"merged": "darcy", "into": "Mr. Darcy", "reason": "exact name match"},
            ],
            "blocked": [
                {"a": "Mr. Bennet", "b": "Mrs. Bennet", "reason": "surname-only exclusion"},
            ],
            "profile_count_before": 45,
            "profile_count_after": 32,
        },
        # ... stages 2-4
    ],
    "trait_caps_applied": [
        {"character": "Elizabeth Bennet", "original_count": 47, "capped_to": 30},
    ],
    "cross_contamination_flags": [],
}
```

**Trait count cap:**
After all merge stages, iterate profiles and truncate `personality_traits` to 30 entries. Log when capping occurs.

**Post-merge validation:**
After all stages, check for cross-contamination: if character A's aliases contain character B's canonical name, flag it. Write flags to `merge_audit.json` and log warnings.

### Feature 2: Opinionated Voice Profiles

**Scope:** New `src/attribution/distinctiveness.py` + modifications to `src/attribution/extractor.py` prompt + voice override loading in `src/pipeline.py`.

#### 2a. Extraction Prompt Hardening

Modify `EXTRACTION_SYSTEM_PROMPT` in `extractor.py` to add negative examples that push the LLM toward more specific voice descriptions:

```python
# Add to EXTRACTION_SYSTEM_PROMPT:
"""
- AVOID generic voice descriptions. Bad: "a normal voice". Good: "a clipped, \
nasal voice with impatient energy".
- When the text gives no voice evidence, use personality and age to INFER a \
plausible voice. A timid young woman likely has a soft, hesitant voice. \
A boisterous old sea captain likely has a booming, weathered voice.
- Each character's voice_profile.description MUST be unique and distinguishable \
from other characters in this chapter.
"""
```

This is a prompt-only change. No structural changes to the extractor.

#### 2b. Distinctiveness Pass (NEW file)

**File:** `src/attribution/distinctiveness.py`

**When called:** After `merge_characters()` returns, before writing `characters.json`. Only when `--opinionated` flag is set.

**What it does:** Compares all VoiceProfile fields across characters. When two characters share the same value for pitch, pace, tone, or energy, push the less-described character's value to a contrasting option.

**Integration point in pipeline.py:**
```python
# In run_attribute():
characters = merge_characters(chapter_characters, cache_dir)

if opinionated:
    from src.attribution.distinctiveness import push_voices_apart
    characters = push_voices_apart(characters)
```

**Algorithm:**
```python
def push_voices_apart(profiles: list[CharacterProfile]) -> list[CharacterProfile]:
    """Push similar voice profiles apart for more distinct character voices.

    For each coarse trait (pitch, pace, tone, energy), if two characters
    share the same value, change the character with fewer dialogue-evidence
    lines to a contrasting value.

    Contrast maps:
        pitch: high <-> low, medium -> pick based on gender
        pace: fast <-> slow, moderate -> pick based on personality
        energy: restrained <-> animated, moderate -> pick based on age
    """
```

This does NOT use LLM calls -- it is a deterministic rule-based pass. This is intentional: the LLM already had its chance during extraction, and adding another LLM round would be slow and unpredictable.

#### 2c. Voice Overrides

**File:** `voice_overrides.yaml` in each book's output directory.

**Format:**
```yaml
# voice_overrides.yaml -- manual per-character voice tuning
# Place in book output directory (e.g., output/pride-and-prejudice/)
# Fields match VoiceProfile: pitch, pace, tone, accent, pace_style,
# tone_style, energy, typical_emotion, description
# Any field not specified keeps its extracted value.

Mr. Darcy:
  pitch: low
  tone: cold
  energy: restrained
  description: "A deep, controlled voice with aristocratic reserve"

Mrs. Bennet:
  pitch: high
  energy: animated
  tone: shrill
  description: "A high, excitable voice prone to dramatic outbursts"
```

**Loading point:** In `pipeline.py`, after the distinctiveness pass (or after merge if `--opinionated` is off):

```python
overrides_path = book_dir / "voice_overrides.yaml"
if overrides_path.exists():
    from src.attribution.distinctiveness import apply_voice_overrides
    characters = apply_voice_overrides(characters, overrides_path)
```

**Override application** lives in `distinctiveness.py` (same file as the distinctiveness pass, since both modify VoiceProfile post-extraction).

### Feature 3: Expressive Reference Clip Selection

**Scope:** New `src/matching/expressive_scorer.py` + modifications to `src/matching/clip_selector.py`.

#### Current clip selection (clip_selector.py):

```
For each speaker_id:
  1. Find all WAV files in LibriTTS-R
  2. Filter by duration (5-25s, prefer ~12.5s)
  3. Score by proximity to target duration
  4. Pick highest-scoring clip
```

SNR filtering happens later in `voice_prep.py` (warns but doesn't re-select).

#### v1.3 clip selection:

```
For each speaker_id:
  1. Find all WAV files (unchanged)
  2. Filter by duration (unchanged)
  3. Compute multi-criteria score:
     a. Duration proximity (existing, weight 0.3)
     b. SNR score (move from voice_prep, weight 0.3)
     c. Pitch variance -- higher = more expressive (NEW, weight 0.15)
     d. Energy variance -- higher = more dynamic (NEW, weight 0.15)
     e. Rate match -- match clip speaking rate to character pace (NEW, weight 0.1)
  4. Pick highest-scoring clip
```

**New file: `src/matching/expressive_scorer.py`**

```python
@dataclass
class ExpressiveScore:
    """Multi-criteria score for a reference clip."""
    duration_score: float      # 0-1, proximity to target
    snr_score: float           # 0-1, normalized from dB
    pitch_variance: float      # 0-1, normalized F0 variance
    energy_variance: float     # 0-1, normalized RMS variance
    rate_match: float          # 0-1, how well speaking rate matches target pace
    composite: float           # Weighted combination

def score_clip(
    wav_path: Path,
    target_duration_s: float = 12.5,
    target_pace: str = "moderate",
) -> ExpressiveScore:
    """Score a WAV clip on multiple expressiveness criteria."""
```

**Pitch variance computation:** Use `librosa.pyin()` for F0 extraction (librosa is already an indirect dependency via mlx-audio). Compute coefficient of variation of non-zero F0 values. Higher variance = more melodic/expressive clip.

**Energy variance computation:** Frame-level RMS (reuse approach from `voice_prep._compute_snr_rms()`). Compute coefficient of variation. Higher variance = more dynamic range.

**Rate matching:** Estimate syllables-per-second from the transcript length and audio duration. Map character's VoiceProfile.pace to a target range:
- "fast" -> prefer clips with >4.5 syllables/sec
- "moderate" -> prefer 3.5-4.5 syllables/sec
- "slow" -> prefer <3.5 syllables/sec

**Modified `clip_selector.py` signature:**
```python
def select_reference_clip(
    speaker_id: str,
    libritts_root: Path,
    target_pace: str = "moderate",  # NEW: from VoiceProfile.pace
    use_expressive_scoring: bool = True,  # NEW: enable multi-criteria
) -> str | None:
```

**Integration in orchestrator.py:** When selecting clips (Step 9), pass the character's `pace` from their VoiceProfile:
```python
# In orchestrator.py, Step 9:
for char_profile in characters:
    assignment = find_assignment(char_profile.name)
    clip = select_reference_clip(
        assignment.speaker_id,
        libritts_audio_dir,
        target_pace=char_profile.voice_profile.pace,
    )
```

This requires `orchestrator.py` to have access to character profiles during clip selection, which it currently does not (it only has assignments). The fix: load `characters.json` at the start (already loaded in Step 2) and pass it through, or add a `pace` field to `VoiceAssignment` during matching.

**Recommended approach:** Add the character's pace to the VoiceAssignment during matching (simpler, avoids threading characters through clip selection):

```python
# In VoiceAssignment model:
target_pace: str = "moderate"
"""Character's speaking pace for reference clip matching."""
```

## Data Flow Changes

### Before (v1.2)
```
extractor.py -> chapter_characters
                     |
              merge_characters()
                     |
              characters.json -> trait_matcher -> clip_selector -> voice_map.json
                                                  (duration only)
```

### After (v1.3)
```
extractor.py -> chapter_characters    (hardened prompts)
                     |
              merge_characters()      (cross-name, co-occurrence on all stages)
                     |
              merge_audit.json        (diagnostic output)
                     |
              push_voices_apart()     (--opinionated only)
                     |
              apply_voice_overrides() (if voice_overrides.yaml exists)
                     |
              characters.json -> trait_matcher -> clip_selector -> voice_map.json
                                                  (multi-criteria scoring)
```

### Key Invariants Preserved

1. **Phase boundaries unchanged.** All merger/distinctiveness work stays in Phase 2. All clip selection stays in Phase 3. No cross-phase coupling added.
2. **JSON artifact contracts unchanged.** `characters.json` schema (CharacterProfile) and `voice_map.json` schema (VoiceMap) keep their existing fields. New fields are additive.
3. **Cache invalidation.** Extraction cache uses content hash -- prompt changes invalidate automatically. Merger diagnostics are new output, not cached input. Clip selection is not cached.
4. **Memory budget.** No new models loaded. Expressive scoring uses numpy/librosa (already in memory during Phase 3). No concurrent LLM+TTS.

## Suggested Build Order

Build order follows data flow direction and dependency chain:

### Phase A: Merger Hardening (build first -- independent, highest impact)

**Rationale:** The merger is the first integration point in the pipeline. Fixing it before adding opinionated profiles means the distinctiveness pass operates on clean, correctly-merged data. Also, merger bugs cause cascading errors (wrong character gets wrong voice gets wrong clips).

1. **A1: Co-occurrence guard on stages 2-3** -- Thread `chapter_characters` through `_merge_by_fuzzy()` and `_merge_by_substring_and_alias()`. Build co-occurrence map once in `merge_characters()` and pass it down.

2. **A2: Cross-name exclusion** -- Add `_is_cross_name_blocked()` check to all four stages. Requires the full profile list to be visible at each stage (currently each stage operates on its own subset).

3. **A3: Surname-only exclusion hardening** -- Extend `_names_share_surname_only()` to handle title-vs-title cases beyond Mr./Mrs. (e.g., "Lord Pemberton" vs "Lady Pemberton"). Review the TITLES set.

4. **A4: Merge diagnostics** -- Add audit dict accumulation throughout merge pipeline. Write `merge_audit.json`. Update `merge_characters()` return type.

5. **A5: Post-merge validation** -- Cross-contamination detection pass. Trait count cap (30). Integrate with audit output.

6. **A6: Extraction prompt hardening** -- Add negative examples to `EXTRACTION_SYSTEM_PROMPT`. This is the lowest-risk change (prompt text only) but placed after merger fixes so cached extraction results get invalidated by the prompt change.

### Phase B: Opinionated Voice Profiles (build second -- depends on clean merger output)

7. **B1: Distinctiveness pass** -- Create `src/attribution/distinctiveness.py` with `push_voices_apart()`. Rule-based, no LLM. Add `--opinionated` flag to CLI and pipeline.

8. **B2: Voice overrides** -- Add `apply_voice_overrides()` to `distinctiveness.py`. YAML loading, field-level override application. No new dependencies (PyYAML is already available via Pydantic).

### Phase C: Expressive Reference Clips (build last -- depends on voice profiles being correct)

9. **C1: Expressive scorer** -- Create `src/matching/expressive_scorer.py`. Pitch/energy/rate variance computation. Pure audio analysis, no integration yet.

10. **C2: Clip selector integration** -- Modify `select_reference_clip()` to use multi-criteria scoring. Add `target_pace` parameter. Wire through orchestrator.

11. **C3: Rate matching** -- Add speaking-rate estimation and pace-matching logic to expressive scorer. Requires transcript access (already available via `select_reference_clip_with_transcript()`).

## Anti-Patterns to Avoid

### Anti-Pattern 1: LLM-Based Distinctiveness

**What people do:** Use another LLM call to "make voices more distinct" after extraction.
**Why it is wrong:** Adds 10-30 seconds per character, results are nondeterministic, hard to test, and the LLM already had its chance. If extraction prompts are good, the LLM produces distinct voices. If they are not, fix the prompts.
**Do this instead:** Deterministic rule-based push (contrast maps for pitch/pace/energy).

### Anti-Pattern 2: Blocking All Co-Occurring Names

**What people do:** Block merge whenever ANY names appear in the same chapter.
**Why it is wrong:** Unnamed descriptors ("the old man") legitimately co-occur with their named counterpart ("Mr. Wickham"). The co-occurrence guard must only block named+named pairs, not named+unnamed.
**Do this instead:** Keep the existing `is_named` check in `_named_pair_cooccurs()`. Only extend the guard to unnamed pairs when they have strong substring match AND co-occur repeatedly (3+ chapters).

### Anti-Pattern 3: Reselecting Clips Per Segment

**What people do:** Pick a different reference clip per synthesis call based on segment emotion.
**Why it is wrong:** Destroys voice consistency -- the whole point of Resemblyzer verification is that each character sounds like their reference. Changing references mid-book guarantees voice drift.
**Do this instead:** Select ONE expressive clip per character at matching time. Use it for all segments.

### Anti-Pattern 4: Modifying VoiceProfile Schema for Overrides

**What people do:** Add "override" fields to VoiceProfile or CharacterProfile.
**Why it is wrong:** Pollutes the extraction model with post-processing concerns. Override data is transient (applied once before writing characters.json), not part of the model.
**Do this instead:** Apply overrides by creating a new VoiceProfile with updated fields, then assigning it to the character. The override YAML is external configuration, not model state.

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| merger.py -> pipeline.py | Return type changes from `list[CharacterProfile]` to `tuple[list[CharacterProfile], dict]` | Audit dict is optional (None when diagnostics=False) |
| pipeline.py -> distinctiveness.py | Direct function call, passes `list[CharacterProfile]` | Only called when --opinionated flag set |
| orchestrator.py -> clip_selector.py | Passes `target_pace` string from character profile | Requires character profiles accessible in orchestrator |
| clip_selector.py -> expressive_scorer.py | Passes WAV path, gets back ExpressiveScore | Pure function, no state |
| voice_prep.py -> expressive_scorer.py | SNR computation moves to shared utility | Avoid duplicating RMS calculation |

### New Dependencies

| Dependency | Already Available | Used For |
|------------|------------------|----------|
| numpy | Yes (via mlx-audio) | Pitch/energy variance computation |
| soundfile | Yes (via voice_prep) | Audio reading for scoring |
| librosa (pyin only) | Indirect via mlx-audio | F0 extraction for pitch variance |
| PyYAML | Yes (via Pydantic) | voice_overrides.yaml loading |

**Note on librosa:** Verify that librosa is importable in the current environment. If not, use a simpler F0 method (autocorrelation via numpy) to avoid adding a heavy dependency. Check with `python -c "import librosa"` before committing to librosa.pyin().

### Existing Artifact Contracts

| Artifact | Schema Changes |
|----------|---------------|
| `characters.json` | None -- VoiceProfile fields may have different VALUES (more opinionated) but same schema |
| `voice_map.json` | Additive: VoiceAssignment gets optional `target_pace` field, `expressive_score` field |
| `attributed.json` | None |
| `segments.json` | None |
| NEW: `merge_audit.json` | New file, not consumed by any downstream phase |
| NEW: `voice_overrides.yaml` | User-created, loaded in pipeline.py |

## Scaling Considerations

| Concern | Current (v1.2) | After v1.3 |
|---------|----------------|------------|
| Merger stages 2-3 | O(n^2) pairwise comparison | Same O(n^2) + co-occurrence lookup (O(1) per pair from pre-built map) |
| Distinctiveness pass | N/A | O(n^2) pairwise VoiceProfile comparison -- trivial for <100 characters |
| Clip scoring | O(k) per speaker, k=clips | O(k * audio_read) per speaker -- 5-10x slower than duration-only but runs once |
| Memory for scoring | Negligible | ~1MB per clip for numpy arrays -- ephemeral, GC'd after scoring |

The expressive scorer reads audio files from disk for each candidate clip. For speakers with many clips (50+), this could take 5-10 seconds per speaker. Pre-filter by duration first (existing behavior), then score the top 5-10 candidates only.

## Sources

- Existing codebase analysis (merger.py, extractor.py, clip_selector.py, voice_prep.py, orchestrator.py, pipeline.py)
- VoiceProfile model definition (attribution/models.py)
- LibriTTS-P annotation format (speaker_index.py)
- Resemblyzer voice consistency verification (voice_verifier.py)

---
*Architecture research for: v1.3 Voice Quality milestone*
*Researched: 2026-03-09*
