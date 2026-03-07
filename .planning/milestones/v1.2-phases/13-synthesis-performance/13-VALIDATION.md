---
phase: 13
slug: synthesis-performance
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-07
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | tests/ directory (existing) |
| **Quick run command** | `python -m pytest tests/test_synthesizer.py tests/test_trait_matcher.py -x -q` |
| **Full suite command** | `python -m pytest tests/ -x -q --ignore=tests/test_trait_matcher.py` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_synthesizer.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 13-01-01 | 01 | 1 | SYNTH-05 | unit | `python -m pytest tests/test_synthesizer.py -x -q` | ❌ W0 | ⬜ pending |
| 13-01-02 | 01 | 1 | SYNTH-06 | unit | `python -m pytest tests/test_synthesizer.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_synthesizer.py` — add reference cache and batch-by-character tests (stubs)
- [ ] Existing test infrastructure covers framework needs

*Existing pytest infrastructure covers all phase requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Measurable time reduction with reference caching | SYNTH-05 | Requires actual TTS model loaded | Run synthesis on test book, compare wall time with/without cache |
| Identical output regardless of batch ordering | SYNTH-06 | Requires full synthesis comparison | Run same book with and without --batch-by-character, compare WAV checksums |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
