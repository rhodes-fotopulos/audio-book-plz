# Phase 10: Verification & CLI Wiring Fixes - Research

**Researched:** 2026-03-04
**Domain:** CLI wiring fixes, verification documentation, frontmatter updates, docstring maintenance
**Confidence:** HIGH

## Summary

Phase 10 is a gap closure phase that addresses all audit findings from the v1.1 milestone audit (`.planning/v1.1-MILESTONE-AUDIT.md`). There are six distinct work items: two CLI wiring bugs, two VERIFICATION.md files, Phase 9 SUMMARY frontmatter updates, and one stale docstring. None of these require new libraries, architectural changes, or external research. The entire phase operates on existing code and documentation that has already been verified by the audit as functionally implemented -- the gaps are in CLI plumbing and verification documentation.

The two CLI bugs are precisely scoped. Bug 1: the `assemble` command in `main.py` accepts `--voice-threshold` but never calls `run_voice_check()` -- the parameter is silently discarded. Bug 2: the `synthesize` command lacks a `--libritts-audio` flag, so standalone synthesis cannot pass LibriTTS-R audio paths to `voice_prep.py` for transcript/SNR preparation. Both bugs work correctly through the `convert` command, which calls the full pipeline.

The verification documents (Phase 8 VERIFICATION.md and Phase 9 VERIFICATION.md) follow the established format from Phase 7's `07-VERIFICATION.md`: YAML frontmatter with phase/status/verified fields, a requirement coverage table with evidence, must-have truth checklists from plan frontmatter, artifact verification tables, and key link verification.

**Primary recommendation:** Fix the two CLI bugs first (code changes), then write VERIFICATION.md files (documentation confirming existing implementations), update Phase 9 SUMMARY frontmatter, and fix the stale docstring. No new dependencies, no architectural changes.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| LLM-01 | Attribution uses qwen3:14b Q4_K_M with KV cache quantization, falling back to 8B Q8_0 if 14B exceeds 16GB memory budget | **Verification only.** Already implemented in `src/attribution/llm_client.py` (`select_model()` with psutil RAM check, 12GB threshold). Confirmed by 08-01-SUMMARY.md. Phase 10 writes VERIFICATION.md evidence. |
| LLM-02 | Dialogue detection uses hybrid regex + LLM to tag lines as spoken/thought/shouted/whispered | **Verification only.** Already implemented in `src/attribution/speech_acts.py` (regex patterns + LLM refinement). Confirmed by 08-02-SUMMARY.md. Phase 10 writes VERIFICATION.md evidence. |
| LLM-03 | Ollama model loads once at pipeline start and stays resident across all LLM phases, with explicit unload before TTS | **Verification only.** Already implemented via `preload_model(keep_alive=-1)` and `unload_model(keep_alive=0)` in `src/attribution/llm_client.py`, called from `src/pipeline.py`. Confirmed by 08-01-SUMMARY.md. |
| EMO-01 | Character extraction generates a voice_baseline field describing each character's default speaking style | **Verification only.** Already implemented: `VoiceBaseline` model in `src/attribution/models.py`, extracted in `src/attribution/extractor.py`. Confirmed by 08-02-SUMMARY.md. |
| EMO-02 | Scene mood analysis produces one mood + intensity per scene via LLM pass | **Verification only.** Already implemented in `src/attribution/emotion/scene_mood.py`, called from `src/pipeline.py` `run_attribute()`. Confirmed by 08-03-SUMMARY.md. |
| EMO-03 | Line-level emotion overrides flag only lines where speaker emotion sharply breaks from scene mood | **Verification only.** Already implemented in `src/attribution/emotion/overrides.py`, called from `src/pipeline.py`. Confirmed by 08-03-SUMMARY.md. |
| EMO-04 | Emotion data flows to synthesis as post-processing parameters (volume/speed adjustments for speech-act tags), not as TTS instruct prompts | **Verification only.** Already implemented in `src/synthesis/post_processor.py` (`SPEECH_ACT_PARAMS` dict), integrated in all 4 synthesis paths in `src/synthesis/synthesizer.py`. Confirmed by 08-03-SUMMARY.md. |
| POL-01 | Pause timing uses Gaussian-randomized durations within context-aware ranges | **Verification only.** Already implemented: `PauseConfig` in `src/assembly/models.py`, `gaussian_pause_ms()` in `src/assembly/concatenator.py`. Confirmed by 09-01-SUMMARY.md. |
| POL-02 | Post-processing applies pedalboard effects chain incrementally | **Verification only.** Already implemented: `create_mastering_chain()` and `apply_effects_chain()` in `src/assembly/effects.py`, applied per chapter in `src/assembly/assembler.py`. Confirmed by 09-01-SUMMARY.md. |
| POL-03 | Final export is 44.1kHz 192kbps CBR MP3 (ACX spec) | **Verification only.** Already implemented: `export_chapter_mp3()` in `src/assembly/encoder.py` with bitrate="192k" and sample_rate=44100. Confirmed by 09-03-SUMMARY.md. |
| POL-04 | Voice consistency pass compares same-speaker segment embeddings and regenerates outliers | **CLI fix + verification.** Implementation exists in `src/synthesis/voice_verifier.py` and is wired through `convert` command. **BUG:** `assemble` command accepts `--voice-threshold` but never calls `run_voice_check()` -- dead flag. Fix required in `main.py`. |
| POL-05 | Segments use 5-10ms fade-in/fade-out crossfades | **Verification only.** Already implemented: `_apply_crossfade()` in `src/assembly/concatenator.py` with `PauseConfig.crossfade_ms=8`. Confirmed by 09-01-SUMMARY.md. |
</phase_requirements>

