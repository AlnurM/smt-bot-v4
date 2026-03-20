---
phase: 07-integration-wiring-fix
plan: "01"
subsystem: database
tags: [sqlalchemy, postgresql, asyncpg, signal, dispatch, risk]

# Dependency graph
requires:
  - phase: 04-telegram-interface
    provides: send_signal_message dispatch module with signal["id"] callback_data
  - phase: 03-signal-and-risk
    provides: check_rr_ratio pure function in bot/risk/manager.py
  - phase: 01-foundation
    provides: Signal ORM model with gen_random_uuid() server default

provides:
  - Signal ORM row inserted with session.flush() before send_signal_message — real UUID available for callback routing
  - R/R ratio gate wired: signals below min_rr_ratio silently filtered before DB insert
  - session.rollback() on bot-paused path — no orphan pending Signal rows committed
  - schedule_signal_expiry receives real signal UUID instead of placeholder "00000000-..."
  - 2 new integration tests covering Signal row creation and R/R filter behavior

affects: [05-order-execution-and-position-monitoring, 04-telegram-interface]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Insert-flush-then-dispatch: ORM row inserted and flushed for UUID before any side effects
    - Rollback on paused path: session.rollback() protects against uncommitted orphan rows

key-files:
  created: []
  modified:
    - bot/strategy/manager.py
    - tests/test_strategy_manager.py

key-decisions:
  - "session.flush() (not session.commit()) used before dispatch — gives UUID while keeping row in same transaction, allows rollback if bot is paused"
  - "R/R filter placed before ORM insert — no DB write for signals that don't meet threshold, no rollback needed"
  - "check_rr_ratio imported at the bot-present block, not at module top — consistent with existing lazy import pattern in run_strategy_scan"
  - "continue used (not return) on R/R filter failure — processing continues to next candidate coin in the loop"

patterns-established:
  - "Insert-before-dispatch: always flush ORM row before calling Telegram, set signal['id'] = str(row.id) for callback routing"
  - "Paused-bot rollback: send_signal_message returns -1 when paused; session.rollback() prevents orphan pending rows"

requirements-completed:
  - SIG-01
  - SIG-02
  - SIG-03
  - SIG-04
  - SIG-05
  - SIG-06
  - TG-03
  - TG-04
  - ORD-01
  - ORD-02
  - ORD-03
  - ORD-04
  - ORD-05
  - MON-01
  - MON-02
  - MON-03
  - MON-04
  - MON-05
  - RISK-03

# Metrics
duration: 2min
completed: 2026-03-20
---

# Phase 7 Plan 01: Integration Wiring Fix Summary

**Signal ORM insert-flush-then-dispatch pattern with R/R filter gate, unblocking the full Confirm -> Order -> Monitor flow that was unreachable due to placeholder UUID "00000000-..."**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-20T09:07:24Z
- **Completed:** 2026-03-20T09:09:40Z
- **Tasks:** 2 (TDD: RED + GREEN each)
- **Files modified:** 2

## Accomplishments

- Removed fragile post-hoc `select(SignalModel).order_by(created_at.desc()).limit(1)` query — all Confirm/Reject/Pine callbacks now receive a real DB UUID
- Wired `check_rr_ratio()` from `bot/risk/manager.py` before Signal insert — RISK-03 requirement finally exercised at runtime
- Added `session.rollback()` for bot-paused branch — no orphan `pending` Signal rows accumulate when bot is paused
- Two new integration tests (TDD): `test_signal_row_created_in_db` and `test_rr_filter_blocks_low_ratio` — all 10 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for Signal row creation and R/R filter** - `d5aa0e7` (test)
2. **Task 1 GREEN: Insert Signal ORM row before dispatch + wire R/R filter** - `f2f171a` (feat)

_Note: TDD tasks have RED (test) then GREEN (feat) commits_

## Files Created/Modified

- `bot/strategy/manager.py` - Replaced broken post-hoc signal query with insert-flush-dispatch pattern; added R/R filter gate and rollback on paused path
- `tests/test_strategy_manager.py` - Added `test_signal_row_created_in_db` and `test_rr_filter_blocks_low_ratio` integration tests

## Decisions Made

- `session.flush()` not `session.commit()` before dispatch: gives real UUID while keeping row in same transaction, enabling clean rollback if bot is paused
- R/R filter placed before ORM insert: no DB write for filtered signals, no rollback overhead
- `continue` not `return` on R/R filter: loop proceeds to next candidate coin rather than aborting entire scan
- Lazy import of `check_rr_ratio` inside the `if bot is not None:` block: consistent with existing import style in `run_strategy_scan`

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The full Confirm -> Order Execution -> Position Monitoring flow is now reachable: `signal["id"]` is always a real DB UUID when `send_signal_message` is called
- `schedule_signal_expiry` receives the real signal UUID so expiry job can find the correct Signal row
- All 19 requirements listed in this plan's frontmatter are unblocked — Confirm/Reject callbacks can now do `select(Signal).where(Signal.id == uuid.UUID(signal_id))` and find the row

---
*Phase: 07-integration-wiring-fix*
*Completed: 2026-03-20*
