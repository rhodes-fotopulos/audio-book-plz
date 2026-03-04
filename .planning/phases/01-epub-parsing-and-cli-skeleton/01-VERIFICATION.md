---
phase: 01-epub-parsing-and-cli-skeleton
verified: 2026-03-03T00:00:00Z
status: passed
score: 10/10 must-haves verified
re_verification: false
---

# Phase 1: EPUB Parsing and CLI Skeleton Verification Report

**Phase Goal:** Users can feed any EPUB into the pipeline and get back a validated, speech-ready `segments.json` that all downstream phases can consume, with a working CLI to invoke each phase
**Verified:** 2026-03-03
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

The five success criteria from ROADMAP.md are used as the authoritative truths.

| #  | Truth                                                                                                                  | Status     | Evidence                                                                                                                         |
|----|------------------------------------------------------------------------------------------------------------------------|------------|----------------------------------------------------------------------------------------------------------------------------------|
| 1  | User can run `python main.py parse book.epub` and get a `segments.json` with all chapters in reading order, front matter excluded | VERIFIED | `main.py` wires `parse` command to `run_parse()`; `run_parse()` calls `load_epub` + `get_story_chapters` + iterates chapters; writes to `output/{slug}/segments.json`. 3-tier hybrid front matter detection implemented in `epub_reader.py`. |
| 2  | Every segment is tagged as narration, dialogue, chapter heading, or scene break, and no segment exceeds 280 characters | VERIFIED | `segmenter.py` has `CHAR_LIMIT = 280`; `classify_block()` returns only four `SegmentType` values; `split_to_segments()` enforces limit via NLTK sentence splitting + clause-boundary splitting; 52 tests pass confirming this invariant. |
| 3  | Dialogue is correctly identified for both straight and curly quotation mark variants across representative fiction EPUBs | VERIFIED | `_contains_dialogue_quote()` in `segmenter.py` handles straight `"`, curly double `\u201c`/`\u201d`, and curly single `\u2018`/`\u2019`; apostrophes explicitly excluded; multi-paragraph state machine implemented via `_update_dialogue_state()`; 11 dedicated test cases covering all variants pass. |
| 4  | User can run `python main.py [parse|attribute|match|synthesize|assemble]` to invoke any individual phase from the CLI | VERIFIED | `main.py` declares 6 `@app.command()` functions: `parse`, `convert`, `attribute`, `match`, `synthesize`, `assemble`; stub commands print phase messages and raise `typer.Exit(code=0)`. |
| 5  | User can run `python main.py convert book.epub` to trigger the full end-to-end pipeline with a single command | VERIFIED | `convert` command in `main.py` calls `run_full_pipeline()`; `run_full_pipeline()` calls `run_parse()` then prints stub messages for phases 2-5; no confirmation prompt. |

**Score: 5/5 truths verified**

Additional plan-level truths verified:

| #  | Truth (from Plan frontmatter)                                                                                     | Status     | Evidence                                                                                                    |
|----|-------------------------------------------------------------------------------------------------------------------|------------|-------------------------------------------------------------------------------------------------------------|
| 6  | EPUB2 and EPUB3 files can be loaded and chapters extracted in spine (reading) order                               | VERIFIED   | `epub_reader.py` iterates `book.spine` with `get_item_with_id()`; never uses `get_items_of_type` (confirmed absent). |
| 7  | HTML tags are stripped and clean, speech-ready text blocks are produced per chapter                               | VERIFIED   | `html_cleaner.py` uses `BeautifulSoup(content, "lxml")` on `item.get_body_content()`, iterates block tags, calls `tag.get_text(separator=" ", strip=True)`. |
| 8  | Front matter (title pages, copyright, ToC, dedications) is excluded from chapter list                            | VERIFIED   | `_find_story_start()` implements 3 tiers: guide check, heading scan (`h1`/`h2` containing chapter/part/prologue/number), include-all fallback. |
| 9  | Back matter (acknowledgments, author bios, reading guides) is excluded; epilogues and afterwords are included     | VERIFIED   | `_find_story_end()` scans backwards with `_BACK_MATTER_EXCLUDE` regex, stops at unrecognised chapters or `_BACK_MATTER_INCLUDE` matches (epilogue, afterword, coda, postscript). |
| 10 | CLI shows progress during parsing (chapters processed) and a summary after (chapter count, segment count, dialogue count) | VERIFIED | `run_parse()` wraps chapter iteration with `rich.progress.track()`; prints coloured summary via `rprint()` with chapter count, segment count, dialogue count, and output path. |

