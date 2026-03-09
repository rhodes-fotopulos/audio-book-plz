# Project Research Summary

**Project:** audio-book-plz v1.3 Voice Quality
**Domain:** Audiobook generation pipeline -- character merger hardening, opinionated voice profiles, expressive reference clip selection
**Researched:** 2026-03-09
**Confidence:** HIGH

## Executive Summary

The v1.3 milestone addresses three interconnected quality problems in the existing EPUB-to-audiobook pipeline: (1) the character merger produces false-positive merges that contaminate voice profiles, (2) extracted voice profiles are too generic to differentiate similar characters during voice matching, and (3) reference clip selection ignores expressiveness, picking clips purely by duration. All three problems are rooted in well-understood code paths (merger.py, extractor.py, clip_selector.py) and the research identifies specific line-level fixes rather than architectural rewrites.

The recommended approach is strictly sequential: fix the merger first, then improve profile distinctiveness, then upgrade clip selection. This ordering is non-negotiable because each layer depends on clean output from the previous one. Opinionated voice profiles are worthless if they get cross-contaminated during merge, and expressive clip selection cannot rate-match to character pace if the pace field is "unknown" or belongs to the wrong character. The entire v1.3 stack requires zero new pip installs -- librosa and PyYAML are already in the venv as transitive dependencies and just need promotion to explicit deps in pyproject.toml.

The primary risk is cascading merge contamination: one false-positive merge in Stage 2 (fuzzy) snowballs through Stages 3-4, producing mega-profiles that absorb entire casts. This is the root cause driving the milestone and must be fixed with cross-name exclusion, co-occurrence guards on all merge stages, and post-merge validation. Secondary risks include the distinctiveness pass producing internally contradictory profiles (a "gruff old sailor" reassigned to high pitch) and expressive clip scoring that optimizes for raw variance rather than character-profile alignment. Both have clear mitigation strategies documented in the research.

## Key Findings

### Recommended Stack

No new installations required. The existing Python 3.11 + Pydantic + Ollama/Qwen3 + mlx-audio stack handles all v1.3 features. Two transitive dependencies need promotion to explicit deps in pyproject.toml.

**Core technologies:**
- **librosa >=0.10.0** (already installed v0.11.0): Pitch variance via `pyin()`, energy variance via `feature.rms()`, speaking rate via `onset_detect()` -- the three audio analysis functions needed for expressive clip scoring
- **PyYAML >=6.0** (already installed v6.0.3): Load `voice_overrides.yaml` for manual per-character voice profile tuning -- YAML chosen over JSON/TOML because overrides are user-edited config that benefits from comments and clean nesting
- **Existing Ollama + Qwen3 14B**: Handles both opinionated extraction prompts and any LLM-assisted distinctiveness reasoning without adding a new model

**What NOT to add:** parselmouth (heavy C++ binary), crepe (neural pitch tracker needing GPU), opensmile (6000+ features when we need 3), FuzzyWuzzy/rapidfuzz (stdlib SequenceMatcher is sufficient for <100 profiles), networkx (set operations handle co-occurrence).

### Expected Features

**Must have (table stakes):**
- Cross-name exclusion in alias/substring merge -- prevents "Bennet" absorbing all Bennet family members
- Co-occurrence guard on ALL merge stages (currently only on Stage 4 LLM consolidation)
- Surname-only exclusion hardening for 1-part vs multi-part names
- Extraction prompt hardening with negative examples
- Trait count cap (30) to prevent unbounded accumulation
- Merge diagnostics via `merge_audit.json` -- essential for diagnosing merge failures
- Post-merge validation flagging cross-contaminated profiles
- Voice overrides via `voice_overrides.yaml` -- users need manual control when automated matching fails

**Should have (differentiators):**
- Opinionated voice profile extraction (`--opinionated` flag) with sharpened prompts
- Post-extraction distinctiveness pass pushing similar profiles apart
- Expressive reference clip scoring (pitch/energy/rate variance)
- Rate-match reference clips to character profile pace

**Defer:**
- Cross-book voice consistency, full upfront LibriTTS-R feature extraction, LLM-based audio quality assessment, automatic merge auto-correction/splitting, real-time merge visualization

### Architecture Approach

The existing 6-phase sequential pipeline (Parse, Attribute, Match, Synthesize, Verify, Assemble) remains unchanged. All v1.3 changes slot into Phase 2 (Attribute) and Phase 3 (Match) without cross-phase coupling. Two new files are needed: `src/attribution/distinctiveness.py` for the post-merge distinctiveness pass and voice override application, and `src/matching/expressive_scorer.py` for multi-criteria clip scoring. The merger return type changes to include an audit dict, and clip_selector gains a `target_pace` parameter, but all JSON artifact schemas (characters.json, voice_map.json) remain backward-compatible with additive-only field changes.

