# Feature Landscape

**Domain:** Audiobook voice quality -- merger hardening, opinionated voice profiles, expressive clip selection
**Researched:** 2026-03-09

## Table Stakes

Features users expect. Missing = the v1.3 milestone delivers no perceptible improvement.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| Cross-name exclusion in alias/substring merge | Without this, `_names_match_substring` merges any name containing another as a substring regardless of whether the shorter name is a *different* character's canonical name. "Elizabeth" substring-matches into "Elizabeth Bennet" correctly, but also lets "Bennet" absorb into "Mr. Bennet" when "Mrs. Bennet" exists. | Low | Existing merger stages 1-3 | Build a set of all canonical names + aliases across all profiles. Before any substring/alias merge, check if the candidate's name appears in this cross-name set for a *different* profile. If so, block the merge. Simple set lookup against the full registry. |
| Co-occurrence guard on ALL merge stages | Currently only applied in stage 4 (LLM consolidation). Stages 1-3 (exact, fuzzy, substring/alias) merge blindly. Two characters who share a name variant but appear as separate speakers in the same chapter get incorrectly merged. | Med | `_build_cooccurrence` exists, needs threading through stages 1-3 | The current `merge_characters` function flattens `chapter_characters` into `all_profiles` immediately, losing chapter provenance. Must either (a) tag each profile with its source chapter(s) before flattening, or (b) pass `chapter_characters` to each stage function. Option (a) is cleaner -- add a `source_chapters: set[int]` transient field to CharacterProfile or use a wrapper. |
| Surname-only exclusion hardening | `_names_share_surname_only` requires both names to have 2+ parts. "Darcy" (1 part) vs "Mr. Darcy" (2 parts) bypasses the guard, allowing substring merge. Same problem with "Bennet" vs "Mrs. Bennet". | Low | Existing `_names_share_surname_only`, `TITLES` set | Extend to handle 1-part vs multi-part: if one name is a single word matching the last word of a multi-part name, and the multi-part name's prefix is a known title, treat as surname-only match and block. The `TITLES` set already exists. |
| Extraction prompt hardening with negative examples | Current `EXTRACTION_SYSTEM_PROMPT` has abstract rules against cross-contamination ("Never list another character's name as an alias") but no concrete negative examples. LLMs follow few-shot negative examples far more reliably than instruction text. | Low | `EXTRACTION_SYSTEM_PROMPT` in `extractor.py` | Add 2-3 negative examples: "WRONG: Character 'Jane Bennet' with aliases ['Elizabeth', 'Lizzy']. Elizabeth and Lizzy belong to Elizabeth Bennet, a DIFFERENT character. CORRECT: Character 'Jane Bennet' with aliases ['Jane', 'Miss Bennet']." Keep concise to avoid consuming context window budget. |
| Trait count cap (30) with overflow handling | After merging 40+ chapters of per-chapter character extractions, `personality_traits` accumulates unbounded near-synonyms via `dict.fromkeys` dedup. A character appearing in 30 chapters may have 50+ traits. This bloats the LLM casting prompt and confuses the trait matcher. | Low | `_merge_two_profiles` in `merger.py` | After union, if count > 30, truncate to 30. Simple approach: keep the first 30 (preserves earliest/most repeated traits since `dict.fromkeys` preserves insertion order). Better approach: group near-synonyms and keep one per group, but this adds complexity for marginal value. Start with simple truncation. |
| Merge diagnostics with `merge_audit.json` | When a merge goes wrong, there is no way to diagnose which stage caused it. Only `logger.debug` calls exist, and those disappear in normal log levels. | Low | All merger stages | Accumulate audit entries during merge: `{stage: "fuzzy", merged_from: "Miss Darcy", merged_into: "Georgiana Darcy", reason: "title_name_match", blocked: false}`. Write to `book_dir/merge_audit.json` after completion. Include blocked merges too (shows what the system considered and rejected). |
| Post-merge validation flagging cross-contaminated profiles | No automated check that the final registry is sane. Cross-contaminated profiles (Mrs. Bennet with Mr. Bennet's traits, or Elizabeth with Jane's voice profile) silently propagate to voice matching and produce wrong voice assignments. | Med | Merge diagnostics (for context when flagging) | After merge completes, validate: (1) No profile's alias list contains another profile's canonical name. (2) Gender in voice_profile description does not contradict profile gender. (3) Description does not reference a different character by name. Emit warnings, do not auto-fix (user decides via voice overrides). |
| Voice overrides via `voice_overrides.yaml` | Users cannot manually fix a bad voice match without deleting `voice_map.json` and hoping the LLM picks differently. For a pipeline that takes hours to run, this is unacceptable. | Low | `voice_map.json` schema, orchestrator | Load `voice_overrides.yaml` from `book_dir` at start of `run_matching`. Format: `{character_name: {speaker_id: "1234"}}` for direct speaker override, or `{character_name: {voice_profile: {pitch: "low", tone: "gruff"}}}` to override profile traits before matching. Direct speaker_id skips matching entirely for that character. |