## Standard Stack

### Core

No new libraries needed. Phase 10 modifies only existing code and creates documentation files.

| Library | Version | Purpose | Already Present |
|---------|---------|---------|-----------------|
| typer | (existing) | CLI framework -- adding flag to synthesize, wiring assemble | Yes |
| rich | (existing) | Console output for voice check summary in assemble | Yes |

### Supporting

None. All work uses existing project infrastructure.

### Alternatives Considered

Not applicable -- this is a fix/verification phase, not a feature phase.

**Installation:**
No new dependencies required.

## Architecture Patterns

### Recommended Changes Structure

```
Files to MODIFY:
  main.py                           # Fix 2 CLI bugs
  src/pipeline.py                   # Fix stale docstring (line 7)

Files to CREATE:
  .planning/phases/08-*/08-VERIFICATION.md  # Phase 8 verification
  .planning/phases/09-*/09-VERIFICATION.md  # Phase 9 verification

Files to UPDATE (frontmatter only):
  .planning/phases/09-*/09-01-SUMMARY.md    # Add requirements-completed
  .planning/phases/09-*/09-02-SUMMARY.md    # Add requirements-completed
  .planning/phases/09-*/09-03-SUMMARY.md    # Add requirements-completed
```

### Pattern 1: Wire Voice Check into Assemble Command

**What:** The `assemble` command in `main.py` accepts `--voice-threshold` but never passes it to `run_voice_check()`. The voice check needs to run before assembly.
**Where:** `main.py` lines 281-342 (the `assemble` function)

**Current state (broken):**
```python
# main.py: assemble command
# voice_threshold is accepted as a parameter but NEVER USED
def assemble(
    ...
    voice_threshold: float = typer.Option(0.60, ...),
    ...
) -> None:
    run_assemble(
        book_dir, epub_path=epub, title=title, author=author, cover=cover,
        cpu=cpu, output_dir=mp3_dir,
    )
    # voice_threshold is silently discarded!
```

**Fix pattern:**
```python
def assemble(
    ...
    voice_threshold: float = typer.Option(0.60, ...),
    ...
) -> None:
    # Run voice consistency check BEFORE assembly
    rprint("\n[bold green]Voice Consistency Check[/bold green]")
    run_voice_check(book_dir, voice_threshold=voice_threshold)

    run_assemble(
        book_dir, epub_path=epub, title=title, author=author, cover=cover,
        cpu=cpu, output_dir=mp3_dir,
    )
```

**Evidence:** This mirrors the `run_full_pipeline()` pattern in `pipeline.py` (lines 782-788) which calls `run_voice_check()` between synthesis and assembly.

### Pattern 2: Add --libritts-audio Flag to Synthesize Command

