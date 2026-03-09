# Pitfalls Research: v1.3 Voice Quality

**Domain:** Merger hardening, opinionated voice profiles, and expressive reference clip selection for existing audiobook generation pipeline
**Researched:** 2026-03-09
**Confidence:** HIGH -- Grounded in actual codebase analysis of merger.py (697 lines), extractor.py (354 lines), clip_selector.py (172 lines), trait_matcher.py (407 lines), and models.py. All pitfalls reference specific code paths, not hypothetical patterns.

---

## Critical Pitfalls

### Pitfall 1: Cascading Merge Contamination from _merge_two_profiles() Blind Union

**What goes wrong:**
`_merge_two_profiles()` (merger.py line 250-315) unions ALL aliases and ALL personality_traits from both profiles with zero filtering. When a false-positive merge occurs -- e.g., a fuzzy match incorrectly links "Mrs. Bennet" to "Elizabeth Bennet" -- every subsequent merge stage inherits the contaminated alias set and trait list. The alias set now contains names of BOTH characters, which triggers _alias_overlap() on future comparisons, pulling in even more unrelated characters. One bad merge in Stage 2 (fuzzy) cascades through Stage 3 (substring/alias) and Stage 4 (LLM consolidation), producing a mega-profile with 200+ traits and aliases spanning the entire cast.

The root cause is that merges are applied greedily and irreversibly within each stage. Once `current = _merge_two_profiles(current, candidate)` executes on line 234, the contaminated profile replaces the original for all subsequent comparisons in the same loop iteration.

**Why it happens:**
The merger was designed for the common case where merges are correct. There is no validation between merge stages, no trait cap, and no cross-name exclusion. The `_names_share_surname_only()` guard (line 60-91) only fires for names with 2+ parts, so it misses "Elizabeth" matching as a substring of "Elizabeth Bennet" when the other profile's canonical name is just "Bennet" (1 part).

**How to avoid:**
1. **Cross-name exclusion list**: Before merging A into B, check that none of A's aliases appear as canonical names of OTHER profiles in the registry. If "Jane" is a canonical name for profile #3, it cannot be absorbed as an alias of profile #7 ("Mrs. Bennet"). Build the exclusion set once before each stage starts: `protected_names = {p.name.lower() for p in profiles}`.
2. **Trait count cap**: After every `_merge_two_profiles()` call, truncate `personality_traits` to 30 items (configurable). Keep the first N traits since primary profile traits come first in the deduplicated union. Log a warning when capping triggers.
3. **Post-stage validation**: After each merge stage, scan for profiles whose alias set intersects with another profile's canonical name set. Flag these as likely false positives and reverse the merge (keep both profiles separate).
4. **Immutable originals**: Store original pre-merge profiles in a list. If post-stage validation detects contamination, restore from originals instead of trying to untangle the merged result.

**Warning signs:**
- A profile with more than 30 personality_traits after merging
- A profile whose aliases include canonical names of other profiles in the registry
- Total profile count dropping by more than 40% through the merge pipeline
- A single profile accumulating aliases that span both genders (e.g., "Mr. Darcy" and "Elizabeth" as aliases of the same profile)

**Phase to address:**
Phase 1 (merger hardening). This is the core bug driving the entire milestone. Fix before anything else.

---

### Pitfall 2: Substring Match False Positives on Common Name Components

**What goes wrong:**
`_names_match_substring()` (merger.py line 33-57) returns True when one name contains the other as a substring, with only a MIN_SUBSTRING_LENGTH=3 guard. This produces false positives for common English name fragments:
- "Ann" matches "Anne", "Anna", "Annabelle", "Joanna", "Marianne" -- all different characters
- "Ben" matches "Bennet", "Benedict", "Benjamin"
- "Will" matches "William", "Willoughby"
- "Jane" matches "Jane Bennet", "Jane Fairfax" -- could be different Janes in different novels

The surname-only guard (`_names_share_surname_only`) requires BOTH names to have 2+ parts, so it cannot block "Jane" (1 part) from matching "Jane Fairfax" (2 parts). Once merged, the alias set of "Jane Fairfax" now contains "Jane", which then matches any other profile with "Jane" as a substring.

**Why it happens:**
Substring matching is inherently aggressive. The MIN_SUBSTRING_LENGTH=3 threshold was set to exclude "I", "Mr", etc., but common 3-4 letter name fragments are legitimate given names in English literature.

