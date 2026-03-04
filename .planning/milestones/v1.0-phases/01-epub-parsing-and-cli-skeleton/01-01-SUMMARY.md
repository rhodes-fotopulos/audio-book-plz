---
phase: 01-epub-parsing-and-cli-skeleton
plan: 01
subsystem: parser
tags: [ebooklib, beautifulsoup4, lxml, epub, python, dataclasses, pyproject]

# Dependency graph
requires: []
provides:
  - pyproject.toml with all Phase 1 dependencies (EbookLib, beautifulsoup4, lxml, nltk, typer, rich, pytest)
  - Segment dataclass and SegmentType enum (4 values) in src/parser/models.py
  - load_epub() function with warning suppression and ignore_ncx option
  - get_story_chapters() with 3-tier hybrid front/back matter detection
  - chapter_to_text_blocks() extracting (tag, text, attrs) tuples from EPUB XHTML
  - Python 3.11.14 virtual environment via uv (.venv)
affects:
  - 01-02-PLAN (segmenter uses html_cleaner output as input)
  - 01-03-PLAN (CLI uses epub_reader and html_cleaner)
  - All downstream phases (Segment model is the core data contract)

# Tech tracking
tech-stack:
  added:
    - EbookLib 0.20 (EPUB loading and spine iteration)
    - beautifulsoup4 4.14.3 with lxml 6.0.2 backend (XHTML parsing)
    - nltk 3.9.3 (sentence tokenization, used in Plan 02)
    - typer 0.24.1 (CLI framework, used in Plan 03)
    - rich 14.3.3 (terminal output, used in Plan 03)
    - pytest 9.0.2 (dev dependency for Plan 02 TDD)
    - uv (virtual environment and package management tool)
  patterns:
    - Spine-order iteration via book.spine + get_item_with_id() (never manifest order)
    - 3-tier hybrid front matter detection (guide -> heading scan -> include all)
    - get_body_content() + BeautifulSoup(content, 'lxml') pattern for XHTML extraction
    - warnings.catch_warnings() with filterwarnings for ebooklib warning suppression
    - Dataclass-based Segment model with SegmentType enum for clean data contracts

key-files:
  created:
    - pyproject.toml
    - src/__init__.py
    - src/parser/__init__.py
    - src/parser/models.py
    - src/parser/epub_reader.py
    - src/parser/html_cleaner.py
  modified: []

key-decisions:
  - "setuptools.build_meta used as build backend (setuptools.backends.legacy not available in Python 3.11 setuptools bundled with uv)"
  - "uv venv .venv with Python 3.11.14 (uv auto-downloaded) since system Python is 3.14 and pip install is blocked by PEP 668"
  - "4 SegmentType values only (no 5th for internal monologue) - Phase 2 LLM is better positioned for that distinction"
  - "Back matter scanner stops at first unrecognised chapter rather than scanning entire book end to start"

patterns-established:
  - "Spine iteration: always use book.spine + get_item_with_id(), never get_items_of_type(ITEM_DOCUMENT)"
  - "XHTML extraction: item.get_body_content() -> BeautifulSoup(content, 'lxml') -> iterate block tags"
  - "Warning suppression: warnings.catch_warnings() + filterwarnings for ebooklib UserWarning"

requirements-completed:
  - PARSE-01
  - PARSE-02
  - PARSE-05

# Metrics
duration: 2min
completed: 2026-03-04
---

# Phase 01 Plan 01: Project Foundation and EPUB Parser Summary

**EPUB loading with 3-tier hybrid front/back matter detection using ebooklib spine iteration and BeautifulSoup lxml extraction, plus Segment/SegmentType data model and full dependency stack**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-04T05:35:25Z
- **Completed:** 2026-03-04T05:38:02Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Segment dataclass and SegmentType enum (4 values) as the core data contract for all downstream phases
- pyproject.toml with 6 core dependencies (EbookLib, beautifulsoup4, lxml, nltk, typer, rich) and Python 3.11 constraint
- epub_reader.py with load_epub() (warning suppression, ignore_ncx) and get_story_chapters() (3-tier hybrid front matter + back matter exclusion)
- html_cleaner.py with chapter_to_text_blocks() returning (tag, text, attrs) tuples preserving CSS classes for scene break detection
- Python 3.11.14 virtual environment via uv with all 23 packages installed

## Task Commits

Each task was committed atomically:

1. **Task 1: Create project structure, dependencies, and data models** - `72cc529` (feat)
2. **Task 2: Implement EPUB reader and HTML cleaner** - `b094a37` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `pyproject.toml` - Project dependencies and Python 3.11 constraint; all 6 core deps + pytest dev dep
- `src/__init__.py` - Package marker
- `src/parser/__init__.py` - Package marker
- `src/parser/models.py` - Segment dataclass and SegmentType enum (4 values)
- `src/parser/epub_reader.py` - load_epub() and get_story_chapters() with 3-tier hybrid detection
- `src/parser/html_cleaner.py` - chapter_to_text_blocks() with lxml backend and CSS class preservation

## Decisions Made

- **Build backend:** Used `setuptools.build_meta` instead of `setuptools.backends.legacy:build` — the legacy backend path requires a very new setuptools that wasn't available in the Python 3.11 uv environment.
- **uv for environment:** System pip blocked by PEP 668 (macOS Homebrew Python protection). Used `uv venv --python 3.11` to auto-download Python 3.11.14 and manage the environment.
- **4 SegmentType values:** Followed plan discretion recommendation — no 5th type for internal monologue, as Phase 2 LLM handles that distinction better with full story context.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed build backend in pyproject.toml**
- **Found during:** Task 2 (dependency installation)
- **Issue:** `setuptools.backends.legacy:build` not available in Python 3.11 setuptools version installed by uv; `ModuleNotFoundError: No module named 'setuptools.backends'`
- **Fix:** Changed `build-backend` to `"setuptools.build_meta"` (the standard, stable backend)
- **Files modified:** `pyproject.toml`
- **Verification:** `uv pip install -e ".[dev]"` succeeded, all 23 packages installed
- **Committed in:** `b094a37` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Build backend fix was necessary for any package installation. Standard `setuptools.build_meta` is the correct, stable backend for this project. No scope creep.

## Issues Encountered

- System pip blocked by macOS PEP 668 protection (Homebrew Python) — resolved by using `uv venv` which auto-downloads and manages Python 3.11.14 in `.venv/`.
- EPUB3 landmarks vs. `book.guide` open question from research noted: implemented guide check for EPUB2 with BeautifulSoup fallback for heading scan; EPUB3 landmarks behavior can be verified with test EPUBs in Plan 02.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 02 (segmenter TDD) can start immediately: `src/parser/models.py`, `src/parser/html_cleaner.py` are the inputs, and `.venv` has pytest installed
- Plan 03 (CLI skeleton) can start immediately: `src/parser/epub_reader.py` + `src/parser/html_cleaner.py` + typer/rich are all available
- Virtual environment at `.venv/` — activate with `source .venv/bin/activate` or use `.venv/bin/python`

## Self-Check: PASSED

- All 6 source files created and present on disk
- SUMMARY.md created at correct path
- Commits 72cc529 and b094a37 verified in git log
- Segment instantiates correctly with all fields
- SegmentType has exactly 4 values
- All module imports succeed
- Anti-pattern `get_items_of_type` not used anywhere in src/

---
*Phase: 01-epub-parsing-and-cli-skeleton*
*Completed: 2026-03-04*
