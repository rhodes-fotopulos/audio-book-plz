---
phase: 14
slug: character-profile-merger-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none (discovered via pyproject.toml) |
| **Quick run command** | `python -m pytest tests/test_merger.py -x` |
| **Full suite command** | `python -m pytest tests/ -x` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_merger.py -x`
- **After every plan wave:** Run `python -m pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 1 | MERGE-01 | unit | `python -m pytest tests/test_merger.py::TestAuditTrail -x` | No -- W0 | ⬜ pending |
| 14-01-02 | 01 | 1 | MERGE-02 | unit | `python -m pytest tests/test_merger.py::TestPostMergeValidation -x` | No -- W0 | ⬜ pending |
| 14-01-03 | 01 | 1 | MERGE-03 | unit | `python -m pytest tests/test_merger.py::TestAuditOutput -x` | No -- W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | MERGE-04 | unit | `python -m pytest tests/test_merger.py::TestCrossNameExclusion -x` | No -- W0 | ⬜ pending |
| 14-02-02 | 02 | 1 | MERGE-05 | unit | `python -m pytest tests/test_merger.py::TestCooccurrenceSignal -x` | No -- W0 | ⬜ pending |
| 14-02-03 | 02 | 1 | MERGE-06 | unit | `python -m pytest tests/test_merger.py::TestTraitCap -x` | No -- W0 | ⬜ pending |
| 14-02-04 | 02 | 1 | MERGE-07 | unit | `python -m pytest tests/test_merger.py::TestSurnameExclusion -x` | No -- W0 | ⬜ pending |
| 14-02-05 | 02 | 1 | MERGE-08 | unit | `python -m pytest tests/test_merger.py::TestExtractionPrompt -x` | No -- W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_merger.py` — new file covering MERGE-01 through MERGE-08
- [ ] Test fixtures for CharacterProfile, VoiceProfile creation helpers (follow pattern from test_dedup.py)
- [ ] No framework install needed (pytest already in project)

*Existing test infrastructure covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pride & Prejudice produces separate Bennet profiles | SC-1 | Requires full pipeline run with real book | Run `python main.py convert pride-and-prejudice.epub`, inspect characters.json for separate Bennet entries |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