**How to avoid:**
1. **Raise MIN_SUBSTRING_LENGTH to 4** and require the shorter name to be a WORD BOUNDARY match, not just a substring. "Ann" should not match "Annabelle" but "Jane" should match "Miss Jane Bennet" (where "Jane" appears as a complete word).
2. **Cross-name exclusion**: If "Jane" is a canonical name for ANY profile in the current registry, do not allow it to be matched as a substring of another profile's name. This is the same exclusion list from Pitfall 1.
3. **Require the substring match to be on a name PART (split by space)**, not a character-level substring. "Jane" in "Jane Fairfax" is a word match (good). "Ann" in "Annabelle" is a character-level substring (bad).

**Warning signs:**
- Characters with short first names (3-4 letters) getting merged with unrelated characters
- Merge log showing substring matches on character substrings rather than word boundaries
- Multiple characters sharing a common name component all collapsing into one profile

**Phase to address:**
Phase 1 (merger hardening). Fix alongside the cross-name exclusion from Pitfall 1.

---

### Pitfall 3: Opinionated Voice Profiles Without Extraction Prompt Changes Produce Generic Descriptions

**What goes wrong:**
The current extraction prompt (extractor.py line 43-87) instructs the LLM to use "unknown" when unsure about a trait. This is correct for accuracy but produces voice profiles where most characters get `pitch: "unknown"`, `pace: "unknown"`, `tone: "unknown"` -- the exact opposite of "opinionated." Adding a post-extraction distinctiveness pass cannot fix profiles that are mostly "unknown" because there is nothing distinctive to work with.

The planned `--opinionated` flag needs the LLM to make INFERENCES from character personality, dialogue style, and narrative description rather than leaving fields as "unknown." This requires fundamentally different extraction prompt instructions, not just a post-processing step.

**Why it happens:**
The "unknown when unsure" instruction was the right call for v1.0-v1.2 where accuracy mattered more than distinctiveness. But opinionated profiles need a different philosophy: "always infer something reasonable, never return unknown." These are contradictory instructions that cannot coexist in a single prompt without the `--opinionated` flag changing the entire prompt text.

**How to avoid:**
1. **Two extraction prompts**: Keep the current conservative prompt as default. Create an opinionated variant that replaces "When unsure about a trait, use unknown" with "Always infer voice characteristics from the character's personality, age, social class, and dialogue style. A grumpy old man should have low pitch, slow pace, gruff tone -- do not leave these as unknown."
2. **Add negative examples to the opinionated prompt**: Show the LLM what a BAD opinionated profile looks like (all medium/neutral values for every character) vs. a GOOD one (distinctive, exaggerated traits that differentiate characters from each other).
3. **Extraction cache invalidation**: The opinionated prompt will produce different character profiles from the same chapter text. The cache key must include the prompt variant (`extraction_v2` vs `extraction_v2_opinionated`) or all opinionated runs will return cached conservative results.

**Warning signs:**
- Running with `--opinionated` but getting the same voice profiles as without it (cache hit on old extraction)
- Opinionated profiles where most characters still have `pace: "moderate"`, `energy: "moderate"`, `tone: "neutral"` -- the LLM defaulted to safe middle values instead of truly unknown
- All characters sounding similar despite opinionated extraction (the distinctiveness pass cannot differentiate profiles that use the same moderate values)

**Phase to address:**
Phase 2 (opinionated voice profiles). Must change the extraction prompt, not just add a post-processing pass. Cache invalidation is critical.

---

### Pitfall 4: Distinctiveness Pass Produces Contradictory Profiles When Pushing Characters Apart

**What goes wrong:**
A post-extraction distinctiveness pass that "pushes similar voices apart" can produce internally contradictory profiles. If two characters both have `pitch: "low"` and `tone: "warm"`, the pass might change one to `pitch: "high"` -- but that character is described as "a gruff old sailor." A high-pitched gruff old sailor is absurd. The pass optimizes for inter-character distinctiveness at the cost of intra-profile coherence.

Worse, if the distinctiveness pass uses an LLM, it may not have access to the original chapter text. It only sees the profiles in isolation and has no way to verify that the modified traits are consistent with the source material.

