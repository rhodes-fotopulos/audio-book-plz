---
phase: 08-llm-intelligence-and-emotion
plan: 01
subsystem: attribution
tags: [ollama, qwen3, psutil, model-selection, keep-alive]

requires:
  - phase: 07-tts-engine-swap
    provides: "Engine abstraction and synthesis pipeline"
provides:
  - "RAM-based model selection (14B/8B) with user override"
  - "Model lifecycle management (preload with keep_alive=-1, unload with keep_alive=0)"
  - "--model CLI flag on attribute, match, and convert commands"
  - "Active model tracking across LLM phases"
affects: [08-02, 08-03, attribution, pipeline]

tech-stack:
  added: [psutil]
  patterns: [module-level state tracking, RAM-based auto-selection]

key-files:
  created: [tests/test_llm_client.py]
  modified: [src/attribution/llm_client.py, src/attribution/__init__.py, src/pipeline.py, main.py, pyproject.toml]

key-decisions:
  - "RAM threshold set to 12.0 GB (14B Q4_K_M ~10GB weights + ~2GB KV cache q8_0)"
  - "Module-level _active_model state for cross-function model tracking"
  - "preload_model() auto-selects via select_model() when no model specified"

patterns-established:
  - "Model lifecycle: preload at phase start, keep_alive=-1 through all LLM calls, unload at phase boundary"
  - "Pipeline model_override parameter threading from CLI through pipeline to llm_client"

requirements-completed: [LLM-01, LLM-03]

duration: 15min
completed: 2026-03-04
---

# Plan 08-01: LLM Model Upgrade Summary

**RAM-based model selection (qwen3:14b/8b) with keep_alive lifecycle and --model CLI override**

## Performance

- **Duration:** ~15 min
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- select_model() returns qwen3:14b when RAM >= 12GB, falls back to qwen3:8b with warning
- preload_model() pins model in Ollama with keep_alive=-1 (resident until explicit unload)
- Pipeline preloads model before extraction/matching, unloads before TTS synthesis
- --model flag available on attribute, match, and convert CLI commands
- 11 unit tests covering all model selection and lifecycle paths

## Task Commits

1. **Task 1: Model selection and lifecycle in llm_client.py** - `4690bdd` (feat)
2. **Task 2: Wire model lifecycle into pipeline and CLI** - `74174ce` (feat)
3. **Task 3: Unit tests for model selection** - `74174ce` (included with Task 2)

## Files Created/Modified
- `src/attribution/llm_client.py` - Refactored: select_model(), preload_model(), get_active_model(), updated call_llm_structured() and unload_model()
- `src/attribution/__init__.py` - Added select_model, preload_model, get_active_model exports
- `src/pipeline.py` - Added model_override param to run_attribute(), run_match(), run_full_pipeline(); preload_model() calls before LLM phases
- `main.py` - Added --model option to attribute, match, convert commands
- `pyproject.toml` - Added psutil>=5.9 dependency
- `tests/test_llm_client.py` - 11 tests: RAM-based selection, override bypass, preload/unload lifecycle, active model tracking

## Decisions Made
- RAM threshold 12.0 GB covers 14B Q4_K_M weights (~10GB) + KV cache q8_0 (~2GB)
- Module-level _active_model state avoids repeated select_model() calls across LLM phases
- KV cache quantization guidance in docstring (OLLAMA_KV_CACHE_TYPE=q8_0) for 16GB machines

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- psutil needed explicit `uv pip install` since `uv run` dependency resolution was blocked by mlx-audio requiring transformers==5.0.0rc3 pre-release

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Model lifecycle in place for Plans 08-02 (speech-act detection) and 08-03 (emotion system)
- Both plans use call_llm_structured() which now automatically uses the active model with keep_alive=-1
- 146 tests passing, zero regressions

---
*Phase: 08-llm-intelligence-and-emotion*
*Completed: 2026-03-04*
