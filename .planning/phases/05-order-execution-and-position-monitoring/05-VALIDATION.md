---
phase: 5
slug: order-execution-and-position-monitoring
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-20
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio 0.24+ |
| **Config file** | `pytest.ini` (exists from Phase 1) |
| **Quick run command** | `pytest tests/test_order_executor.py tests/test_position_monitor.py -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run quick run command
- **After every plan wave:** Run full suite
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 20 seconds

---

## Wave 0 Requirements

- [ ] Alembic migration: add `sl_order_id`, `tp_order_id`, `is_dry_run` to Position; unique constraint on Order.signal_id
- [ ] `tests/test_order_executor.py` — covers ORD-01 through ORD-05, dry-run
- [ ] `tests/test_position_monitor.py` — covers MON-01 through MON-05
- [ ] `tests/conftest.py` — extend mock_binance_client with futures order methods

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Market order appears on Binance Testnet | ORD-01 | Requires live API | Confirm signal, check Binance Testnet dashboard |
| SL/TP bracket visible on Testnet | ORD-02 | Requires live API | Verify SL and TP orders in Testnet open orders |
| Fill notification in Telegram | ORD-03 | Requires live bot | Check Telegram for fill price message |
| Close notification on SL/TP hit | MON-02 | Requires live position close | Wait for SL/TP to trigger, verify Telegram notification |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
