---
phase: 04-telegram-interface
plan: "02"
subsystem: telegram
tags: [aiogram, apscheduler, sqlalchemy, select-for-update, inline-keyboard, dispatch, callbacks]

# Dependency graph
requires:
  - phase: 04-01
    provides: SignalAction CallbackData factory, AllowedChatMiddleware, _bot_state, telegram_message_id/caption DB columns
  - phase: 03-signal-and-risk
    provides: generate_signal() return shape, calculate_position_size() return shape, generate_chart() bytes

provides:
  - "send_signal_message(): sends photo+caption+keyboard; returns message_id"
  - "schedule_signal_expiry(): APScheduler DateTrigger job to auto-expire signals"
  - "expire_signal_job(): async job that marks signal expired and edits Telegram message"
  - "handle_confirm: SELECT FOR UPDATE idempotent confirm with double-tap protection"
  - "handle_reject: SELECT FOR UPDATE idempotent reject with message edit"
  - "handle_pine: Phase 6 placeholder Pine Script response"
  - "callbacks_router wired into main.py Dispatcher"

affects:
  - "05-trade-execution (dispatch.send_signal_message called from strategy manager after signal DB insert)"
  - "phase 6 (handle_pine will be expanded with real Pine Script generation)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "callback.answer() called FIRST in every handler (Telegram 60s deadline)"
    - "SELECT ... WITH FOR UPDATE for idempotent double-tap protection on confirm/reject"
    - "Each handler opens its own session (no session sharing across handlers)"
    - "APScheduler DateTrigger with id=expire_{signal_id} + replace_existing=True (idempotent registration)"
    - "Bot-paused guard in dispatch: check _bot_state['paused'] before sending any signal"
    - "Caption truncated at 1020 chars + '...' to stay under Telegram 1024-char limit"
    - "MIN_NOTIONAL omits Confirm button (2-button keyboard instead of 3)"

key-files:
  created:
    - "bot/telegram/dispatch.py"
    - "bot/telegram/handlers/callbacks.py"
    - "tests/test_telegram_dispatch.py"
    - "tests/test_telegram_callbacks.py"
  modified:
    - "bot/main.py (callbacks_router import + dp.include_router)"

key-decisions:
  - "Caption truncation at 1020 (not 1024) chars — leaves 4-char buffer for safety"
  - "expire_signal_job uses direct select (no FOR UPDATE) — expiry is one-writer scenario via scheduler job id uniqueness"
  - "handle_pine uses callback.message.answer() (new message) not edit_caption — placeholder doesn't modify signal display"
  - "builder.adjust(2, 1) for normal signals (Confirm+Reject on row 1, Pine on row 2); (1, 1) for MIN_NOTIONAL"
  - "session_factory injected via **kwargs from Dispatcher workflow_data — consistent with command handler pattern"

patterns-established:
  - "Pattern: TDD RED (importorskip scaffold) -> GREEN (production module) for each feature module"
  - "Pattern: callback handlers answer() first, then open session, then do DB work"
  - "Pattern: SELECT FOR UPDATE + status == 'pending' filter = atomic idempotency for user actions"

requirements-completed: [TG-02, TG-03, TG-04]

# Metrics
duration: 5min
completed: 2026-03-20
---

# Phase 4 Plan 02: Signal Dispatch and Callback Handlers Summary

**Aiogram dispatch module sends photo+caption+3-button inline keyboard to Telegram with APScheduler signal expiry, and callback handlers (Confirm/Reject/Pine) use SELECT FOR UPDATE for double-tap idempotency.**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-20T00:20:40Z
- **Completed:** 2026-03-20T00:25:35Z
- **Tasks:** 3 (TDD RED + GREEN x2)
- **Files modified:** 5

## Accomplishments
- `bot/telegram/dispatch.py`: `send_signal_message()` sends photo+caption+keyboard; `schedule_signal_expiry()` registers APScheduler DateTrigger; `expire_signal_job()` marks pending signals expired and edits Telegram message
- `bot/telegram/handlers/callbacks.py`: three inline-button handlers (Confirm, Reject, Pine) with atomic SELECT FOR UPDATE idempotency and double-tap protection
- `bot/main.py`: `callbacks_router` wired into Dispatcher; all 5 Telegram test files pass (23 tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 test scaffolds** - `21ba900` (test)
2. **Task 2: Signal dispatch module** - `5b44246` (feat)
3. **Task 3: Callback handlers + main.py wiring** - `e935c96` (feat)

_Note: TDD tasks have separate test (RED) and feat (GREEN) commits_

## Files Created/Modified
- `bot/telegram/dispatch.py` - Signal dispatch: send photo, format caption, schedule/execute expiry
- `bot/telegram/handlers/callbacks.py` - Confirm/Reject/Pine callback handlers with FOR UPDATE idempotency
- `bot/main.py` - Added callbacks_router import and dp.include_router(callbacks_router)
- `tests/test_telegram_dispatch.py` - 6 tests: send_photo, caption truncation, button counts, expiry scheduling/execution
- `tests/test_telegram_callbacks.py` - 4 tests: confirm, double-tap noop, reject, pine placeholder

## Decisions Made
- Caption truncated at 1020 chars (not 1024) to leave a 4-char safety buffer
- `expire_signal_job` uses plain select (no FOR UPDATE) — scheduler job ID uniqueness (`expire_{signal_id}`) is sufficient concurrency control for the single-writer expiry path
- `handle_pine` sends a new message via `callback.message.answer()` rather than editing the signal message — placeholder behavior that won't interfere with the signal display
- `builder.adjust(2, 1)` for normal signals (Confirm+Reject on row 1, Pine on row 2); `(1, 1)` for MIN_NOTIONAL (2-button keyboard, no Confirm)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. The `bot/main.py` had already been modified by plan 04-03 (settings router) when this plan ran, so the callbacks_router addition merged cleanly with both routers present.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Signal dispatch pipeline is complete: `run_strategy_scan` in Phase 5 can call `send_signal_message()` after DB INSERT
- `callbacks_router` is registered and session_factory is injected via Dispatcher workflow_data
- Signal expiry via APScheduler is operational; caller must provide `scheduler` instance and `session_factory`
- Pine Script handler is a stub — Phase 6 implements the real chart generation

---
*Phase: 04-telegram-interface*
*Completed: 2026-03-20*
