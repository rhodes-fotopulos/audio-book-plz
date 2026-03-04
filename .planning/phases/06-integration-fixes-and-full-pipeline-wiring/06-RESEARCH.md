# Phase 6: Integration Fixes and Full Pipeline Wiring - Research

**Researched:** 2026-03-04
**Domain:** Python pipeline integration, Pydantic model validation, file path conventions, CLI wiring
**Confidence:** HIGH

## Summary

Phase 6 is a gap-closure phase that fixes 4 integration bugs preventing the full pipeline from running end-to-end. The bugs are well-localized -- each has a specific root cause, a known file and line number, and a clear fix. No new libraries, architecture changes, or complex design decisions are needed.

The four blocking issues are: (1) WAV file path convention mismatch between the Phase 4 synthesizer (writes `wavs/ch{NN}/seg_{NNNN}.wav`) and the Phase 5 assembler (expects `wavs/segment_{NNNNNN}.wav`), causing the assembler to find zero files; (2) `run_full_pipeline()` in `pipeline.py` only runs Phases 1-2, with Phases 3-5 as stub messages; (3) the Phase 5 announcer crashes with `FileNotFoundError` when the narrator's `clip_path` is a placeholder string from matching without LibriTTS-R audio; and (4) `CharacterProfile(**c)` and `VoiceMap(**data)` use the constructor instead of `model_validate()`, which is Pydantic v2 best practice (though testing confirms both work in Pydantic 2.12.5 installed in this project). Additionally, `epub_path` needs to be threaded through `run_full_pipeline` so Phase 5 can extract metadata for ID3 tags.

**Primary recommendation:** Fix the WAV path convention first (highest impact), then wire `run_full_pipeline` to call all 5 phases, then fix the announcer placeholder crash, then apply the `model_validate()` cleanups and `epub_path` threading. Every fix is a targeted code edit to existing files -- no new modules needed.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CLI-01 | User can run the full pipeline end-to-end with a single command | Fix `run_full_pipeline()` to call phases 3-5 instead of printing stubs; add `--libritts-data` / `--libritts-audio` options to `convert` command |
| AUDIO-01 | User gets a single full-audiobook MP3 file as final output | Fix WAV path convention so assembler discovers synthesized WAV files; fix announcer placeholder crash |
| AUDIO-02 | Appropriate silence is inserted between segments | Code exists in `concatenator.py` and works correctly -- just needs WAV path fix so it can find files |
| AUDIO-03 | Audio is normalized for consistent volume across different voices | Code exists in `normalizer.py` and works correctly -- just needs WAV path fix so chapters have content |
| AUDIO-04 | MP3 files include ID3 metadata (title, author, chapter names) | Thread `epub_path` through `run_full_pipeline` to Phase 5; fix announcer so it doesn't crash before tagger runs |
| VOICE-01 | User can match characters to real human voices from LibriTTS-P | Fix `CharacterProfile(**c)` to `model_validate(c)` in orchestrator.py:74 (best practice; currently works on 2.12.5) |
| VOICE-02 | LLM compares character voice traits to LibriTTS-P speaker annotations | Same fix as VOICE-01 -- matching code works once character loading succeeds |
| VOICE-03 | Embedding similarity serves as fallback for large casts | Same fix as VOICE-01 -- embedding fallback code works once character loading succeeds |
| VOICE-04 | No two major characters are assigned the same voice reference | Same fix as VOICE-01 -- dedup enforcement code works once character loading succeeds |
| VOICE-05 | Voice assignments are saved to voice_map.json and cached for re-runs | Fix `VoiceMap(**data)` to `VoiceMap.model_validate(data)` on cache-hit path in orchestrator.py:64 (best practice) |
</phase_requirements>

## Standard Stack

### Core (already installed -- no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | 2.12.5 | Data models with validation | Already used throughout Phases 2-4 |
| typer | installed | CLI framework | Already powers main.py |
| rich | installed | Terminal output | Already used for progress/tables |
| pydub | installed | Audio concatenation | Already used in Phase 5 assembler |
| mutagen | installed | ID3 metadata tagging | Already used in Phase 5 tagger |
| ebooklib | installed | EPUB metadata extraction | Already used in Phase 5 metadata |

### No New Dependencies Needed

This phase modifies only existing code. No new libraries, no package installs.

## Architecture Patterns