**Overall score: 10/10 must-haves verified**

---

## Required Artifacts

| Artifact                        | Min Lines | Actual Lines | Status     | Key Evidence                                                        |
|---------------------------------|-----------|--------------|------------|---------------------------------------------------------------------|
| `pyproject.toml`                | —         | 27           | VERIFIED   | All 6 deps: EbookLib, beautifulsoup4, lxml, nltk, typer, rich; `requires-python = ">=3.11,<3.12"`; pytest as dev dep. |
| `src/parser/models.py`          | —         | 37           | VERIFIED   | `class SegmentType(str, Enum)` with exactly 4 values; `@dataclass class Segment` with 6 fields; stdlib only. |
| `src/parser/epub_reader.py`     | —         | 173          | VERIFIED   | Exports `load_epub` and `get_story_chapters`; 3-tier front matter + back matter detection; spine iteration. |
| `src/parser/html_cleaner.py`    | —         | 54           | VERIFIED   | Exports `chapter_to_text_blocks`; lxml backend; CSS class preservation; body-content-only extraction. |
| `src/parser/segmenter.py`       | 60        | 385          | VERIFIED   | Exports `process_chapter_blocks`, `classify_block`, `split_to_segments`; `CHAR_LIMIT = 280`; NLTK bootstrap. |
| `tests/test_segmenter.py`       | 80        | 402          | VERIFIED   | 52 test functions across 8 test classes; all pass; covers PARSE-03, PARSE-04, PARSE-06. |
| `src/parser/__init__.py`        | —         | 12           | VERIFIED   | Exports `load_epub`, `get_story_chapters`, `chapter_to_text_blocks`, `process_chapter_blocks` with `__all__`. |
| `main.py`                       | 40        | 111          | VERIFIED   | `app = typer.Typer(no_args_is_help=True)`; 6 commands with docstrings; `.epub` extension validation; entry point. |
| `src/pipeline.py`               | 30        | 127          | VERIFIED   | Exports `run_parse` and `run_full_pipeline`; Rich progress; JSON output with `indent=2, ensure_ascii=False`. |

---

## Key Link Verification

