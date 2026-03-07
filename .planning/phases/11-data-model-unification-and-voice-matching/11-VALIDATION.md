---
phase: 11
slug: data-model-unification-and-voice-matching
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-06
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 7.0 |
| **Config file** | pyproject.toml (dev deps) |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

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
| 11-01-01 | 01 | 1 | MODEL-01 | unit | `python -m pytest tests/test_models.py -x -q` | No — W0 | pending |
| 11-01-02 | 01 | 1 | MODEL-01 | unit | `python -m pytest tests/test_trait_matcher.py -x -q` | Yes — fixture update | pending |
| 11-01-03 | 01 | 1 | MODEL-01 | unit | `python -m pytest tests/test_embedding_matcher.py -x -q` | Yes — fixture update | pending |
| 11-02-01 | 02 | 1 | MATCH-01 | unit | `python -m pytest tests/test_trait_matcher.py -x -q` | Yes | pending |
| 11-02-02 | 02 | 1 | MATCH-02 | unit | `python -m pytest tests/test_embedding_matcher.py -x -q` | Yes | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] Update `tests/test_trait_matcher.py` — fixtures use `VoiceQualities`, need `VoiceProfile`
- [ ] Update `tests/test_embedding_matcher.py` — fixtures use `VoiceQualities`, need `VoiceProfile`
- [ ] Update `tests/test_matching_orchestrator.py` — if it constructs CharacterProfile objects
- [ ] Any other test files importing `VoiceQualities` or `VoiceBaseline`

*These are fixture updates, not new test files — existing test logic remains valid.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| No regression in speaker selection quality | MATCH-01, MATCH-02 | Subjective quality assessment | Run pipeline on a test book, compare speaker assignments to v1.1 output |
| Matching logs show unified profile data | MATCH-01, MATCH-02 | Log output format | Run pipeline with DEBUG logging, verify VoiceProfile fields appear in matching logs |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
