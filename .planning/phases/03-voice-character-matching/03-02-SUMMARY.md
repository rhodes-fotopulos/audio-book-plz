---
phase: 03-voice-character-matching
plan: 02
subsystem: matching
tags: [llm-matching, embedding-similarity, dedup, tdd, sentence-transformers]

requires:
  - phase: 03-voice-character-matching
    plan: 01
    provides: SpeakerAnnotation, VoiceAssignment, CastClassification models and speaker index
  - phase: 02-llm-character-extraction-and-speaker-attribution
    provides: CharacterProfile model with voice_qualities, call_llm_structured, attribution segments
provides:
  - LLM trait comparison matching (match_character_llm, match_narrator_llm)
  - Embedding similarity fallback matching (build_speaker_embeddings, match_character_embedding)
  - Major character uniqueness enforcement and minor co-occurrence dedup (enforce_uniqueness)
affects: [03-voice-character-matching]

tech-stack:
  added: ["sentence-transformers>=3.0"]
  patterns:
    - "LLM-as-casting-director with structured JSON response via call_llm_structured"
    - "Module-level model cache for lazy-loaded SentenceTransformer"
    - "Cosine similarity ranking with exclusion set for assigned speakers"
    - "Two-tier dedup: major uniqueness enforcement, minor co-occurrence checking"

key-files:
  created:
    - src/matching/trait_matcher.py
    - src/matching/embedding_matcher.py
    - src/matching/dedup.py
    - tests/test_trait_matcher.py
    - tests/test_embedding_matcher.py
    - tests/test_dedup.py
  modified:
    - pyproject.toml

key-decisions:
  - "LLM trait matcher retries up to 3 times if returned speaker_id not in candidate list"
  - "First-person narrator matching reuses protagonist voice traits; third-person infers book tone"
  - "Embedding matcher uses all-MiniLM-L6-v2 (80MB, 384-dim) on CPU for speed"
  - "Dedup keeps higher-confidence assignment and reassigns lower-confidence to next-best"
  - "Minor characters may share speakers across chapters but not within same chapter"
  - "Low embedding confidence threshold is 0.5 — below triggers warning for manual review"

patterns-established:
  - "MatchResponse Pydantic schema for structured LLM JSON output (speaker_id, reasoning, confidence)"
  - "Character description builder (_build_character_text) combines gender/age/voice/personality into natural language"
  - "Chapter co-occurrence set for efficient minor character dedup lookup"
  - "Candidate pool fallback with 0.3 confidence when embedding matcher unavailable"

requirements-completed: [VOICE-02, VOICE-03, VOICE-04]

duration: 5min
completed: 2026-03-03
---

# Plan 03-02: Voice Matching Engine Summary

**Two-tier voice matching engine with LLM trait comparison, embedding similarity fallback, and dedup enforcement for uniqueness**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-03
- **Completed:** 2026-03-03
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- LLM trait matcher using Qwen3 8B as casting director with structured MatchResponse schema and retry logic
- Narrator matching handles both first-person (protagonist voice) and third-person (book tone analysis) modes
- Embedding similarity fallback using all-MiniLM-L6-v2 for fast CPU-based cosine similarity ranking
- Dedup enforcement: no two major characters share a speaker; minor characters blocked only if co-occurring in same chapter
- 14 mock tests for trait matcher, 9 integration tests for embedding matcher (loads real model), 9 unit tests for dedup
- sentence-transformers added to project dependencies

## Task Commits

1. **Task 1: LLM trait matcher with TDD** - `dd87d81` (feat)
2. **Task 2: Embedding similarity fallback with TDD** - `1b244e7` (feat)
3. **Task 3: Dedup enforcement with TDD** - `db9ddc6` (feat)

## Files Created/Modified
- `src/matching/trait_matcher.py` - match_character_llm, match_narrator_llm with structured LLM calls
- `src/matching/embedding_matcher.py` - build_speaker_embeddings, match_character_embedding with all-MiniLM-L6-v2
- `src/matching/dedup.py` - enforce_uniqueness, _get_chapter_cooccurrence for major/minor dedup
- `tests/test_trait_matcher.py` - 14 mock tests covering LLM matching, narrator modes, assigned_ids exclusion
- `tests/test_embedding_matcher.py` - 9 integration tests with real model loading, semantic matching validation
- `tests/test_dedup.py` - 9 tests covering co-occurrence, major dedup, minor sharing rules
- `pyproject.toml` - Added sentence-transformers>=3.0 dependency

## Decisions Made
- LLM trait matcher retries up to 3 times when speaker_id not in candidate list, then returns None for embedding fallback
- First-person narrator matched using protagonist's voice traits; third-person uses tone inference (dark/light/romantic/literary)
- Embedding model cached at module level (lazy-loaded once per session) for performance
- Dedup always keeps higher-confidence assignment; lower-confidence reassigned with "Reassigned for distinctiveness" reasoning
- Co-occurrence check excludes "narrator" and "unknown" speakers from pair detection

## Deviations from Plan
None - plan executed as specified with TDD approach for all three tasks.

## Issues Encountered
- pip not available in uv-managed venv; used `uv pip install sentence-transformers` instead.

## User Setup Required
None - sentence-transformers auto-downloads the 80MB model on first use.

## Next Phase Readiness
- Trait matcher ready for orchestrator to call with pre-filtered candidates (Plan 03-03)
- Embedding matcher ready as fallback for overflow characters (Plan 03-03)
- Dedup ready for post-matching enforcement pass (Plan 03-03)
- All exports available for orchestrator integration

---
*Phase: 03-voice-character-matching*
*Completed: 2026-03-03*