## Differentiators

Features that set the product apart. Not expected, but produce noticeably better audiobooks.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| Opinionated voice profile extraction (`--opinionated` flag) | Current extraction produces generic profiles: many characters get "medium pitch, moderate pace, warm tone" because the LLM defaults to safe middle values when text evidence is sparse. This makes voice matching nearly random for similar characters because the trait matcher cannot distinguish between identical profiles. Opinionated extraction forces distinctive, polarized traits. | Med | Existing extraction prompt, VoiceProfile model | Two complementary mechanisms: (1) Sharpen the extraction prompt to demand commitment ("Never use 'medium' or 'moderate' -- choose a direction"), (2) Post-extraction distinctiveness pass where the LLM sees ALL profiles and pushes similar ones apart. Mechanism 2 is more important because extraction sees only one chapter at a time and cannot compare across characters. |
| Post-extraction distinctiveness pass | The core mechanism behind opinionated profiles. After all profiles are merged, compare voice profiles pairwise. When two same-gender characters have near-identical profiles, invoke the LLM to differentiate them. "Two young female characters both have 'warm tone, moderate pace' -- give one 'clipped, bright' and the other 'languid, honeyed'." | Med | Merged character registry, LLM client | Input: complete character list. Output: revised profiles with more distinctive trait combinations. Constraints: only modify voice_profile fields, never name/aliases/gender/age_range. Must run AFTER merge hardening but BEFORE voice matching. Gate behind `--opinionated` flag so users can opt out. |
| Extraction-time voice profile sharpening | Complement to post-extraction pass. Modify the extraction prompt to demand specific, non-generic traits from the start. Add examples: "Instead of 'medium pitch, warm tone', write 'tenor pitch, honeyed tone with an edge of impatience'." | Low | Extraction prompt only | Less effective alone than the distinctiveness pass (extraction sees one chapter, not the full cast), but produces richer raw material for the distinctiveness pass to work with. Use both together. |
| Expressive reference clip scoring (pitch/energy/rate variance) | Current `clip_selector.py` scores clips purely by closeness to 12.5s target duration. A monotone 12.5s clip is rated higher than an expressive 10s clip. Qwen3-TTS mirrors the reference clip's prosodic range during voice cloning -- a flat reference produces flat output, an expressive reference produces expressive output. | High | `clip_selector.py`, `librosa` for audio analysis | Per-clip feature extraction: (a) pitch variance via `librosa.pyin` (F0 contour variance), (b) RMS energy variance (dynamic range), (c) speaking rate estimate via voiced-frame ratio from VAD or syllable density. Combine into composite expressiveness score. Scoring weights: 40% expressiveness, 30% SNR, 30% duration fitness. HIGH complexity because this requires loading and analyzing WAV files for every candidate clip (dozens per speaker), which is I/O and compute intensive on the full LibriTTS-R dataset. |
| Rate-match reference clips to character profile pace | Beyond generic expressiveness: if a character's profile says "slow, measured speech", prefer clips with lower speaking rate. If "rapid, energetic", prefer clips with higher rate. The cloned voice inherits the reference clip's speaking rate tendencies. | Med | Expressive clip scoring (needs rate measurement already computed), VoiceProfile.pace field | After computing per-clip speaking rate, segment the rate distribution into tertiles. Map profile pace: "slow" -> bottom tertile, "moderate" -> middle, "fast" -> top. Apply as a filter before expressiveness scoring. Falls back to expressiveness-only if pace is "unknown" or if the tertile has too few candidates. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Automatic speaker reassignment based on voice similarity | Tempting to auto-swap speaker IDs when Resemblyzer detects a "better" match elsewhere in the dataset. Breaks user trust, makes results unpredictable between runs, and creates action-at-a-distance where changing one character's profile affects another's voice. | Provide voice overrides YAML for manual control. Flag weak matches with warnings but let the user decide. |
| Full upfront audio feature extraction for all LibriTTS-R clips | Pre-computing pitch/energy/rate for all 2,443 speakers' clips would take hours and require significant disk for cached features. Most speakers are never considered for any given book. | Compute features lazily: only for the ~10-30 candidate speakers that survive gender/age filtering for each character. Cache per-speaker features in a `.cache/clip_features/` directory after first computation. |
| LLM-based audio quality assessment | Sending audio descriptions or spectrogram summaries to the LLM for quality scoring. Adds an LLM call per clip (hundreds of calls), the LLM has no actual audio understanding, and results are non-deterministic. | Use signal-processing metrics (SNR via waveform analysis, pitch variance via librosa) which are objective, fast, and deterministic. |
| Cross-book voice consistency | Maintaining the same voice assignments across different books. Adds persistent state, cross-book coupling, and rarely matches user expectations (same actor should sound different as different characters). | Each book is independent. If users want consistency, they copy voice_overrides.yaml between books. |
| Real-time merge visualization (TUI/GUI) | Over-engineering for a batch CLI tool. The merge runs once per book and takes seconds. | Emit `merge_audit.json` for post-hoc analysis. Log merge decisions at INFO level for real-time monitoring. |
| Automatic personality-to-acoustic-feature mapping | Building deterministic rules like "shy = quiet voice, assertive = loud voice". Personality is a narrative quality, not an acoustic one. A shy character might whisper OR might speak normally and show shyness through word choice. | Keep personality traits as context for the LLM casting director prompt (it handles nuance), but do not build acoustic parameter rules from personality. |
| Merger auto-correction (split incorrectly merged profiles) | Detecting and automatically reversing bad merges in a post-merge pass. The signals for "this merge was wrong" are weak (shared traits could be correct or contaminated), and auto-splitting creates worse problems than manual re-extraction. | Flag suspicious profiles in post-merge validation. User can re-run extraction with cache cleared for specific chapters, or use voice overrides to correct downstream effects. |