**What:** The `synthesize` command lacks `--libritts-audio`, so standalone synthesis cannot pass LibriTTS-R audio directory for transcript/SNR voice reference preparation.
**Where:** `main.py` lines 224-278 (the `synthesize` function)

**Current state (missing flag):**
```python
# main.py: synthesize command
def synthesize(
    ...
    # No libritts_audio parameter!
    ...
) -> None:
    run_synthesize(
        book_dir, chapter=chapter, dry_run=dry_run, verbose=verbose,
        cpu=cpu, engine_type=engine,
        # libritts_audio_dir not passed!
    )
```

**Fix pattern:**
```python
def synthesize(
    ...
    libritts_audio: Path = typer.Option(
        None,
        help="Path to LibriTTS-R audio directory (optional). "
        "Default: LIBRITTS_R_AUDIO env var",
        envvar="LIBRITTS_R_AUDIO",
    ),
    ...
) -> None:
    run_synthesize(
        book_dir, chapter=chapter, dry_run=dry_run, verbose=verbose,
        cpu=cpu, engine_type=engine,
        libritts_audio_dir=libritts_audio,
    )
```

**Evidence:** The `convert` command already has this flag (main.py lines 65-70). The `run_synthesize()` function in `pipeline.py` already accepts `libritts_audio_dir` as a parameter (line 413) and passes it to `run_synthesis()` as `libritts_root` (line 526).

### Pattern 3: VERIFICATION.md Format

**What:** Phase 8 and Phase 9 need VERIFICATION.md files following the Phase 7 template.
**Template source:** `.planning/phases/07-tts-engine-swap/07-VERIFICATION.md`

**Structure:**
```markdown
---
phase: {phase-name}
status: passed
verified: 2026-03-04
---

# Phase N Verification: {Phase Name}

## Requirement Coverage
| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| REQ-ID | description | PASS | code evidence |

## Must-Have Truths (from Plan Frontmatter)
### Plan NN-01
- [x] Truth statement from plan frontmatter

## Artifact Verification
| Artifact | Expected | Actual |
|----------|----------|--------|
| file path | what it should contain | what it does contain |

## Key Link Verification
| From | To | Via | Verified |
|------|----|-----|----------|
| source | target | connection | Yes/No |

## Test Results
- N tests passing
- Zero regressions

## Human Verification Items
[Items requiring manual testing]

## Gaps
[None found / any remaining gaps]
```

### Pattern 4: SUMMARY Frontmatter for Requirements

**What:** Phase 9 SUMMARY.md files need `requirements-completed` frontmatter like Phase 8 has.
**Template source:** Phase 8 SUMMARY frontmatter (e.g., `08-01-SUMMARY.md` has `requirements-completed: [LLM-01, LLM-03]`)

**Current Phase 9 SUMMARY frontmatter (missing field):**
```yaml
---
phase: 09-production-polish
plan: 01
status: complete
---
```

**Fix:**
```yaml
---
phase: 09-production-polish
plan: 01
status: complete
requirements-completed: [POL-01, POL-02, POL-05]
---
```

**Mapping (from SUMMARY content and PLAN file analysis):**
- 09-01-SUMMARY: POL-01, POL-02, POL-05 (Gaussian pauses, effects chain, crossfades)
- 09-02-SUMMARY: POL-04 (voice consistency verification)
- 09-03-SUMMARY: POL-03, POL-04 (ACX export, voice consistency CLI wiring)

### Anti-Patterns to Avoid

- **Adding voice check to run_assemble() function instead of main.py:** The voice check is a separate pipeline phase (Phase 4.5), not part of assembly. It should be called before `run_assemble()` in the CLI layer, matching how `run_full_pipeline()` calls it separately.
- **Removing --voice-threshold from assemble command:** The flag is intentional per the Phase 9 design (09-03-SUMMARY.md documents it). Fix the wiring, don't remove the flag.
- **Creating VERIFICATION.md with only surface-level checks:** The Phase 7 VERIFICATION.md includes specific code evidence (function names, parameter values, file locations). Phase 8 and 9 verifications need the same depth.
- **Writing verification documents without checking actual code:** Every claim in VERIFICATION.md must be traceable to a specific file and function. The audit already confirmed the implementations exist, but the verification document must cite the evidence explicitly.

## Don't Hand-Roll