| From                          | To                          | Via                                       | Status  | Evidence                                                                 |
|-------------------------------|-----------------------------|-------------------------------------------|---------|--------------------------------------------------------------------------|
| `src/parser/epub_reader.py`   | `ebooklib`                  | `book.spine` iteration + `get_item_with_id` | WIRED | Line 74: `for item_id, linear in book.spine:` with `book.get_item_with_id(item_id)` |
| `src/parser/html_cleaner.py`  | `beautifulsoup4`            | `BeautifulSoup(content, "lxml")` on `get_body_content()` | WIRED | Lines 33, 37: `content = item.get_body_content()` then `soup = BeautifulSoup(content, "lxml")` |
| `src/parser/epub_reader.py`   | `src/parser/html_cleaner.py` (pattern) | `find_all(["h1", "h2"])` for heading scan | WIRED | Line 121: `for tag in soup.find_all(["h1", "h2"])` inside `_find_story_start()` |
| `src/parser/segmenter.py`     | `nltk`                      | `sent_tokenize` for sentence boundary detection | WIRED | Line 239: `sentences = nltk.tokenize.sent_tokenize(text)` |
| `src/parser/segmenter.py`     | `src/parser/models.py`      | Creates `Segment` instances with `SegmentType` values | WIRED | Line 13: `from src.parser.models import Segment, SegmentType`; line 373: `segment = Segment(...)` |
| `main.py`                     | `src/pipeline.py`           | CLI commands call pipeline functions       | WIRED  | Line 8: `from src.pipeline import run_full_pipeline, run_parse` |
| `src/pipeline.py`             | `src/parser/epub_reader.py` | Parse phase loads EPUB and gets story chapters | WIRED | Lines 21, 62-63: import and usage of `load_epub`, `get_story_chapters` |
| `src/pipeline.py`             | `src/parser/html_cleaner.py` | Parse phase converts chapters to text blocks | WIRED | Lines 22, 71: import and usage of `chapter_to_text_blocks` |
| `src/pipeline.py`             | `src/parser/segmenter.py`   | Parse phase processes text blocks into segments | WIRED | Lines 23, 80: import and usage of `process_chapter_blocks` |
| `src/pipeline.py`             | `output/{book-slug}/segments.json` | `json.dump` with `dataclasses.asdict` | WIRED | Lines 91-95: `json.dump([dataclasses.asdict(s) for s in all_segments], f, ensure_ascii=False, indent=2)` |

All 10 key links: WIRED

---

## Requirements Coverage

| Requirement | Source Plan | Description                                                                         | Status    | Evidence                                                                                           |
|-------------|-------------|-------------------------------------------------------------------------------------|-----------|----------------------------------------------------------------------------------------------------|
| PARSE-01    | 01-01-PLAN  | Parse EPUB (EPUB2 or EPUB3) and extract chapters in reading order                  | SATISFIED | `epub_reader.py` uses `book.spine` iteration (spine = reading order); handles both EPUB2 and EPUB3 via `ignore_ncx=True` |
| PARSE-02    | 01-01-PLAN  | Strip HTML tags and produce clean, speech-ready text per chapter                   | SATISFIED | `html_cleaner.py` uses `tag.get_text(separator=" ", strip=True)` on block-level tags only         |
| PARSE-03    | 01-02-PLAN  | Split text into segments tagged as narration, dialogue, chapter heading, or scene break | SATISFIED | `classify_block()` in `segmenter.py` returns one of four `SegmentType` values; 18 tests covering all types pass |
| PARSE-04    | 01-02-PLAN  | Detect dialogue by identifying text within quotation marks (straight and curly variants) | SATISFIED | `_contains_dialogue_quote()` handles `"`, `\u201c`/`\u201d`, `\u2018`/`\u2019`; apostrophe excluded; 11 tests pass |
| PARSE-05    | 01-01-PLAN  | Filter out front matter, copyright pages, TOC, and dedication pages                 | SATISFIED | 3-tier hybrid detection in `_find_story_start()`; back matter exclusion in `_find_story_end()`    |
| PARSE-06    | 01-02-PLAN  | Split segments exceeding 280 characters at sentence boundaries for TTS compatibility | SATISFIED | `split_to_segments()` uses NLTK sentence tokenization; `_split_long_sentence()` handles over-limit sentences; `CHAR_LIMIT = 280`; tests confirm no segment exceeds limit |
| PARSE-07    | 01-03-PLAN  | Output ordered segments as JSON for downstream phases                               | SATISFIED | `run_parse()` writes `output/{slug}/segments.json` with `json.dump(..., indent=2, ensure_ascii=False)` |
| CLI-01      | 01-03-PLAN  | User can run full pipeline end-to-end with single command (`python main.py convert book.epub`) | SATISFIED | `convert` command in `main.py` calls `run_full_pipeline()`; no prompts; designed for unattended runs |
| CLI-02      | 01-03-PLAN  | User can run individual phases separately (parse, analyze, synthesize, assemble)   | SATISFIED | 6 CLI commands registered: `parse`, `convert`, `attribute`, `match`, `synthesize`, `assemble`; stubs exit cleanly |

