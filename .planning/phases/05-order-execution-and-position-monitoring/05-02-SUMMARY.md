---
phase: 05-order-execution-and-position-monitoring
plan: "02"
subsystem: monitor, scheduler, database
tags: [apscheduler, position-monitor, binance-futures, daily-stats, win-streak, trade-record]

# Dependency graph
requires:
  - phase: 05-order-execution-and-position-monitoring
    plan: "00"
    provides: Position ORM with sl_order_id/tp_order_id/is_dry_run; RED test stubs MON-01..05
  - phase: 05-order-execution-and-position-monitoring
    plan: "01"
    provides: execute_order creating Position rows with sl/tp order IDs; IntervalTrigger import in main.py

provides:
  - monitor_positions() APScheduler IntervalTrigger job at 60-second interval
  - _handle_position_close() — cancel bracket, fetch PnL, write Trade+DailyStats+RiskSettings
  - _update_unrealized_pnl() — update open position PnL from futures_position_information
  - position_monitor job registered in main.py

affects:
  - bot/main.py (job registration)
  - bot/db/models.py (Position closed, Trade inserted, DailyStats upserted, RiskSettings updated)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - pg_insert ON CONFLICT DO UPDATE for atomic DailyStats increment
    - Sequential position processing (not asyncio.gather) prevents win streak race condition
    - BinanceAPIException.code -2011 suppressed on surviving bracket cancel
    - BinanceAPIException.code -2013 marks position 'orphaned', no Telegram alert
    - futures_account_trades filtered by orderId for accurate post-fee realized PnL

key-files:
  created:
    - bot/monitor/__init__.py
    - bot/monitor/position.py
  modified:
    - tests/test_position_monitor.py
    - bot/main.py

key-decisions:
  - "Sequential position loop in monitor_positions (not asyncio.gather) — prevents win_streak_current race condition when two positions close in same cycle (Pitfall 8)"
  - "futures_account_trades filtered by t['orderId'] == int(filled_order_id) — uses Binance-computed PnL including fees, not manual arithmetic"
  - "DailyStats upsert uses pg_insert ON CONFLICT DO UPDATE with incremental set_ expressions — atomic, avoids read-then-write race condition"
  - "ORDER_DOES_NOT_EXIST (-2013) marks position 'orphaned' with no Telegram alert — testnet wipe scenario, not a trader-facing error"
  - "win_rate recomputed inline after upsert (win_count/trade_count) — kept in sync atomically within the same session"

# Metrics
duration: 5min
completed: 2026-03-20
---

# Phase 5 Plan 02: Position Monitor — Summary

**60-second APScheduler polling job that detects SL/TP fills on open Binance Futures positions, cancels surviving bracket order, creates Trade records with Binance-reported realized PnL, updates win streak + daily stats, and sends Telegram close notifications.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-20T07:19:49Z
- **Completed:** 2026-03-20T07:24:18Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Implemented `bot/monitor/position.py` with `monitor_positions()`, `_handle_position_close()`, and `_update_unrealized_pnl()`
- All 5 MON tests pass (MON-01..05): pnl_update, close_notification, trade_record_created, win_streak_update, daily_stats_update
- Registered `position_monitor` APScheduler job in `main.py` with `IntervalTrigger(seconds=60)`
- Full test suite green: 134 passed (excluding DB-dependent integration tests that require a running PostgreSQL)

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Full test implementations** - `9654f96` (test)
2. **Task 1 GREEN: bot/monitor/position.py + __init__.py** - `9f22061` (feat)
3. **Task 2: Register job in main.py** - `d311bc2` (feat)

## Files Created/Modified

- `bot/monitor/__init__.py` — empty package marker
- `bot/monitor/position.py` — full position monitor implementation (170 lines)
- `tests/test_position_monitor.py` — 5 complete test implementations replacing RED stubs
- `bot/main.py` — import + IntervalTrigger job registration for position_monitor

## Decisions Made

- Sequential position loop (not asyncio.gather) prevents win_streak_current race condition when two positions close in same 60-second cycle
- `futures_account_trades` filtered by `orderId` for Binance-reported realized PnL including fees — manual arithmetic would miss funding rates
- `pg_insert ON CONFLICT DO UPDATE` with incremental `set_` expressions for DailyStats — atomic, no read-then-write race
- `-2013 ORDER_DOES_NOT_EXIST` marks position as `orphaned` with no Telegram alert — testnet wipe is expected, not an alert condition
- `win_rate` recomputed inline after upsert within the same session — kept in sync atomically

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Full trade loop is now complete: signal detected → Telegram confirm → order executed → position monitored → closed on SL/TP → Trade record + stats updated
- `test_migrations.py` and `test_scanner.py` failures are pre-existing (require running PostgreSQL / network — not regressions)

## Self-Check: PASSED

- `bot/monitor/__init__.py` exists: FOUND
- `bot/monitor/position.py` exists: FOUND (exports monitor_positions, _handle_position_close, _update_unrealized_pnl)
- All 5 MON tests pass: VERIFIED (5 passed, 0.33s)
- `position_monitor` registered in main.py: VERIFIED (line 205)
- Commits verified: 9654f96, 9f22061, d311bc2 in git log

---
*Phase: 05-order-execution-and-position-monitoring*
*Completed: 2026-03-20*