### Existing Project Structure (no changes needed)
```
src/
  pipeline.py          # Full pipeline orchestration (FIX: wire phases 3-5)
  matching/
    orchestrator.py    # Voice matching pipeline (FIX: model_validate)
  synthesis/
    synthesizer.py     # TTS synthesis (REFERENCE: WAV path convention source)
  assembly/
    assembler.py       # Assembly orchestrator (FIX: WAV path lookup)
    announcer.py       # Chapter announcements (FIX: placeholder clip_path)
main.py                # CLI entry points (FIX: convert command options)
```

### Pattern: Fix at the Boundary, Not the Interior

Each bug is at a phase boundary -- where one phase's output becomes another's input. The correct approach is to fix the **consumer** to match the **producer's** convention (or vice versa), NOT to refactor both sides. This phase should pick one convention and adjust the other side.

For the WAV path mismatch specifically: the synthesizer's convention (`wavs/ch{NN}/seg_{NNNN}.wav`) is superior because it organizes files by chapter, making per-chapter assembly cleaner and preventing flat directories with thousands of files. The assembler should be updated to match this convention.

### Pattern: Graceful Degradation for Optional Inputs

The announcer crashes when `clip_path` is a placeholder. The synthesizer already demonstrates the correct pattern -- it logs a warning and continues (line 202-207 in `synthesizer.py`). The announcer should follow this same pattern: detect placeholder paths, skip announcement generation, and return an empty dict so chapter assembly proceeds without announcements.

### Anti-Patterns to Avoid
- **Refactoring both producer and consumer simultaneously:** Pick the better convention and change only one side
- **Making announcements a hard requirement:** Chapter assembly must work without announcements (graceful degradation)
- **Adding interactive prompts in full pipeline mode:** The `convert` command is designed for unattended overnight runs -- `run_match` currently has a `typer.confirm()` prompt that must be bypassed or auto-accepted in pipeline mode

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pydantic dict-to-model conversion | Manual dict unpacking | `Model.model_validate(data)` | Handles nested models, type coercion, validation in one call |
| WAV file discovery | Custom glob/walk patterns | Consistent path convention + direct Path construction | Glob patterns are fragile; known path format is deterministic |
| Pipeline phase ordering | Complex dependency resolution | Sequential function calls in `run_full_pipeline` | Pipeline is always linear (1->2->3->4->5); no parallel or conditional execution needed |

## Common Pitfalls

### Pitfall 1: WAV Path Convention -- Three Points of Mismatch

**What goes wrong:** The WAV path mismatch isn't just in the segment lookup (line 187 of `assembler.py`). There are THREE places where the assembler assumes a flat `wavs/segment_{NNNNNN}.wav` convention:

1. **Input validation** (line 74): `any(wavs_dir.glob("*.wav"))` -- checks for `*.wav` files directly in `wavs/`, but synthesizer puts them in `wavs/ch{NN}/` subdirectories
2. **Pipeline.py validation** (line 506): Same glob pattern in `run_assemble()` -- `any(wavs_dir.glob("*.wav"))`
3. **Segment WAV lookup** (line 187): `wavs_dir / f"segment_{seg_id:06d}.wav"` -- wrong name format AND wrong directory

**How to avoid:** Fix ALL THREE locations when aligning the path convention. The validation globs should use `"**/*.wav"` or check for the chapter subdirectory pattern. The segment lookup should use `wavs_dir / f"ch{ch_num:02d}" / f"seg_{seg_id:04d}.wav"`.

**Warning signs:** Tests pass but pipeline still produces empty audiobook -- likely missed one of the three locations.

### Pitfall 2: Interactive Prompt in Pipeline Mode

**What goes wrong:** `run_match()` in `pipeline.py` calls `typer.confirm("Write voice_map.json?")` at line 324. In the full pipeline (`convert` command), this blocks waiting for user input, defeating the "unattended overnight run" design goal.

**How to avoid:** Either (a) add an `auto_confirm` parameter to `run_match()` that defaults to `True` when called from `run_full_pipeline`, or (b) write `voice_map.json` automatically in pipeline mode and only prompt in standalone `match` mode. Option (b) is cleaner -- it matches the principle that `convert` is the unattended command while individual phase commands allow interaction.

**Warning signs:** Pipeline hangs after Phase 3 with no visible error.

### Pitfall 3: Announcer Placeholder Detection Must Match Synthesizer

**What goes wrong:** The synthesizer detects placeholder paths by checking `ref_clip.startswith("AUDIO_DIR/")` (line 202). The announcer must use the SAME detection logic. If they diverge, one will handle the placeholder while the other crashes.

**How to avoid:** Extract the placeholder detection into a shared utility function, or at minimum use the same string prefix check (`"AUDIO_DIR/"`) in both locations.

### Pitfall 4: LibriTTS Data Path Required for Pipeline Mode