## Feature Dependencies

```
Extraction prompt hardening (independent, do first -- improves raw data quality)
    |
    v
Cross-name exclusion -----> Co-occurrence guard on all stages -----> Surname-only hardening
    |                              |
    v                              v
Trait count cap              Merge diagnostics (merge_audit.json)
                                   |
                                   v
                             Post-merge validation
                                   |
                                   v
              +--------------------+--------------------+
              |                                         |
              v                                         v
    Opinionated voice profiles                Voice overrides (YAML)
              |                                   (independent, can
              +-- Extraction-time sharpening       slot in anywhere)
              |   (complementary, do together)
              v
    Post-extraction distinctiveness pass
              |
              v
    Expressive reference clip scoring
              |
              v
    Rate-match clips to character pace
```

**Key ordering rationale:**

1. **Merger hardening before opinionated profiles.** No point making profiles more distinctive if they get cross-contaminated during merge. A sharpened "Mrs. Bennet: shrill, rapid, high-pitched" profile is worthless if it gets merged with "Mr. Bennet: dry, measured, low baritone" due to surname-only matching.

2. **Extraction prompt hardening is independent and cheap.** Do it first because it improves raw extraction quality for all downstream features and costs only a prompt edit (no code changes beyond the prompt string).

3. **Post-merge validation before distinctiveness pass.** The distinctiveness pass modifies profiles. We need validation to confirm profiles are clean *before* modification, and again *after* to confirm the pass did not introduce problems.