Not applicable. Phase 10 does not build any new functionality. All work is fixing existing wiring and creating documentation.

## Common Pitfalls

### Pitfall 1: Voice Check Blocking Assembly on Missing Prerequisites

**What goes wrong:** `run_voice_check()` raises `typer.Exit(code=1)` if voice_map.json or attributed.json is missing, but the `assemble` command may not have these in a location the voice check expects.
**Why it happens:** The `assemble` command receives `book_dir` which already must have these files (assembly itself needs them). But it is worth being aware that `run_voice_check()` does its own validation.
**How to avoid:** `run_voice_check()` already validates prerequisites and exits cleanly. The assemble command already validates `book_dir` exists. Just call `run_voice_check()` before `run_assemble()` -- both use the same `book_dir`.
**Warning signs:** `run_voice_check` erroring when `assemble` would have succeeded.

### Pitfall 2: Incorrect Requirement Mapping in Phase 9 SUMMARYs

**What goes wrong:** Assigning wrong requirement IDs to the wrong plan's frontmatter.
**Why it happens:** POL-04 (voice consistency) spans two plans (09-02 built the verifier, 09-03 wired the CLI). The audit notes both plans contributed.
**How to avoid:** Read each SUMMARY content section carefully and cross-reference with the audit's `completed_by_plans` entries. POL-04 should appear in both 09-02 and 09-03 frontmatter since both contributed work.
**Warning signs:** A requirement appearing in one SUMMARY but the code changes are documented in a different SUMMARY.

### Pitfall 3: Stale Docstring Partial Fix

**What goes wrong:** Fixing only the explicit "Chatterbox TTS" reference on line 7 of pipeline.py but missing other potential stale references in the same docstring.
**Why it happens:** The docstring was written during the original pipeline design and has been incrementally updated but not fully reconciled with v1.1 changes.
**How to avoid:** Read the full module docstring (lines 1-9) and verify all phase descriptions match current implementation. Phase 4 now uses "Qwen3-TTS (MLX)" not "Chatterbox TTS". Also confirm Phase 4.5 (voice consistency) and the emotion annotation step are reflected.
**Warning signs:** The docstring mentioning only 5 phases when the pipeline now has 6 phases (including voice consistency).

### Pitfall 4: VERIFICATION.md Claiming Incorrect Evidence

**What goes wrong:** Stating a function or behavior exists when the actual implementation differs from what was planned.
**Why it happens:** The SUMMARY describes what was built, but implementation details sometimes differ from the original PLAN. Copy-pasting plan descriptions into verification evidence without checking.
**How to avoid:** Every verification claim should cite the actual source file and function, verified against the codebase. Use the audit's integration checker findings as a starting point, then confirm each claim.
**Warning signs:** Evidence column references functions that don't exist or have different signatures than described.

## Code Examples

### CLI Bug Fix 1: Wire voice_threshold in assemble

```python
# In main.py, assemble command body (around line 339)
# BEFORE run_assemble():
rprint("\n[bold green]Voice Consistency Check[/bold green]")
run_voice_check(book_dir, voice_threshold=voice_threshold)
```

Source: Pattern matches `run_full_pipeline()` in pipeline.py lines 782-788.

### CLI Bug Fix 2: Add --libritts-audio to synthesize

```python
# In main.py, synthesize command definition
libritts_audio: Path = typer.Option(
    None,
    help="Path to LibriTTS-R audio directory (optional). "
    "Default: LIBRITTS_R_AUDIO env var",
    envvar="LIBRITTS_R_AUDIO",
),

# In run_synthesize call:
run_synthesize(
    book_dir, chapter=chapter, dry_run=dry_run, verbose=verbose,
    cpu=cpu, engine_type=engine,
    libritts_audio_dir=libritts_audio,
)
```

Source: Pattern matches `convert` command in main.py lines 65-70.

### Stale Docstring Fix