**What goes wrong:** The `convert` command currently accepts only `epub_file` and `output_dir`. But Phase 3 (matching) requires `libritts_data_dir` and optionally `libritts_audio_dir`. Without these, the full pipeline cannot run Phase 3.

**How to avoid:** Add `--libritts-data` and `--libritts-audio` options to the `convert` command (matching the same defaults/env vars as the `match` command). Thread these through `run_full_pipeline()` to `run_match()`.

### Pitfall 5: epub_path Threading Requires Function Signature Changes

**What goes wrong:** `run_full_pipeline()` has `epub_path` as a parameter, but doesn't pass it downstream. Phase 5's `run_assemble()` already accepts `epub_path` -- the problem is just the pipeline function not threading it through. But note that `run_assemble()` is called inside `run_full_pipeline` which doesn't exist yet (it's a stub).

**How to avoid:** When wiring Phase 5 into the full pipeline, pass `epub_path` to `run_assemble()`. The `run_assemble` function already accepts it as an optional parameter.

### Pitfall 6: Test Coverage for Integration Paths

**What goes wrong:** Existing tests mock internal functions heavily but don't test the actual file path conventions or cross-phase integration. After fixing these bugs, a test that creates WAV files in the synthesizer's format and verifies the assembler discovers them would prevent regressions.

**How to avoid:** Add at least one integration test that creates files matching the synthesizer's WAV path convention and verifies the assembler's discovery logic finds them.

## Code Examples

### Fix 1: Assembler WAV Path Convention (assembler.py)

**Current (broken):**
```python
# assembler.py line 74 — validation
if not wavs_dir.exists() or not any(wavs_dir.glob("*.wav")):

# assembler.py line 187 — segment lookup
wav_path = wavs_dir / f"segment_{seg_id:06d}.wav"
```

**Fixed:**
```python
# assembler.py line 74 — validation: check chapter subdirectories
if not wavs_dir.exists() or not any(wavs_dir.glob("ch*/*.wav")):

# assembler.py line 184-189 — segment lookup: match synthesizer convention
for seg in segs:
    seg_id = seg.get("id", 0)
    ch_num_seg = seg.get("chapter", 0)
    wav_path = wavs_dir / f"ch{ch_num_seg:02d}" / f"seg_{seg_id:04d}.wav"
    if wav_path.exists():
        segment_wavs.append((seg, wav_path))
```

**Also fix pipeline.py line 506:**
```python
# Current (broken):
if not wavs_dir.exists() or not any(wavs_dir.glob("*.wav")):

# Fixed: match the chapter subdirectory convention
if not wavs_dir.exists() or not any(wavs_dir.glob("ch*/*.wav")):
```

### Fix 2: Wire run_full_pipeline (pipeline.py)

**Current (stubs):**
```python
def run_full_pipeline(epub_path: Path, output_dir: Path) -> None:
    run_parse(epub_path, output_dir)
    book_slug = _make_book_slug(epub_path)
    output_book_dir = output_dir / book_slug
    run_attribute(output_book_dir)
    rprint("[yellow]Phase 3 (match): requires --libritts-data...")
    rprint("[yellow]Phase 4 (synthesize): ...")
    rprint("[yellow]Phase 5 (assemble): ...")
```

**Fixed:**
```python
def run_full_pipeline(
    epub_path: Path,
    output_dir: Path,
    libritts_data_dir: Path,
    libritts_audio_dir: Path | None = None,
    cpu: bool = False,
) -> None:
    # Phase 1
    run_parse(epub_path, output_dir)
    book_slug = _make_book_slug(epub_path)
    output_book_dir = output_dir / book_slug

    # Phase 2
    run_attribute(output_book_dir)

    # Phase 3 — auto-write voice_map.json (no interactive prompt)
    run_match(output_book_dir, libritts_data_dir, libritts_audio_dir,
              auto_confirm=True)

    # Phase 4
    run_synthesize(output_book_dir, cpu=cpu)

    # Phase 5 — thread epub_path for metadata extraction
    run_assemble(output_book_dir, epub_path=epub_path, cpu=cpu)
```

### Fix 3: Announcer Placeholder Graceful Handling (announcer.py)

**Current (crashes):**
```python
if not narrator_ref_path.exists():
    raise FileNotFoundError(...)
```

**Fixed:**
```python
if not narrator_ref_path.exists():
    # Placeholder path from matching without LibriTTS-R audio
    # Skip announcements gracefully — chapters will assemble without them
    logger.warning(
        "Narrator reference clip not found: %s — skipping chapter announcements. "
        "Provide --libritts-audio to enable announcements.",
        narrator_ref_path,
    )
    return {}
```