**Why it happens:**
Distinctiveness is a pairwise property (character A vs B) while profile coherence is a unary property (character A's traits should make sense together). Optimizing one can degrade the other. This is the classic fairness-accuracy tradeoff applied to voice casting.

**How to avoid:**
1. **Constrain the distinctiveness pass to fields without strong textual evidence**. If the extraction found `pitch: "low"` from "the old man grumbled in a deep voice," that pitch is ANCHORED and should not change. Only push apart traits that were inferred (not explicitly stated in text).
2. **Use the distinctiveness pass to ADD differentiating traits, not CHANGE existing ones**. If two characters both have `pitch: "low"`, differentiate on pace, energy, or tone_style instead of changing pitch. The pass should look for the LEAST constrained dimension to push apart on.
3. **Include the character description and personality traits as context for the LLM distinctiveness pass**. The LLM needs to know "gruff old sailor" before deciding which traits can change.
4. **Cap changes per profile**: The distinctiveness pass can modify at most 2-3 fields per profile. If more changes are needed, the extraction prompt should be improved instead.

**Warning signs:**
- Post-distinctiveness profiles where voice description contradicts individual trait fields
- Characters whose voice profiles changed so much that the voice_profile.description no longer matches the traits
- Listen tests where a character's voice does not match their described personality at all

**Phase to address:**
Phase 2 (opinionated voice profiles). Design the constraint system before implementing the LLM distinctiveness pass.

---

### Pitfall 5: Expressive Clip Scoring Ignores the Clip Content Relevance to Character

**What goes wrong:**
The current `clip_selector.py` selects clips purely by duration (closest to 12.5s target). The planned expressive scoring adds pitch/energy/rate variance metrics. But a clip with high pitch variance might be a dramatic reading of Shakespeare -- great variance metrics, terrible reference for a calm, measured character like Mr. Darcy. The scoring becomes a "most expressive clip" selector rather than a "best reference for THIS character" selector.

The fundamental issue: expressive scoring ranks clips by how INTERESTING they sound, not by how well they match the target character's voice profile.

**Why it happens:**
Pitch/energy/rate variance are speaker-independent acoustic features. They tell you about the recording, not about whether the recording matches a specific character profile. High variance is desirable for an animated character but wrong for a monotone one.

**How to avoid:**
1. **Rate-match clips to character profile pace**: If character has `pace: "slow"`, prefer clips with lower speaking rate. If `pace: "fast"`, prefer higher rate clips. This is explicitly in the milestone requirements ("rate-matching to character profiles") but easy to implement as an afterthought instead of as the primary scoring signal.
2. **Energy-match to character energy**: If character has `energy: "restrained"`, prefer clips with lower energy variance (more consistent, subdued delivery). If `energy: "animated"`, prefer high variance.
3. **Use variance scoring as a TIEBREAKER, not primary signal**: First filter by rate/energy match to character profile, THEN among matching clips, prefer ones with richer variance (better for voice cloning quality). The primary signal should be character-profile alignment, not raw expressiveness.
4. **SNR remains the floor filter**: Keep the existing SNR filtering as a minimum quality gate before any expressiveness scoring. A noisy clip with perfect expressiveness is still a bad reference.

**Warning signs:**
- All characters getting clips from the same few highly-expressive speakers (the scoring always picks dramatic readings)
- Calm characters sounding agitated because their reference clip was an expressive dramatic passage
- Clip selection results that do not vary based on character profile (expressiveness score dominates, character match is irrelevant)

**Phase to address:**
Phase 3 (expressive reference clips). Must integrate character profile data into clip scoring, not just acoustic features.

---

### Pitfall 6: voice_overrides.yaml Silently Ignored Due to Load Order or Missing Schema Validation

**What goes wrong:**
The `voice_overrides.yaml` feature lets users manually specify voice traits per character. The pitfall is a silent failure mode: the file is loaded but its values are overwritten by extraction results (if loaded before extraction) or by the distinctiveness pass (if loaded before distinctiveness). The override must be applied LAST in the pipeline to actually take effect, but there is no validation that it was applied or that it changed anything.

A second failure mode: the YAML schema is not validated. A user writes `pitch: loud` (invalid value for pitch, should be energy) and the override silently passes through Pydantic as-is (strings are strings). The invalid value then confuses downstream voice matching.

**Why it happens:**
Override systems need clear documentation of WHEN in the pipeline they apply and WHAT values are valid. Without validation, YAML is a stringly-typed footgun.

**How to avoid:**
1. **Apply overrides AFTER all automated processing** (extraction, merging, distinctiveness). The pipeline should be: extract -> merge -> opinionated pass -> distinctiveness pass -> apply overrides. Overrides are final, non-negotiable values.
2. **Validate override YAML against the VoiceProfile schema**. Use Pydantic to parse each override entry. Reject unknown fields and provide clear error messages for invalid values.
3. **Log each override application**: "Applied voice override for 'Mr. Darcy': pitch changed from 'medium' to 'low', tone changed from 'warm' to 'cold'". This makes overrides auditable.
4. **Warn if an override character name does not match any character in the registry**. Typos in character names should not silently pass.

**Warning signs:**
- User specifies overrides but voice matching results do not change
- No log output mentioning override application
- Override YAML with invalid field names or values loads without error
- Override applied to a character name that does not exist in the merged registry (typo)

**Phase to address:**
Phase 2 (opinionated voice profiles). Design the override application point and validation before implementing the YAML loading.

---

### Pitfall 7: LLM Consolidation Stage Operates on Already-Contaminated Profiles

**What goes wrong:**
The LLM consolidation stage (merger.py line 451-578) runs AFTER fuzzy matching and substring/alias matching. If either of those stages produced a false-positive merge, the LLM sees contaminated profiles with bloated alias lists and trait sets. The LLM then makes FURTHER merge decisions based on those inflated profiles. A profile that now lists both "Elizabeth" and "Mrs. Bennet" as aliases looks like it should merge with any profile mentioning either name.

The co-occurrence guard (`_named_pair_cooccurs`) only blocks merges where BOTH profiles have `is_named=True` and appear in the same chapter. It does not catch contamination from earlier stages because the contaminated profile already absorbed the other character's identity.

**Why it happens:**
The 4-stage merge pipeline is sequential with no backtracking. Each stage trusts the output of the previous stage. There is no global validation that detects cross-contamination across stages.

**How to avoid:**
1. **Run cross-name exclusion BEFORE the LLM consolidation stage**: After stages 1-3, verify that no profile's alias set contains canonical names of other profiles. Remove such aliases before passing profiles to the LLM.
2. **Add merge diagnostics (merge_audit.json)**: After each stage, log the full state of all profiles including what was merged and why. This makes it possible to trace contamination back to its source.
3. **Cap aliases per profile**: No profile should have more than 10 aliases after merging. If it has more, it likely absorbed another character's identity. Flag for review.
4. **Apply co-occurrence guard to ALL merge stages, not just LLM consolidation**: The fuzzy and substring stages currently do not check co-occurrence. If "Elizabeth" and "Mrs. Bennet" both appear in chapter 3, they should not be merged in ANY stage.

**Warning signs:**
- LLM consolidation proposing to merge profiles that already have 10+ aliases
- merge_audit.json (when implemented) showing a merge chain longer than 3 steps
- The LLM reasoning field mentioning aliases that came from a prior incorrect merge

**Phase to address:**
Phase 1 (merger hardening). Co-occurrence guard must be extended to all stages, not just the LLM stage.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Add cross-name exclusion only to substring stage, not fuzzy | Faster implementation, fewer code changes | Fuzzy stage can still produce false positives that cascade | Never -- apply to ALL merge stages or the guard is incomplete |
| Hardcode trait count cap at 30 without configurability | Quick fix for the immediate problem | Different books have different optimal caps; literary fiction with complex characters may need 40+ | Acceptable for v1.3 with a TODO to make configurable |
| Implement distinctiveness pass as a simple trait-swap without LLM | No LLM call overhead, deterministic results | Rule-based swaps cannot reason about character coherence; produces absurd combinations | Never for production -- use LLM with character context |
| Store merge_audit.json only in debug mode | No disk overhead in normal runs | Merge issues in production runs are undiagnosable without the audit trail | Acceptable for v1.3 if the audit is opt-in via `--merge-audit` flag, but strongly recommend making it default since the file is small |
| Skip expressive clip scoring for speakers with only 1 clip cached | Avoids scoring edge cases when there is no alternative | Misses the opportunity to flag that the sole available clip is a poor match for the character | Acceptable -- log a warning when only 1 clip is available so the user knows selection was constrained |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Cross-name exclusion + alias_overlap() | Building the exclusion set once and not updating it after merges | Rebuild the protected name set before EACH merge stage. After stage 1 merges "Mr. Darcy" with "Darcy", the protected set changes. |
| Opinionated extraction + cache | Using the same cache key prefix for conservative and opinionated extraction | Include the extraction mode in the cache key: `extraction_v2` vs `extraction_v2_opinionated`. Otherwise `--opinionated` returns cached conservative results. |
| Distinctiveness pass + voice matching | Running distinctiveness pass on profiles that have already been matched to speakers | Distinctiveness must run BEFORE voice matching. If you push profiles apart after matching, the matched voice no longer fits. Pipeline order: extract -> merge -> opinionated -> distinctiveness -> match -> synthesize. |
| voice_overrides.yaml + trait matcher cache | Applying overrides before matching but the trait matcher cache key does not include override data | Include override hash in the trait matcher cache key, or invalidate the cache when overrides change. Otherwise matching uses stale cached results that ignore overrides. |
| Expressive clip scoring + audio_downloader | Scoring clips that have not been downloaded yet | Clip scoring runs AFTER download_voice_clips(). The scorer needs actual WAV files on disk to compute pitch/energy/rate. Ensure the download step is called first. |
| Co-occurrence guard + unnamed characters | Applying co-occurrence guard to unnamed characters ("the servant") that appear in many chapters | Co-occurrence guard already skips unnamed characters (line 429: `if not profile_a.is_named or not profile_b.is_named: return False`). Do NOT change this -- unnamed characters legitimately appear across chapters and should still be mergeable. |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Computing pitch/energy/rate variance for every WAV in a speaker's directory | Clip selection takes 10+ seconds per speaker when speakers have 50+ clips | Compute features once and cache in a sidecar JSON file per speaker directory. On subsequent runs, load cached features. | Immediate for speakers with many clips (some LibriTTS speakers have 100+ utterances) |
| O(n^2) pairwise comparison in distinctiveness pass | Distinctiveness pass takes minutes for books with 40+ characters | Use the distinctiveness pass only on character PAIRS that are already similar (cosine similarity of profiles above threshold). Skip pairs that are already distinct. | Books with 40+ speaking characters (epic fantasy, ensemble novels) |
| Rebuilding co-occurrence map in every merge stage | Redundant computation of chapter->character mappings | Build co-occurrence map ONCE from the original chapter_characters input, pass it as a parameter to each stage. The map does not change -- only the profiles change. | Not severe but wastes time on books with 60+ chapters |
| Expressive clip scoring loading full WAV audio into memory | Memory spikes when scoring clips for 20+ speakers simultaneously | Process one speaker at a time, release WAV data after computing features. Do not hold all speaker audio in memory simultaneously. | M4 Mac with 16GB -- WAV files for 20 speakers at 12.5s each = ~24MB (manageable, but be defensive) |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No merge audit output by default | User cannot understand why characters were incorrectly merged without adding debug flags and re-running | Always write merge_audit.json. It is small (<100KB) and critical for diagnosing merge issues. Make it opt-OUT not opt-IN. |
| Opinionated mode changes existing cached profiles silently | User runs with `--opinionated`, gets new profiles, then runs without it and gets old cached profiles -- confusing inconsistency | Clear extraction cache when switching between opinionated and conservative modes, or use separate cache directories per mode |
| No diff output when overrides are applied | User writes voice_overrides.yaml but cannot see what changed vs. the extracted profile | Print a before/after diff for each override: "Mr. Darcy: pitch medium->low, tone warm->cold" |
| Expressive clip selection picks different clips than previous runs | Re-running the pipeline selects different reference clips, making voice consistency verification fail (Resemblyzer detects "drift" that is actually a different reference clip) | Pin clip selection results in voice_map.json. Only re-select clips if explicitly requested via `--reselect-clips` flag or if voice_map.json does not exist. |

## "Looks Done But Isn't" Checklist

- [ ] **Cross-name exclusion:** Test with Pride and Prejudice cast -- "Bennet" should not merge Mrs. Bennet, Mr. Bennet, Elizabeth Bennet, Jane Bennet, Lydia Bennet, Mary Bennet, or Kitty Bennet into one profile
- [ ] **Co-occurrence guard on all stages:** Verify that fuzzy merge and substring merge check co-occurrence, not just LLM consolidation
- [ ] **Trait count cap:** After merging a 61-chapter novel, no profile has more than 30 personality_traits
- [ ] **Opinionated cache isolation:** Run conservative extraction, then opinionated extraction on the same book -- profiles should differ. Run conservative again -- should get the original cached results, not the opinionated ones.
- [ ] **Distinctiveness coherence:** After distinctiveness pass, each profile's voice_profile.description still matches its individual trait fields (pitch, pace, tone)
- [ ] **voice_overrides.yaml validation:** A YAML file with invalid field names (`loudness: "high"`) produces a clear error, not a silent pass-through
- [ ] **Expressive clip scoring with character context:** A character with `pace: "slow"` gets a different clip than a character with `pace: "fast"` from the same speaker (if multiple clips exist)
- [ ] **Merge diagnostics:** merge_audit.json records every merge decision with before/after profile snapshots and the merge stage that triggered it

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Cascading merge contamination | MEDIUM | Delete characters.json, clear extraction cache, re-run attribution phase. Merges happen during attribution, so re-extraction + re-merge from clean state fixes it. |
| Substring false positives | LOW | Fix MIN_SUBSTRING_LENGTH and add word-boundary check. Re-run merge only (extraction cache can be reused). Delete characters.json and re-run attribution. |
| Generic opinionated profiles | LOW | Iterate on the opinionated extraction prompt. Clear the opinionated cache entries. Re-run extraction. No downstream impact until matching/synthesis run. |
| Contradictory distinctiveness results | LOW | Revert profiles to pre-distinctiveness state (the pass should save a backup). Adjust distinctiveness constraints and re-run the pass only. |
| Expressive clips mismatched to characters | LOW | Delete voice_map.json clip_path entries, re-run clip selection with corrected scoring. Re-run synthesis for affected characters. |
| voice_overrides.yaml silently ignored | LOW | Add logging, verify pipeline application order. No data loss -- overrides are additive. Fix the load order and re-run matching + synthesis. |
| LLM consolidation on contaminated profiles | MEDIUM | Must fix upstream stages first (fuzzy, substring), then clear consolidation cache, then re-run full merge pipeline. Cannot fix consolidation in isolation. |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Cascading merge contamination | Phase 1 (Merger Hardening) | merge_audit.json shows no profile with >30 traits or aliases containing other profiles' canonical names |
| Substring false positives | Phase 1 (Merger Hardening) | Pride and Prejudice test: all 5 Bennet sisters remain separate profiles after full merge pipeline |
| Generic opinionated profiles | Phase 2 (Opinionated Profiles) | Run `--opinionated` on test book: <10% of voice_profile fields remain "unknown" (vs. ~60% in conservative mode) |
| Contradictory distinctiveness | Phase 2 (Opinionated Profiles) | Manual review of 5 character profiles after distinctiveness pass -- all traits coherent with description |
| Expressive clip mismatch | Phase 3 (Expressive Clips) | Character with `pace: "slow"` assigned clip with lower speaking rate than character with `pace: "fast"` |
| voice_overrides.yaml ignored | Phase 2 (Opinionated Profiles) | Apply override `pitch: "low"` to character with `pitch: "high"` -- voice_map.json reflects changed matching |
| LLM consolidation contamination | Phase 1 (Merger Hardening) | Co-occurrence guard logs show blocks in fuzzy and substring stages, not just LLM stage |
| Cache pollution across modes | Phase 2 (Opinionated Profiles) | Toggle between `--opinionated` and default three times -- each run produces consistent, mode-appropriate results |

## Sources

- Actual codebase: `src/attribution/merger.py` -- full merge pipeline with 4 stages, `_merge_two_profiles()` blind union on lines 250-315, `_names_match_substring()` on lines 33-57, `_build_cooccurrence()` on lines 386-412
- Actual codebase: `src/attribution/extractor.py` -- `EXTRACTION_SYSTEM_PROMPT` on lines 43-87, cache key generation on line 259
- Actual codebase: `src/matching/clip_selector.py` -- duration-only scoring on lines 72-73, no character-profile awareness
- Actual codebase: `src/matching/trait_matcher.py` -- `_build_character_description()` on lines 102-142, cache key including available candidates on lines 193-199
- Actual codebase: `src/attribution/models.py` -- VoiceProfile schema (9 string fields), CharacterProfile schema with personality_traits as unbounded list
- PROJECT.md known root cause: "_merge_two_profiles() in merger.py blindly unions ALL aliases and ALL personality traits"

---
*Pitfalls research for: v1.3 Voice Quality milestone*
*Researched: 2026-03-09*