```python
# pipeline.py lines 1-9 currently:
"""Pipeline orchestrator for audio-book-plz.

Coordinates the multi-phase conversion pipeline:
  Phase 1 - Parse:      EPUB -> segments.json
  Phase 2 - Attribute:  segments.json -> characters.json + attributed.json
  Phase 3 - Match:      attributed segments -> voice_map.json
  Phase 4 - Synthesize: segments -> WAV audio files via Chatterbox TTS
  Phase 5 - Assemble:   WAV segments -> chapter MP3s + audiobook.mp3
"""

# Should become:
"""Pipeline orchestrator for audio-book-plz.

Coordinates the multi-phase conversion pipeline:
  Phase 1 - Parse:      EPUB -> segments.json
  Phase 2 - Attribute:  segments.json -> characters.json + attributed.json + emotion.json
  Phase 3 - Match:      attributed segments -> voice_map.json
  Phase 4 - Synthesize: segments -> WAV audio files via Qwen3-TTS (MLX)
  Phase 4.5 - Verify:   voice consistency check on synthesized segments
  Phase 5 - Assemble:   WAV segments -> chapter MP3s + audiobook.mp3
"""
```

### Phase 9 SUMMARY Frontmatter Additions

```yaml
# 09-01-SUMMARY.md: add after "status: complete"
requirements-completed: [POL-01, POL-02, POL-05]

# 09-02-SUMMARY.md: add after "status: complete"
requirements-completed: [POL-04]

# 09-03-SUMMARY.md: add after "status: complete"
requirements-completed: [POL-03, POL-04]
```

## State of the Art

Not applicable. Phase 10 is a maintenance/verification phase, not a technology adoption phase.

## Open Questions

1. **Should `assemble --voice-threshold` also support `--engine` and `--libritts-audio` for regeneration mode?**
   - What we know: The current `run_voice_check()` in pipeline.py runs in verification-only mode (no `engine_config` passed). The full pipeline also runs it in verification-only mode. Regeneration is deferred to manual re-runs of `synthesize`.
   - What's unclear: Whether the audit intends regeneration support on the assemble command or just the verification check.
   - Recommendation: Match the existing full pipeline behavior: verification-only (no regeneration). The audit's success criterion says "actually runs voice consistency check" not "runs with regeneration." Keep it simple.

2. **Should REQUIREMENTS.md checkboxes be updated from [ ] to [x] for verified requirements?**
   - What we know: The audit noted all implementations exist but checkboxes remain unchecked. Phase 10 creates VERIFICATION.md files that formally verify each requirement.
   - What's unclear: Whether updating the checkboxes is in scope for Phase 10 or should be done as a separate step after all verification is complete.
   - Recommendation: Include updating REQUIREMENTS.md checkboxes as part of Phase 10. Once VERIFICATION.md exists, the checkboxes should reflect verified status. This closes the loop.

## Sources

### Primary (HIGH confidence)
- **Codebase inspection:** `main.py` -- full CLI definition with all commands, flags, and wiring
- **Codebase inspection:** `src/pipeline.py` -- all `run_*` functions including `run_voice_check()`
- **Codebase inspection:** `src/synthesis/voice_verifier.py` -- voice consistency implementation
- **Codebase inspection:** `src/synthesis/synthesizer.py` -- synthesis loop with libritts_root parameter
- **Codebase inspection:** `src/synthesis/voice_prep.py` -- voice reference preparation with transcripts
- **Audit document:** `.planning/v1.1-MILESTONE-AUDIT.md` -- all gaps enumerated with evidence
- **Phase 7 VERIFICATION.md:** `.planning/phases/07-tts-engine-swap/07-VERIFICATION.md` -- template format
- **Phase 8 SUMMARYs:** `08-01-SUMMARY.md`, `08-02-SUMMARY.md`, `08-03-SUMMARY.md` -- frontmatter with requirements-completed pattern
- **Phase 9 SUMMARYs:** `09-01-SUMMARY.md`, `09-02-SUMMARY.md`, `09-03-SUMMARY.md` -- content confirms implementations, frontmatter missing requirements-completed

### Secondary (MEDIUM confidence)
- None needed -- all findings are from direct codebase inspection.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- CLI bug fixes: HIGH -- exact locations identified, fix patterns confirmed against existing working code
- VERIFICATION.md creation: HIGH -- template established, evidence already enumerated in audit document
- SUMMARY frontmatter updates: HIGH -- exact fields and values determined from Phase 8 precedent and SUMMARY content
- Docstring fix: HIGH -- single line change with clear before/after

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- no external dependencies or moving targets)