**Major components:**
1. **merger.py (MODIFY)** -- Cross-name exclusion, co-occurrence on all 4 stages, trait cap, merge diagnostics, post-merge validation
2. **distinctiveness.py (NEW)** -- Deterministic rule-based push of similar voice profiles apart, voice override YAML loading and application
3. **expressive_scorer.py (NEW)** -- Pitch/energy/rate variance computation via librosa, multi-criteria composite scoring with character-profile alignment

**Key data flow change:** extract -> merge (hardened) -> merge_audit.json -> push_voices_apart (--opinionated) -> apply_voice_overrides -> characters.json -> trait_matcher -> clip_selector (multi-criteria) -> voice_map.json

### Critical Pitfalls

1. **Cascading merge contamination** -- `_merge_two_profiles()` blindly unions all aliases and traits. One false positive in Stage 2 snowballs through Stages 3-4, absorbing entire casts. **Avoid:** Cross-name exclusion set rebuilt before each stage, trait count cap at 30, post-stage validation.

2. **Substring match false positives on short names** -- "Ann" matches "Annabelle", "Jane" matches "Jane Fairfax" via character-level substring. **Avoid:** Require word-boundary matching (split by space), cross-name exclusion blocks absorption when the short name is another character's canonical name.

3. **Opinionated extraction returns cached conservative results** -- Cache key does not include extraction mode, so `--opinionated` silently gets old profiles. **Avoid:** Include extraction mode in cache key (`extraction_v2` vs `extraction_v2_opinionated`).

4. **Distinctiveness pass produces incoherent profiles** -- Pushing a "gruff old sailor" to high pitch optimizes inter-character distinctiveness at the cost of intra-profile coherence. **Avoid:** Only change the least-constrained dimension, cap changes to 2-3 fields per profile, include character description as context.

5. **Expressive clip scoring ignores character profile** -- High-variance clips are "most expressive" but wrong for calm characters. **Avoid:** Use character pace/energy for primary filtering, expressiveness as tiebreaker. Rate-match is the primary signal, not raw variance.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Merger Hardening

**Rationale:** The merger is the root cause of the v1.3 milestone. Every downstream feature (opinionated profiles, expressive clips) depends on correctly-merged character profiles. One false positive merge cascades through the entire pipeline. Fix the foundation first.
**Delivers:** Reliable character deduplication with full audit trail, cross-name exclusion on all 4 merge stages, co-occurrence guards on stages 2-3 (extending existing stage 4 guard), surname-only hardening for 1-part names, trait count cap, post-merge validation, merge_audit.json
**Addresses:** All 7 table-stakes features from FEATURES.md (cross-name exclusion, co-occurrence guard, surname-only hardening, extraction prompt hardening, trait cap, merge diagnostics, post-merge validation)
**Avoids:** Pitfall 1 (cascading contamination), Pitfall 2 (substring false positives), Pitfall 7 (LLM consolidation on contaminated profiles)
**Stack:** Pure Python + Pydantic (no new deps)
**Estimated complexity:** ~250 LOC new code, heavy modification of merger.py

### Phase 2: Opinionated Voice Profiles

**Rationale:** With clean merged profiles from Phase 1, the pipeline can now produce distinctive, character-appropriate voice descriptions. This phase transforms generic "medium pitch, moderate pace" profiles into polarized, differentiated voice characteristics that enable meaningful voice matching.
**Delivers:** `--opinionated` CLI flag, sharpened extraction prompt, deterministic distinctiveness pass (`push_voices_apart()`), voice override loading and application from `voice_overrides.yaml`
**Addresses:** All 4 differentiator features from FEATURES.md (opinionated extraction, distinctiveness pass, extraction-time sharpening, voice overrides)
**Avoids:** Pitfall 3 (generic opinionated profiles -- two prompt variants needed), Pitfall 4 (contradictory distinctiveness -- constrain changes to least-anchored fields), Pitfall 6 (overrides silently ignored -- apply LAST, validate against VoiceProfile schema)
**Stack:** PyYAML (promote to explicit dep), existing Ollama/Qwen3 for extraction
**Estimated complexity:** ~280 LOC new code (distinctiveness.py + voice_overrides), prompt modifications in extractor.py

### Phase 3: Expressive Reference Clip Selection

