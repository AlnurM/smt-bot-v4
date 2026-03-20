---
phase: 05-order-execution-and-position-monitoring
plan: "01"
subsystem: order-execution, telegram
tags: [binance-futures, order-executor, dry-run, bracket-orders, tdd]

# Dependency graph
requires:
  - phase: 05-order-execution-and-position-monitoring
    plan: "00"
    provides: DB migration 0004, ORM updates, RED test scaffolds, mock fixtures

provides:
  - execute_order() with full 19-step MARKET + bracket SL/TP placement
  - _exchange_info_cache module-level dict (lazy per-symbol cache)
  - _set_isolated_margin() with -4046 silent handling
  - _set_leverage()
  - _get_symbol_filters() with cache
  - _handle_order_error() with Russian error messages
  - get_error_message() mapping BINANCE_ERROR_MESSAGES
  - handle_confirm wired to asyncio.create_task(execute_order(...))
  - /dryrun on|off command with _bot_state["dry_run"] toggle
  - IntervalTrigger import in main.py (ready for Plan 02)

affects:
  - 05-02-position-monitor (receives execute_order Position rows with sl_order_id/tp_order_id)
  - bot/telegram/handlers/callbacks.py (handle_confirm now fires order execution)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Lazy import of _bot_state inside execute_order() to avoid circular import
    - asyncio.create_task() from handle_confirm after session.commit() — non-blocking
    - Module-level _exchange_info_cache dict populated on first order per symbol
    - _set_isolated_margin() catches BinanceAPIException code -4046, re-raises all others
    - closePosition=True + workingType=MARK_PRICE + priceProtect=True on bracket orders
    - SL-would-trigger guard: fill price validated vs SL price after MARKET fill
    - send_error_alert() used for all BinanceAPIException paths (15-min throttle from Phase 4)

key-files:
  created:
    - bot/order/__init__.py
    - bot/order/executor.py
  modified:
    - tests/test_order_executor.py
    - bot/telegram/handlers/callbacks.py
    - bot/telegram/handlers/commands.py
    - bot/main.py

key-decisions:
  - "Lazy import of _bot_state inside execute_order() to avoid circular dependency: executor imports commands, commands imports nothing from executor"
  - "asyncio.create_task() fires execute_order from handle_confirm after commit — parallel execution, non-blocking, session already committed before task starts"
  - "_exchange_info_cache module-level dict — single process TTL sufficient for single-session bot, no expiry needed"
  - "SL-would-trigger guard uses fill_price vs sl_price (not signal.entry_price) — slippage on MARKET fill can shift entry past SL"
  - "_handle_order_error marks 'failed' for known error codes, 'error' for unknown codes — callers know the difference"

# Metrics
duration: 7min
completed: 2026-03-20
---

# Phase 5 Plan 01: Order Executor — Summary

**Implemented execute_order() (19-step MARKET entry + bracket SL/TP flow) with dry-run mode, double-tap protection, circuit breakers, and Russian-language Binance error alerts; wired asyncio.create_task trigger from handle_confirm and added /dryrun command.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-20T07:09:17Z
- **Completed:** 2026-03-20T07:16:53Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Created `bot/order/__init__.py` (package marker)
- Implemented `bot/order/executor.py` with full 19-step order flow:
  - Step 0: dry-run guard via `_bot_state["dry_run"]` (lazy import to avoid circular)
  - Step 1-2: SELECT FOR UPDATE on status='confirmed' → set 'executing' (double-tap protection)
  - Steps 3-5: Load RiskSettings, DailyStats, open Position count; check circuit breakers
  - Steps 6-12: Balance fetch, isolated margin, leverage, precision filters, position sizing
  - Step 13: MARKET entry order with BinanceAPIException → _handle_order_error
  - Step 14: Validate fill price vs SL (covers -2021 slippage scenario)
  - Steps 15-16: Create Order + Position rows in DB
  - Step 17: STOP_MARKET + TAKE_PROFIT_MARKET with closePosition=True, workingType=MARK_PRICE, priceProtect=True
  - Step 18: Update Position.sl_order_id / tp_order_id; mark signal 'filled'
  - Step 19: Send Telegram confirmation with fill price, quantity, SL, TP
- Replaced 6 RED stubs in `test_order_executor.py` with 7 passing tests (split double-tap into two)
- Updated `callbacks.py`: added `asyncio.create_task(execute_order(...))` in `handle_confirm`
- Updated `commands.py`: `_bot_state` gains `"dry_run": False`; `cmd_dryrun` handler added
- Updated `main.py`: `IntervalTrigger` imported alongside `CronTrigger`

## Task Commits

1. **Task 1: Implement bot/order/executor.py** - `6f955af` (feat)
2. **Task 2: Wire trigger, add /dryrun, import IntervalTrigger** - `9a2353c` (feat)

## Files Created/Modified

- `bot/order/__init__.py` — package marker (new)
- `bot/order/executor.py` — 19-step execute_order() + helper functions (new, 280 lines)
- `tests/test_order_executor.py` — 7 async tests covering all 6 ORD behaviors + 1 extra double-tap variant
- `bot/telegram/handlers/callbacks.py` — asyncio + execute_order imported; handle_confirm fires create_task
- `bot/telegram/handlers/commands.py` — _bot_state["dry_run"] added; cmd_dryrun handler registered
- `bot/main.py` — IntervalTrigger imported from apscheduler.triggers.interval

## Decisions Made

- Lazy import of `_bot_state` inside `execute_order()` — avoids circular: `callbacks -> executor -> commands -> (nothing from executor)`
- `asyncio.create_task()` fires after `session.commit()` — the session context is already exited, ensuring the committed status is visible to the executor's own `SELECT FOR UPDATE`
- Module-level `_exchange_info_cache` — TTL-less for single-session bot; populated on first order per symbol
- SL-would-trigger guard checks `fill_price` not `signal.entry_price` — market order slippage means fill can differ
- `_handle_order_error` distinguishes `'failed'` (known error code) from `'error'` (unknown code) for post-mortem filtering

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Added 7th test (test_double_tap_protection_is_none)**
- **Found during:** Task 1 — test file originally had one double-tap test stub
- **Issue:** The original stub `test_double_tap_protection` and `test_double_tap_protection_is_none` covered slightly different scenarios
- **Fix:** Kept both as separate tests for clarity; both pass
- **Files modified:** `tests/test_order_executor.py`

No other deviations — plan executed essentially as written.

## Issues Encountered

- `test_scanner.py::test_ohlcv_fetch_format` fails pre-existing (confirmed by git stash check before this plan's changes)
- `test_migrations.py` tests skip/error due to no running PostgreSQL (expected in unit test environment)

## Next Phase Readiness

- `bot/order/executor.py` is ready for Plan 02 (position monitor) — Position rows have `sl_order_id`, `tp_order_id`, `is_dry_run` populated
- `_bot_state["dry_run"]` is accessible from any module that imports `_bot_state`
- `IntervalTrigger` imported in `main.py` — Plan 02 can add the 60-second position monitor job

## Self-Check: PASSED
