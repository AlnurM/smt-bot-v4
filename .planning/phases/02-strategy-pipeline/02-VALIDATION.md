---
phase: 2
slug: strategy-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-19
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24+ |
| **Config file** | `pytest.ini` (exists from Phase 1) |
| **Quick run command** | `pytest tests/test_scanner.py tests/test_strategy_filter.py -x -q` |
| **Full suite command** | `pytest tests/ -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_scanner.py tests/test_strategy_filter.py -x -q`
- **After every plan wave:** Run `pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | SCAN-01 | unit | `pytest tests/test_scanner.py::test_top_n_by_volume -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | SCAN-02 | unit | `pytest tests/test_scanner.py::test_scheduler_job_registered -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | SCAN-03 | unit | `pytest tests/test_scanner.py::test_volume_filter -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | SCAN-04 | unit | `pytest tests/test_scanner.py::test_top_n_configurable -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | STRAT-03 | unit | `pytest tests/test_scanner.py::test_ohlcv_fetch_format -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | STRAT-01 | unit | `pytest tests/test_claude_engine.py::test_request_structure -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | STRAT-02 | unit | `pytest tests/test_claude_engine.py::test_strategy_schema_validation -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | STRAT-04 | unit | `pytest tests/test_claude_engine.py::test_prompt_contains_walk_forward -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | FILT-01 | unit | `pytest tests/test_strategy_filter.py::test_all_criteria_checked -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | FILT-02 | unit | `pytest tests/test_strategy_filter.py::test_default_criteria -x` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | FILT-03 | unit | `pytest tests/test_strategy_filter.py::test_relaxed_mode -x` | ❌ W0 | ⬜ pending |
| 02-03-04 | 03 | 2 | FILT-04 | unit | `pytest tests/test_strategy_manager.py::test_failed_strategy_logged -x` | ❌ W0 | ⬜ pending |
| 02-03-05 | 03 | 2 | FILT-05 | unit | `pytest tests/test_strategy_manager.py::test_criteria_snapshot_saved -x` | ❌ W0 | ⬜ pending |
| 02-03-06 | 03 | 2 | STRAT-05 | unit | `pytest tests/test_strategy_manager.py::test_skip_if_active -x` | ❌ W0 | ⬜ pending |
| 02-03-07 | 03 | 2 | LIFE-01 | unit | `pytest tests/test_strategy_manager.py::test_strategy_fields_saved -x` | ❌ W0 | ⬜ pending |
| 02-03-08 | 03 | 2 | LIFE-02 | unit | `pytest tests/test_strategy_manager.py::test_expiry_detection -x` | ❌ W0 | ⬜ pending |
| 02-03-09 | 03 | 2 | LIFE-03 | unit | `pytest tests/test_strategy_manager.py::test_old_strategy_deactivated -x` | ❌ W0 | ⬜ pending |
| 02-03-10 | 03 | 2 | LIFE-04 | unit | `pytest tests/test_strategy_manager.py::test_review_interval_stored -x` | ❌ W0 | ⬜ pending |
| 02-03-11 | 03 | 2 | LIFE-05 | unit | `pytest tests/test_strategy_manager.py::test_criteria_snapshot_stored -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_scanner.py` — covers SCAN-01 through SCAN-04, STRAT-03
- [ ] `tests/test_claude_engine.py` — covers STRAT-01, STRAT-02, STRAT-04
- [ ] `tests/test_strategy_filter.py` — covers FILT-01, FILT-02, FILT-03
- [ ] `tests/test_strategy_manager.py` — covers STRAT-05, FILT-04, FILT-05, LIFE-01 through LIFE-05

*Existing test infrastructure (conftest.py, pytest.ini) is sufficient — no framework changes needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Claude code_execution returns valid strategy | STRAT-01 | Requires live Anthropic API key and real OHLCV data | Run scanner manually, verify strategy JSON in DB |
| End-to-end scan cycle | SCAN-01+STRAT-01 | Full pipeline with live APIs | Trigger `/scan` or wait for hourly job, check DB for new strategies |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
