---
phase: 02-llm-character-extraction-and-speaker-attribution
plan: 03
subsystem: llm
tags: [ollama, qwen3, speaker-attribution, pipeline, cli, caching]

# Dependency graph
requires:
  - src/attribution/models.py (ChapterAttributionResult, SegmentAttribution from Plan 01)
  - src/attribution/llm_client.py (call_llm_structured, unload_model from Plan 01)
  - src/attribution/cache.py (get_cache_key, check_cache, write_cache from Plan 01)
  - src/attribution/extractor.py (extract_all_characters from Plan 02)
  - src/attribution/merger.py (merge_characters from Plan 02)
provides:
  - Speaker attribution pass with chapter-level LLM calls and caching (src/attribution/attributor.py)
  - Full Phase 2 pipeline orchestration (src/pipeline.py run_attribute)
  - CLI attribute command wired to real implementation (main.py)
  - characters.json and attributed.json output files
  - attribute_all_segments() returns fully attributed segment list
affects:
  - Phase 3 (characters.json and attributed.json consumed by voice matching)
  - Phase 4 (attributed.json consumed by TTS synthesis)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Non-dialogue segments attributed to narrator without LLM call (ATTR-04) — confidence 1.0 for chapter_heading, narration, scene_break"
    - "Registry budget: CONTEXT_WINDOW - SYSTEM_PROMPT - RESPONSE_BUDGET - REGISTRY_BUDGET = available for segment text"
    - "Dialogue context: 2 segments before and after each dialogue line included in prompt for turn-taking inference"
    - "Stats summary: character count, dialogue/narration split, confidence distribution (high/medium/low), flagged count"

key-files:
  created:
    - src/attribution/attributor.py
  modified:
    - src/attribution/__init__.py
    - src/pipeline.py
    - main.py

key-decisions:
  - "REGISTRY_BUDGET_TOKENS=2000 reserves space for character registry in attribution prompt"
  - "CONFIDENCE_FLAG_THRESHOLD=0.7 — attributions below this are flagged in stats for user review"
  - "Dialogue context window: 2 segments before + 2 after, truncated to 200 chars each for compactness"
  - "LLM failure fallback: speaker='unknown', confidence=0.0 rather than crashing"
  - "run_full_pipeline derives book_slug from epub_path to locate output directory for run_attribute"

patterns-established:
  - "Non-dialogue attribution is deterministic (no LLM) — only dialogue triggers LLM calls"
  - "Cache key for attribution uses dialogue text only (not full chapter) for differentiation"
  - "Model unloaded after attribution completes — frees GPU memory for Phase 3/4"
  - "Stats summary with Rich formatting printed after every pipeline phase completion"

requirements-completed:
  - ATTR-03
  - ATTR-04
  - ATTR-05
  - ATTR-06

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 02 Plan 03: Speaker Attribution, Pipeline Integration, and CLI Wiring Summary

**Speaker attribution pass with non-dialogue narrator assignment (no LLM), dialogue attribution via Qwen3 8B with character registry context, full pipeline wiring with characters.json and attributed.json output, and Rich stats summary**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-03-04
- **Completed:** 2026-03-04
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Speaker attributor assigns narrator to non-dialogue without LLM calls, dialogue speakers via LLM with character registry (ATTR-03, ATTR-04)
- Full Phase 2 pipeline: extraction -> merge -> attribution wired into run_attribute() with output files and model unloading
- CLI `attribute` command validates segments.json exists and calls pipeline; `convert` command chains parse -> attribute
- Rich stats summary shows character count, dialogue/narration split, confidence distribution, and flagged segments

## Task Commits

Each task was committed atomically:

1. **Task 1: Create speaker attributor with chapter-level LLM calls** - `a9e1af2` (feat)
2. **Task 2: Wire Phase 2 into pipeline and CLI with output files and stats** - `3a4c084` (feat)

## Files Created/Modified

- `src/attribution/attributor.py` - Speaker attribution with non-dialogue narrator, dialogue LLM calls, batching, and caching
- `src/attribution/__init__.py` - Public API exports for attribution package
- `src/pipeline.py` - run_attribute() orchestrating extraction -> merge -> attribution with output files and stats
- `main.py` - CLI attribute command wired to run_attribute with segments.json validation

## Decisions Made

- REGISTRY_BUDGET_TOKENS=2000 balances registry detail vs content space in context window
- Confidence flag threshold at 0.7 catches moderate-to-weak attributions for review
- 2-segment context window around each dialogue line for turn-taking inference
- LLM failure produces speaker="unknown" with confidence=0.0 rather than crashing

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 2 complete — all 3 plans executed successfully
- characters.json and attributed.json ready for Phase 3 (voice-character matching)
- Ollama model unloaded after attribution to free memory for future phases
- Ready for phase verification and transition to Phase 3

## Self-Check: PASSED

- `src/attribution/attributor.py` exists with attribute_chapter function
- `src/attribution/__init__.py` exports extract_all_characters and attribute_all_segments
- `src/pipeline.py` has run_attribute function
- `main.py` imports run_attribute and validates segments.json
- Attributor imports ChapterAttributionResult from models
- Pipeline imports extract_all_characters, merge_characters, attribute_all_segments
- Commits a9e1af2 and 3a4c084 verified in git log

---
*Phase: 02-llm-character-extraction-and-speaker-attribution*
*Completed: 2026-03-04*