**Rationale:** With distinctive, correctly-merged voice profiles, clip selection can now match clips to character traits rather than just duration. This is the highest-complexity phase (audio I/O intensive) but produces the most audible improvement in final audiobook quality.
**Delivers:** Multi-criteria clip scoring (duration 0.3 + SNR 0.3 + pitch variance 0.15 + energy variance 0.15 + rate match 0.1), character-profile-aware clip selection, lazy computation with per-speaker caching
**Addresses:** Expressive clip scoring and rate-matching differentiator features from FEATURES.md
**Avoids:** Pitfall 5 (clip scoring ignores character context -- rate-match and energy-match are primary signals, raw variance is tiebreaker)
**Stack:** librosa (promote to explicit dep), numpy (existing)
**Estimated complexity:** ~300 LOC new code (expressive_scorer.py), modification of clip_selector.py and orchestrator.py

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** Opinionated profiles on contaminated merges produce wrong voice assignments. The merger is the data quality foundation.
- **Phase 2 before Phase 3:** Expressive clip selection uses `VoiceProfile.pace` for rate-matching. If pace is "unknown" (non-opinionated default), rate-matching degrades to a no-op. Distinctive profiles make clip selection meaningful.
- **Extraction prompt hardening in Phase 1, not Phase 2:** The prompt change improves raw extraction quality for ALL features. It also invalidates the extraction cache, so it should happen early to avoid re-running extraction later.
- **Voice overrides in Phase 2, not as independent phase:** Overrides are low-complexity (~80 LOC) and share the same integration point (distinctiveness.py) as the distinctiveness pass. Grouping them avoids touching pipeline.py twice.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Opinionated Profiles):** The distinctiveness pass design needs careful constraint specification -- which fields are "anchored" by text evidence vs. freely modifiable. The architecture research recommends deterministic rule-based push (no LLM), but PITFALLS.md warns this can produce incoherent profiles. Needs design iteration.
- **Phase 3 (Expressive Clips):** The scoring weight calibration (0.4/0.35/0.25 in STACK.md vs 0.3/0.3/0.15/0.15/0.1 in ARCHITECTURE.md) is unvalidated. Needs empirical tuning against actual LibriTTS-R data. Pitch variance normalization factor and pace thresholds need calibration.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Merger Hardening):** All changes are in well-understood code paths (merger.py). The fixes are set operations, guard checks, and Pydantic models. No novel patterns. The codebase analysis provides line-number-level integration points.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new installs. Both libraries verified present in venv with correct versions. All integration points confirmed in codebase. |
| Features | HIGH | Feature list derived from PROJECT.md active requirements and codebase analysis. Dependency ordering verified against actual data flow. |
| Architecture | HIGH | All integration points reference specific files and line numbers in existing codebase. Phase boundaries and artifact contracts confirmed unchanged. |
| Pitfalls | HIGH | Every pitfall references specific code paths (merger.py lines 250-315, extractor.py lines 43-87, etc.) with concrete reproduction scenarios. |

**Overall confidence:** HIGH -- All research is grounded in actual codebase analysis, not hypothetical patterns. The v1.3 features are incremental improvements to an existing, working pipeline.

### Gaps to Address

- **Expressiveness scoring weights:** The optimal balance between duration, SNR, pitch variance, energy variance, and rate-match is unknown. STACK.md proposes 0.4/0.35/0.25 (3-factor), ARCHITECTURE.md proposes 0.3/0.3/0.15/0.15/0.1 (5-factor). Needs A/B testing during Phase 3 implementation.
- **Pitch variance normalization:** Dividing by 50.0 Hz for normalization may need per-gender tuning (male F0 range differs from female). Validate against LibriTTS-R speaker distribution.
- **Distinctiveness pass constraint design:** Whether to use deterministic rules (ARCHITECTURE.md recommendation) or LLM with context (PITFALLS.md alternative). The rule-based approach is faster and more predictable but less nuanced. Resolve during Phase 2 planning.
- **Cache invalidation for opinionated mode:** The extraction cache key must include the prompt variant. Implementation detail, but missing it causes a silent, hard-to-diagnose failure (Pitfall 3).

## Sources

### Primary (HIGH confidence)
- Codebase analysis: merger.py (697 LOC), extractor.py (354 LOC), clip_selector.py (172 LOC), trait_matcher.py (407 LOC), orchestrator.py (311 LOC), models.py (VoiceProfile schema)
- Installed package verification: librosa 0.11.0, PyYAML 6.0.3, numpy 2.4.2, scipy 1.17.1, soundfile 0.13.1 confirmed in venv
- PROJECT.md v1.3 milestone definition and known root causes

### Secondary (MEDIUM confidence)
- librosa documentation: pyin(), feature.rms(), onset.onset_detect() API and parameters
- PyYAML safe_load documentation
- LibriTTS-R dataset characteristics (24kHz mono 16-bit WAV, ~2,443 speakers)
- Qwen3-TTS voice cloning behavior (reference clip prosodic range influences output)

### Tertiary (LOW confidence)
- Expressiveness scoring weight proposals (need empirical calibration)
- Pitch variance normalization factors (need per-gender tuning)
- Speaking rate thresholds for pace matching (need LibriTTS-R calibration)
- Whether higher expressiveness clips actually improve TTS voice cloning quality (reasonable assumption, unvalidated)

---
*Research completed: 2026-03-09*
*Ready for roadmap: yes*
