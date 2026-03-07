# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.2 — Voice Expression

**Shipped:** 2026-03-07
**Phases:** 3 | **Plans:** 6 | **Tasks:** 13

### What Was Built
- Unified VoiceProfile model (9 fields) replacing duplicated VoiceQualities + VoiceBaseline
- Emotion system fully removed from pipeline (incompatible with Base model voice cloning)
- LLM result caching for trait matcher with smart invalidation
- Per-character voice reference caching (two-layer: load_audio + encode)
- Batch-by-character synthesis ordering via --batch-by-character flag
- Speech-act FX and LLM refinement made opt-in via feature flags

### What Worked
- Milestone restructure from 5 to 3 phases was decisive and correct -- discovered early that emotion system was incompatible, cut scope immediately
- TDD approach on Phase 13 plans produced clean, testable code with no regressions
- Small focused plans (2 plans per phase) kept execution fast -- all 6 plans completed in under 40 minutes total
- Evidence-based decisions: tested Qwen3-TTS Base model limitations before building emotion system, avoided wasted work

### What Was Inefficient
- Original v1.2 requirements overestimated what was possible with Base model -- 7 requirements dropped, 3 superseded out of 16 total
- Phase 11 plan said "backward compatible" but implementation chose clean break -- requirement MODEL-02 was technically not met as originally written (regeneration required)
- Some phase SUMMARY durations don't include research/planning time -- only execution time tracked

### Patterns Established
- Feature flag wiring pattern: CLI --flag -> pipeline param -> config dataclass -> gated code path
- LLM caching pattern: cache key from all inputs that affect output, check before call, write after success
- Two-layer cache pattern for TTS references: load_audio + encode wrapping
- _process_segment extraction pattern: shared helper for iteration strategy variants

### Key Lessons
1. Validate TTS model capabilities before designing expression systems -- would have saved 2 phases of planning
2. Milestone restructuring mid-flight works well when done decisively with clear rationale
3. Cache invalidation keys must include the full input space (not just the primary key) -- learned from trait matcher needing candidate pool in key
4. Extraction of shared helpers (_process_segment) should happen during initial implementation, not as refactoring debt

### Cost Observations
- Sessions: ~3 (research, phase 11+12, phase 13)
- Notable: All 6 plans executed in under 40 minutes total -- fastest milestone yet

---

## Milestone: v1.1 — Pipeline Quality Improvements

**Shipped:** 2026-03-04
**Phases:** 4 | **Plans:** 12

### What Was Built
- Qwen3-TTS 1.7B via mlx-audio replacing Chatterbox TTS
- 14B LLM with hybrid regex+LLM dialogue detection and speech-act tagging
- Three-layer emotion system (character baselines, scene moods, line overrides)
- Professional mastering chain via pedalboard
- Voice consistency verification via Resemblyzer
- ACX-grade MP3 export (44.1kHz 192kbps CBR)

### What Worked
- TTS engine swap was well-isolated and clean
- Comprehensive test coverage caught integration issues early

### What Was Inefficient
- Emotion system built in v1.1 was removed in v1.2 -- discovered Base model can't use it with voice cloning
- CLI wiring bugs required a dedicated Phase 10 to fix

### Key Lessons
1. Test CLI wiring end-to-end during feature phases, not in a separate "fix" phase
2. Validate TTS model capabilities before building systems around them

---

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-04
**Phases:** 6 | **Plans:** 17

### What Was Built
- Full EPUB-to-audiobook pipeline
- LLM character extraction and speaker attribution
- Voice matching against 2,443 LibriTTS-P speakers
- TTS synthesis with checkpoint/resume
- Audio assembly with chapter markers

### What Worked
- Sequential phase architecture worked perfectly for memory-constrained M4
- Per-segment WAV intermediates enabled reliable checkpoint/resume

### What Was Inefficient
- Integration issues required dedicated Phase 6 -- should have integration tested earlier
- Phases 2-5 never formally verified

### Key Lessons
1. Integration test the full pipeline incrementally, not just at the end
2. Per-segment intermediates are worth the disk cost for long-running batch jobs

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 6 | 17 | Initial build, integration phase needed |
| v1.1 | 4 | 12 | Quality focus, CLI fix phase needed |
| v1.2 | 3 | 6 | Scope cut mid-flight, TDD adopted, fastest execution |

### Top Lessons (Verified Across Milestones)

1. Integration test early and continuously -- validated across v1.0 (Phase 6 needed) and v1.1 (Phase 10 needed)
2. Validate external model capabilities before designing systems -- validated by v1.1 emotion system being removed in v1.2
3. Small, focused plans execute faster than large ones -- v1.2's 2-plan phases were the fastest milestone
