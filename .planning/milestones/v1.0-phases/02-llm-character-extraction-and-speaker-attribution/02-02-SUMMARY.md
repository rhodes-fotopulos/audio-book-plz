---
phase: 02-llm-character-extraction-and-speaker-attribution
plan: 02
subsystem: llm
tags: [ollama, qwen3, character-extraction, alias-merging, caching, nlp]

# Dependency graph
requires:
  - src/attribution/models.py (CharacterProfile, ChapterExtractionResult from Plan 01)
  - src/attribution/llm_client.py (call_llm_structured, estimate_tokens from Plan 01)
  - src/attribution/cache.py (get_cache_key, check_cache, write_cache from Plan 01)
provides:
  - Character extraction pass with chapter-level LLM calls and caching (src/attribution/extractor.py)
  - Character merger with three-stage deduplication (src/attribution/merger.py)
  - extract_all_characters() returns per-chapter character lists
  - merge_characters() returns deduplicated character registry
affects:
  - Plan 02-03 (attributor uses character registry from merger)
  - Phase 3 (characters.json consumed by voice matching)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Chapter text formatting: [TYPE] text prefix for LLM context — helps model distinguish dialogue from narration"
    - "Three-stage merge: exact name -> substring/alias -> alias overlap (with surname-only exclusion)"
    - "Oversized chapter splitting: scene breaks -> paragraph boundaries -> line boundaries"
    - "Token budget: CONTEXT_WINDOW - SYSTEM_PROMPT_TOKENS - RESPONSE_BUDGET = available for content"

key-files:
  created:
    - src/attribution/extractor.py
    - src/attribution/merger.py

key-decisions:
  - "Chapter text prefixed with [TYPE] brackets (e.g., [DIALOGUE], [NARRATION]) to help LLM distinguish segment types"
  - "MIN_SUBSTRING_LENGTH=3 for alias matching — avoids matching trivial strings like 'I' or 'Mr'"
  - "Surname-only check prevents merging 'Mr. Bennet' and 'Mrs. Bennet' while still allowing 'Darcy' / 'Mr. Darcy'"
  - "Voice quality merge prefers longer description as evidence heuristic when both profiles have non-unknown values"
  - "MIN_CHUNK_CHARS=1000 prevents trivially small LLM requests when splitting oversized chapters"

patterns-established:
  - "Per-chapter extraction with cache check before LLM call — cache key includes pass_name for differentiation"
  - "Merge profiles using canonical name (longest/most formal) with all variants as aliases"
  - "Sort registry: named characters first, then alphabetically by name"

requirements-completed:
  - ATTR-01
  - ATTR-02
  - ATTR-05

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 02 Plan 02: Character Extraction and Alias Merger Summary

**Chapter-level character extraction via Qwen3 8B with three-stage merge deduplication (exact name, substring/alias, alias overlap) and surname-only exclusion**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Character extractor processes chapters sequentially through LLM with cache-first strategy (ATTR-01, ATTR-06)
- Oversized chapter splitting at scene breaks / paragraph boundaries for 32K context window (ATTR-05)
- Three-stage merge pipeline: exact name match -> substring/alias detection -> alias overlap (ATTR-02)
- Surname-only exclusion prevents merging different characters who share a last name

## Task Commits

Each task was committed atomically:

1. **Task 1: Create character extractor with chapter-level LLM calls and caching** - `1d70bcf` (feat)
2. **Task 2: Create character merger with alias detection and deduplication** - `8c66eb5` (feat)

## Files Created/Modified

- `src/attribution/extractor.py` - Chapter-level extraction with caching, chunking, and LLM calls
- `src/attribution/merger.py` - Three-stage merge with substring matching and surname exclusion

## Decisions Made

- [TYPE] prefixes on chapter text help the LLM distinguish dialogue from narration
- MIN_SUBSTRING_LENGTH=3 prevents false positive matches on short strings
- Longer description used as evidence heuristic for voice quality conflict resolution

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Extractor and merger ready for integration in Plan 02-03
- Plan 02-03 will wire these into the pipeline and add the attribution pass

## Self-Check: PASSED

- `src/attribution/extractor.py` exists with extract_characters_from_chapter function
- `src/attribution/merger.py` exists with merge_characters function
- EXTRACTION_SYSTEM_PROMPT contains 'character'
- MAX_CONTENT_CHARS is positive
- _build_chapter_text produces [TYPE] prefixed text
- _split_chapter_text returns single-element list for short text
- _names_match_substring('Darcy', 'Mr. Darcy') returns True
- _names_match_substring('Mr', 'Mr. Darcy') returns False
- _names_share_surname_only('Mr. Bennet', 'Mrs. Bennet') returns True
- _merge_two_profiles preserves aliases and uses longer name as canonical
- Commits 1d70bcf and 8c66eb5 verified in git log

---
*Phase: 02-llm-character-extraction-and-speaker-attribution*
*Completed: 2026-03-03*
