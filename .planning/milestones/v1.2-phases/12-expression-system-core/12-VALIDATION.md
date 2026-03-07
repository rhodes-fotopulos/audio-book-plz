---
phase: 12
slug: expression-system-core
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-06
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | EXPR-01 (superseded) | unit | `python -m pytest tests/test_pipeline_no_emotion.py -x` | No — W0 | pending |
| 12-01-02 | 01 | 1 | EXPR-01 (superseded) | unit | `python -m pytest tests/ -x -q -k "not emotion"` | Yes | pending |
| 12-02-01 | 02 | 1 | EXPR-02 (superseded) | unit | `python -m pytest tests/test_post_processor.py -x` | Yes (needs update) | pending |
| 12-02-02 | 02 | 1 | EXPR-03 (superseded) | unit | `python -m pytest tests/test_trait_matcher.py -x` | Yes (needs cache tests) | pending |
| 12-03-01 | 03 | 2 | EXPR-01/02/03 | unit | `python -m pytest tests/ -v` | Yes | pending |

*Status: pending · green · red · flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pipeline_no_emotion.py` — verify emotion imports removed and emotion.json not produced
- [ ] Update `tests/test_post_processor.py` — verify speech-act adjustments respect `speech_act_fx` flag
- [ ] Add cache tests to `tests/test_trait_matcher.py` — verify cache hit/miss/invalidation
- [ ] Verify `tests/test_speech_acts.py` — ensure tests pass with LLM pass disabled by default
- [ ] Delete `tests/test_emotion.py` — corresponds to deleted module

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Full pipeline produces audiobook without emotion.json | EXPR-01 | End-to-end pipeline requires TTS model | Run `python -m audio_book_plz convert <book>` and verify no emotion.json in output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