4. **Expressive clip scoring depends on good profiles** for rate matching, but the base expressiveness scoring (pitch/energy variance + SNR + duration) works independently. Rate matching is an enhancement on top.

5. **Voice overrides are fully independent.** They apply at the voice matching stage and require no changes to merger or extraction. Can be implemented at any point, but most useful after the pipeline produces better profiles.

## MVP Recommendation

**Phase 1 -- Merger Hardening (all table stakes, do first):**

Prioritize:
1. Extraction prompt hardening with negative examples
2. Cross-name exclusion in alias/substring merge
3. Co-occurrence guard on all merge stages
4. Surname-only exclusion hardening
5. Trait count cap (30) with overflow handling
6. Merge diagnostics (`merge_audit.json`)
7. Post-merge validation

**Phase 2 -- Opinionated Voice Profiles (differentiator):**

Prioritize:
1. Extraction-time voice profile sharpening (prompt changes)
2. Post-extraction distinctiveness pass (new LLM step)
3. `--opinionated` flag gating the new behavior
4. Voice overrides via `voice_overrides.yaml`

**Phase 3 -- Expressive Clip Selection (differentiator):**

Prioritize:
1. Expressive reference clip scoring (pitch/energy/rate variance + SNR + duration composite score)
2. Rate-match reference clips to character profile pace
3. Lazy computation with per-speaker feature caching in `.cache/clip_features/`

**Defer:** Cross-book consistency, full upfront feature extraction, LLM audio assessment, merge auto-correction.

## Complexity Budget

| Feature Group | Estimated Complexity | New Code | Existing Code Modified |
|---------------|---------------------|----------|----------------------|
| Merger hardening | Medium overall (each item is Low, but 7 items together) | ~250 LOC (audit system, validation checks, cross-name index) | `merger.py` (co-occurrence threading, guards in stages 1-3), `extractor.py` (prompt only) |
| Opinionated profiles | Medium | ~200 LOC (distinctiveness pass LLM call, profile comparison, `--opinionated` flag) | `extractor.py` (prompt sharpening), `pipeline.py` (new step between merge and match) |
| Expressive clips | High | ~300 LOC (audio feature extraction, composite scoring, caching) | `clip_selector.py` (new scoring replaces duration-only), possible new `audio_features.py` module |
| Voice overrides | Low | ~80 LOC (YAML loader, override application) | `orchestrator.py` (load overrides at start of `run_matching`, apply before/after matching) |

## Sources

- Codebase analysis: `src/attribution/merger.py` (697 LOC, 4-stage merge pipeline), `src/attribution/extractor.py` (354 LOC, per-chapter LLM extraction), `src/matching/clip_selector.py` (172 LOC, duration-only scoring), `src/matching/trait_matcher.py` (407 LOC, LLM casting director), `src/matching/orchestrator.py` (311 LOC, end-to-end matching)
- `src/attribution/models.py` (VoiceProfile with 9 fields, CharacterProfile schema)
- `.planning/PROJECT.md` (v1.3 milestone definition, active requirements list)
- LibriTTS-R dataset: 24kHz mono 16-bit WAV, normalized transcripts, ~2,443 speakers (HIGH confidence, confirmed by existing codebase usage)
- Qwen3-TTS voice cloning behavior: reference clip prosodic range directly influences cloned output expressiveness (HIGH confidence, established through v1.1/v1.2 development)
- librosa pitch tracking: `librosa.pyin` for fundamental frequency estimation is the standard approach for pitch variance measurement (HIGH confidence, well-established library)
