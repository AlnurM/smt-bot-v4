---
phase: 07-integration-wiring-fix
plan: "02"
subsystem: risk, monitor, executor, telegram
tags: [wiring, risk, daily-loss, liquidation-safety, position-monitor, order-executor, help-text]
dependency_graph:
  requires: [07-01]
  provides: [starting_balance-population, check_and_warn_daily_loss-call-site, validate_liquidation_safety-call-site, dryrun-in-help]
  affects: [bot/monitor/position.py, bot/order/executor.py, bot/telegram/handlers/commands.py]
tech_stack:
  added: []
  patterns: [pg_insert ON CONFLICT INSERT-only fields, liquidation-gate-before-MARKET-order, TDD fixture extension]
key_files:
  modified:
    - bot/monitor/position.py
    - bot/order/executor.py
    - bot/telegram/handlers/commands.py
    - tests/test_position_monitor.py
    - tests/test_order_executor.py
decisions:
  - "Reuse risk row fetched for TG-20 check in step 3d — avoids duplicate SELECT RiskSettings in same session"
  - "futures_account() called before the session block in _handle_position_close — balance available for both INSERT and warn call"
  - "validate_liquidation_safety added to top-level import in executor.py (not local import inside function)"
metrics:
  duration_minutes: 11
  completed_date: "2026-03-20"
  tasks_completed: 3
  files_modified: 5
---

# Phase 07 Plan 02: Integration Wiring Fix — DailyStats, Loss Warning, Liquidation Gate, /help Summary

Closed four integration gaps: DailyStats.starting_balance fetched from Binance on INSERT, check_and_warn_daily_loss wired after every position close, validate_liquidation_safety gating MARKET orders before placement, and /dryrun listed in /help.

## Tasks Completed

| # | Name | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Fix DailyStats.starting_balance + wire check_and_warn_daily_loss | 0e2830c | bot/monitor/position.py |
| 2 | Wire validate_liquidation_safety + fix /help text | ce2c9fa | bot/order/executor.py, bot/telegram/handlers/commands.py |
| 3 | Add tests for starting_balance, 80% warning, liquidation safety gate | b74b978 | tests/test_position_monitor.py, tests/test_order_executor.py |

## Changes Made

### bot/monitor/position.py

- Added `futures_account()` call before session block to fetch `day_starting_balance`
- Added `starting_balance=day_starting_balance` to `pg_insert(DailyStats).values(...)` — INSERT path only
- `starting_balance` deliberately absent from `on_conflict_do_update set_={}` — first-trade-of-day value preserved on subsequent closes
- Added `check_and_warn_daily_loss(...)` call after win_rate assignment, before `session.commit()` (TG-20)
- Reused the `risk` row fetched for TG-20 in step 3d — removed duplicate `SELECT RiskSettings`

### bot/order/executor.py

- Added `validate_liquidation_safety` to top-level import from `bot.risk.manager`
- Inserted Step 11b between MIN_NOTIONAL check (Step 11) and rounding (Step 12)
- Rejection path: sends `send_error_alert` + marks `signal.status = "failed"` + returns early (RISK-08)

### bot/telegram/handlers/commands.py

- Added `/dryrun [on|off] — Режим тестирования без реальных ордеров` line to `cmd_help` text (TG-18)

### tests/test_position_monitor.py

- Fixed `make_daily_stats()` fixture to include `starting_balance=None` field (Rule 1 auto-fix)
- Fixed `make_risk_settings()` fixture to include `daily_loss_limit_pct=5.0` field (Rule 1 auto-fix)
- Added `test_starting_balance_set_on_daily_stats` — verifies `futures_account()` called
- Added `test_80pct_warning_called_after_close` — verifies `check_and_warn_daily_loss` called once

### tests/test_order_executor.py

- Added `test_liquidation_safety_blocks_order` — verifies no MARKET order + error alert when liq check returns (False, 48000.0)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] make_daily_stats() fixture missing starting_balance attribute**
- **Found during:** Task 3 (running existing tests)
- **Issue:** `test_close_notification` and other tests failed with `AttributeError: 'types.SimpleNamespace' object has no attribute 'starting_balance'` because `_handle_position_close` now accesses `stats_row.starting_balance` but the test fixture did not include this field
- **Fix:** Added `starting_balance=None` to `make_daily_stats()` in `tests/test_position_monitor.py`
- **Files modified:** tests/test_position_monitor.py
- **Commit:** b74b978

**2. [Rule 1 - Bug] make_risk_settings() fixture missing daily_loss_limit_pct attribute**
- **Found during:** Task 3 (running existing tests)
- **Issue:** `test_close_notification` failed with `AttributeError: 'types.SimpleNamespace' object has no attribute 'daily_loss_limit_pct'` because the new TG-20 code path accesses `risk.daily_loss_limit_pct` but the fixture lacked this field
- **Fix:** Added `daily_loss_limit_pct=5.0` to `make_risk_settings()` in `tests/test_position_monitor.py`
- **Files modified:** tests/test_position_monitor.py
- **Commit:** b74b978

**3. [Rule 1 - Bug] Duplicate SELECT RiskSettings in _handle_position_close**
- **Found during:** Task 1 implementation
- **Issue:** Adding TG-20 risk check inside the session block introduced a `SELECT RiskSettings` that duplicated the query already present in step 3d
- **Fix:** Removed the step 3d standalone `SELECT RiskSettings` query and reused the `risk` variable fetched for TG-20
- **Files modified:** bot/monitor/position.py
- **Commit:** 0e2830c

## Test Results

```
tests/test_position_monitor.py::test_pnl_update PASSED
tests/test_position_monitor.py::test_close_notification PASSED
tests/test_position_monitor.py::test_trade_record_created PASSED
tests/test_position_monitor.py::test_win_streak_update PASSED
tests/test_position_monitor.py::test_daily_stats_update PASSED
tests/test_position_monitor.py::test_starting_balance_set_on_daily_stats PASSED
tests/test_position_monitor.py::test_80pct_warning_called_after_close PASSED
tests/test_order_executor.py::test_dry_run_mode PASSED
tests/test_order_executor.py::test_double_tap_protection PASSED
tests/test_order_executor.py::test_market_order_placed PASSED
tests/test_order_executor.py::test_bracket_orders_placed PASSED
tests/test_order_executor.py::test_confirmation_notification PASSED
tests/test_order_executor.py::test_error_handling PASSED
tests/test_order_executor.py::test_double_tap_protection_is_none PASSED
tests/test_order_executor.py::test_liquidation_safety_blocks_order PASSED
15 passed
```

## Self-Check: PASSED

- bot/monitor/position.py: FOUND
- bot/order/executor.py: FOUND
- bot/telegram/handlers/commands.py: FOUND
- 07-02-SUMMARY.md: FOUND
- Commit 0e2830c: FOUND
- Commit ce2c9fa: FOUND
- Commit b74b978: FOUND