### Fix 4: model_validate() Cleanup (orchestrator.py)

**Line 74 — character loading:**
```python
# Current:
characters = [CharacterProfile(**c) for c in characters_data]
# Fixed:
characters = [CharacterProfile.model_validate(c) for c in characters_data]
```

**Line 64 — cached voice map loading:**
```python
# Current:
return VoiceMap(**data)
# Fixed:
return VoiceMap.model_validate(data)
```

### Fix 5: Convert Command CLI Options (main.py)

```python
@app.command()
def convert(
    epub_file: Path = typer.Argument(..., exists=True, readable=True, help="Path to EPUB file"),
    output_dir: Path = typer.Option(Path("output"), help="Output directory"),
    libritts_data: Path = typer.Option(
        None,
        help="Path to LibriTTS-P data directory (contains df1_en.csv). "
        "Default: LIBRITTS_P_DATA env var or ~/.local/share/libritts-p/data",
        envvar="LIBRITTS_P_DATA",
    ),
    libritts_audio: Path = typer.Option(
        None,
        help="Path to LibriTTS-R audio directory (optional). "
        "Default: LIBRITTS_R_AUDIO env var",
        envvar="LIBRITTS_R_AUDIO",
    ),
    cpu: bool = typer.Option(False, "--cpu", help="Force CPU mode"),
) -> None:
    """Run full pipeline: parse -> attribute -> match -> synthesize -> assemble."""
    # ... validation ...
    run_full_pipeline(epub_file, output_dir, libritts_data, libritts_audio, cpu=cpu)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Model(**data)` constructor | `Model.model_validate(data)` | Pydantic v2 (2023) | Better nested model handling, clearer API intent |
| Flat WAV directory | Chapter-organized subdirectories | Phase 4 implementation | Prevents 10K+ files in single directory, enables per-chapter operations |

**Note on Pydantic strict mode:**
Testing confirms that in Pydantic 2.12.5 (installed in this project), `Model(**data)` with `ConfigDict(strict=True)` DOES successfully coerce nested dicts to nested model instances. The audit's claim that `CharacterProfile(**c)` fails with a `ValidationError` was not reproducible. However, `model_validate()` remains the recommended fix because: (a) it's the documented Pydantic v2 best practice, (b) it's more explicit about intent, and (c) it may become necessary if Pydantic changes strict mode behavior in future versions.

## Open Questions

1. **Should `run_match` auto-confirm in pipeline mode or skip the confirmation entirely?**
   - What we know: `run_match()` line 324 calls `typer.confirm("Write voice_map.json?")`. The `convert` command is designed for unattended operation.
   - What's unclear: Whether to add an `auto_confirm` parameter or to restructure `run_match` to separate display from persistence.
   - Recommendation: Add an `auto_confirm: bool = False` parameter to `run_match()`. When `True`, skip the confirmation prompt and write automatically. Set `True` in `run_full_pipeline()`.

2. **Should the assembler validate WAV completeness?**
   - What we know: The assembler currently just skips missing WAVs with a warning (line 191). If synthesis was interrupted, many WAVs could be missing.
   - What's unclear: Should the assembler warn when >10% of expected WAVs are missing? Or fail entirely?
   - Recommendation: Keep current behavior (warn and skip per segment). The checkpoint/resume system in Phase 4 is the right place to ensure completeness, not the assembler.

3. **What `libritts-data` default path should the convert command use?**
   - What we know: The `match` command checks `~/.local/share/libritts-p/data` as a default (line 128 of main.py).
   - Recommendation: Use the same default path and env var convention for `convert` (copy the logic from the `match` command).

## Sources

### Primary (HIGH confidence)
- Direct code inspection of all affected files in the repository
- Local Pydantic 2.12.5 behavior testing (strict mode with nested dicts verified)
- v1 Milestone Audit report (`.planning/v1-MILESTONE-AUDIT.md`)

### Secondary (MEDIUM confidence)
- [Pydantic Strict Mode docs](https://docs.pydantic.dev/latest/concepts/strict_mode/) - Confirmed strict mode allows dict-to-model coercion for nested fields

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies; all fixes use existing libraries
- Architecture: HIGH - All changes are targeted edits to known files at known line numbers
- Pitfalls: HIGH - Every pitfall is verified by direct code inspection with exact line references
- Pydantic strict mode behavior: MEDIUM - Tested on 2.12.5 but audit claimed failure; applying fix regardless as best practice

**Research date:** 2026-03-04
**Valid until:** No expiry - this is a bug-fix phase with no external dependency risk
