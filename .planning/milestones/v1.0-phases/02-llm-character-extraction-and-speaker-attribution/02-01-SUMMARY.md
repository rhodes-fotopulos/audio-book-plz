---
phase: 02-llm-character-extraction-and-speaker-attribution
plan: 01
subsystem: llm
tags: [ollama, pydantic, qwen3, structured-output, caching, hashlib]

# Dependency graph
requires:
  - src/parser/models.py (Segment, SegmentType from Phase 1)
provides:
  - Pydantic models for character profiles, extraction results, attribution results (src/attribution/models.py)
  - Ollama structured output client with retry logic and /no_think mode (src/attribution/llm_client.py)
  - Content-hash-keyed JSON file cache with atomic writes (src/attribution/cache.py)
  - ollama>=0.6 and pydantic>=2.0 in pyproject.toml dependencies
affects:
  - Plan 02-02 (extractor uses llm_client and cache)
  - Plan 02-03 (attributor uses llm_client, cache, and models)
  - Phase 3 (CharacterProfile schema consumed by voice matching)

# Tech tracking
tech-stack:
  added:
    - ollama 0.6.1 (Python client for Ollama REST API)
    - pydantic 2.12.5 (schema definition and JSON validation)
    - httpx 0.28.1 (transitive dependency from ollama)
  patterns:
    - "Structured output: schema_class.model_json_schema() -> format param -> schema_class.model_validate_json(response)"
    - "LLM retry loop: for attempt in range(1, MAX_RETRIES+1) with try/except ValidationError + Exception"
    - "Cache key: hashlib.sha256(f'{pass_name}:{content}'.encode()).hexdigest()"
    - "Atomic cache write: write to .tmp file, then Path.rename() to final path"
    - "Qwen3 no-think: append ' /no_think' to system prompt for direct JSON output"

key-files:
  created:
    - src/attribution/__init__.py
    - src/attribution/models.py
    - src/attribution/llm_client.py
    - src/attribution/cache.py
  modified:
    - pyproject.toml

key-decisions:
  - "Pydantic strict mode (ConfigDict(strict=True)) on value objects (VoiceQualities, Relationship, SegmentAttribution) but not on container models — balances type safety with LLM flexibility"
  - "Temperature 0 with format constraint — Qwen3 warns against greedy without schema but format param provides token-level determinism"
  - "estimate_tokens uses conservative 1:4 char-to-token ratio — actual Qwen3 ratio is often higher (fewer tokens per char)"
  - "Cache keys include pass_name prefix to differentiate extraction and attribution results for same chapter text"

patterns-established:
  - "All LLM calls go through call_llm_structured() — single entry point with retry, logging, and schema validation"
  - "Cache uses content-hash keys — any change in chapter text invalidates the cache automatically"
  - "Model unload via unload_model() — call at phase boundary to free GPU memory"

requirements-completed:
  - ATTR-05
  - ATTR-06

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 02 Plan 01: Data Models, LLM Client, and Cache Summary

**Pydantic schemas for character profiles and LLM responses, Ollama structured output client with retry logic and /no_think mode, content-hash-keyed JSON cache with atomic writes**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- 8 Pydantic models defining the full contract between the LLM and the attribution pipeline (CharacterProfile, VoiceQualities, Relationship, ChapterExtractionResult, SegmentAttribution, ChapterAttributionResult, AttributedSegment)
- Ollama client wrapper (`call_llm_structured`) with format-constrained decoding, /no_think suffix for Qwen3, and 3-attempt retry logic
- Content-hash cache module with atomic writes (write-to-tmp-then-rename) for crash-safe incremental re-runs
- `ollama>=0.6` and `pydantic>=2.0` installed in project venv

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Pydantic data models and install dependencies** - `6ce9c7c` (feat)
2. **Task 2: Create LLM client wrapper and cache module** - `7c7d43c` (feat)

## Files Created/Modified

- `src/attribution/__init__.py` - Empty package init (populated in Plan 03)
- `src/attribution/models.py` - 8 Pydantic models for LLM schemas and output types
- `src/attribution/llm_client.py` - Ollama structured output wrapper with retry and /no_think
- `src/attribution/cache.py` - SHA-256-keyed JSON file cache with atomic writes
- `pyproject.toml` - Added ollama>=0.6 and pydantic>=2.0 dependencies

## Decisions Made

- Pydantic strict mode on value objects but not container models for LLM flexibility
- Temperature 0 is safe with format constraint (grammar-constrained decoding handles determinism)
- Conservative 1:4 char-to-token ratio for context window budgeting

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Foundation complete: models, LLM client, and cache are ready for extraction (Plan 02) and attribution (Plan 03)
- Ollama must be running with `qwen3:8b` model pulled before Plans 02-03 can execute real LLM calls

## Self-Check: PASSED

- `src/attribution/models.py` exists with CharacterProfile class
- `src/attribution/llm_client.py` exists with call_llm_structured function
- `src/attribution/cache.py` exists with check_cache function
- `pyproject.toml` contains "ollama"
- model_json_schema() produces valid JSON schema
- Cache round-trip (write/read/clear) works correctly
- estimate_tokens returns conservative integer estimate
- Commits 6ce9c7c and 7c7d43c verified in git log

---
*Phase: 02-llm-character-extraction-and-speaker-attribution*
*Completed: 2026-03-03*