All 9 phase-1 requirements: SATISFIED

No orphaned requirements: REQUIREMENTS.md maps exactly PARSE-01 through PARSE-07 and CLI-01, CLI-02 to Phase 1. All 9 IDs are claimed across the three plans and verified above.

---

## Anti-Patterns Found

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| `main.py` (stub commands) | `rprint("[yellow]Not yet implemented...")` + `raise typer.Exit(code=0)` | Info | By design — plan explicitly specifies Phase 2-5 stubs. Not a defect. |
| `src/pipeline.py` (`run_full_pipeline`) | `rprint("[yellow]Phase 2 (attribute): not yet implemented...")` | Info | By design — stub messages for unimplemented phases. Not a defect. |

No blocker anti-patterns. No forbidden `get_items_of_type` usage. No `return null`, empty implementations, or placeholder components in functional code paths.

---

## Human Verification Required

### 1. Real EPUB end-to-end test

**Test:** Run `python main.py parse /path/to/a-real-novel.epub` with a known fiction EPUB (EPUB2 and EPUB3 variants)
**Expected:** `output/{slug}/segments.json` written; progress bar shown; summary prints chapter count, segment count, dialogue count; JSON is valid array of objects with `id`, `chapter`, `chapter_title`, `type`, `text`, `char_count` fields; no segment has `char_count > 280`; segment types are only `narration`, `dialogue`, `chapter_heading`, `scene_break`
**Why human:** No test EPUB is present in the repository. The parsing logic (especially front matter detection) requires a real EPUB to validate the 3-tier heuristics behave correctly on actual publisher output.

### 2. Front matter exclusion accuracy

**Test:** Run `python main.py parse` against an EPUB with known front matter (copyright page, ToC, dedication) and an EPUB with minimal front matter
**Expected:** Story chapters only appear in `segments.json`; copyright/ToC/dedication chapters are absent; chapter 1 aligns with the actual narrative start
**Why human:** The 3-tier detection uses heuristics (guide element, heading text patterns, include-all fallback). Correctness on diverse EPUBs cannot be verified without running against real books.

### 3. CLI help output

**Test:** Run `python main.py --help`, `python main.py parse --help`, `python main.py convert --help`, `python main.py attribute --help`
**Expected:** All commands listed with descriptions; argument/option names and types shown; output is readable and clear
**Why human:** Visual CLI output quality requires human review.

---

## Verified Anti-Pattern Absence

- `get_items_of_type` — absent from all source files (confirmed by grep)
- `return null` / empty stub implementations in functional paths — none found
- TODO/FIXME/PLACEHOLDER comments — none found in source files
- Empty handlers or console.log-only implementations — none applicable (Python project)

---

## Commit Traceability

All commits documented in SUMMARY files were verified present in git log:

| Commit   | Description                                                        | Plan |
|----------|--------------------------------------------------------------------|------|
| `72cc529` | feat(01-01): create project structure, dependencies, and data models | 01-01 |
| `b094a37` | feat(01-01): implement EPUB reader, HTML cleaner, and fix build backend | 01-01 |
| `c4e58ad` | test(01-02): add failing tests for text segmenter (RED)            | 01-02 |
| `dadf353` | feat(01-02): implement text segmenter with dialogue detection and splitting (GREEN) | 01-02 |
| `1d1b105` | feat(01-03): create pipeline orchestrator and parser package exports | 01-03 |
| `4c2ad93` | feat(01-03): create Typer CLI with all pipeline phase commands     | 01-03 |

---

## Test Suite Results

```
52 passed in 0.11s
```

All 52 tests covering PARSE-03, PARSE-04, and PARSE-06 pass against Python 3.11.14 with pytest 9.0.2.

---

_Verified: 2026-03-03_
_Verifier: Claude (gsd-verifier)_
