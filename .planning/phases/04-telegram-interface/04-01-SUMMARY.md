---
phase: 04-telegram-interface
plan: "01"
subsystem: telegram
tags: [aiogram, telegram, middleware, notifications, commands, alembic, sqlalchemy]

# Dependency graph
requires:
  - phase: 03-signal-and-risk
    provides: Signal model, generate_signal, generate_chart, calculate_position_size, RiskSettings ORM
  - phase: 02-strategy-pipeline
    provides: run_strategy_scan, Strategy ORM, SkippedCoin ORM
  - phase: 01-foundation
    provides: main.py entrypoint, DB session, Settings, Bot/Dispatcher scaffold
provides:
  - AllowedChatMiddleware blocking non-allowed chat_ids (TG-01)
  - SignalAction CallbackData factory with prefix="sig" (TG-03 prep)
  - send_error_alert with 15-min per-key throttle (TG-21)
  - check_and_warn_daily_loss firing at 80% of limit (TG-20)
  - send_skipped_coins_alert at consecutive threshold (TG-22)
  - 13 Telegram command handlers: /start /status /signals /positions /history /strategies /skipped /scan /chart /pause /resume /help /help
  - _bot_state module-level dict for pause/resume (used by Plan 02 dispatch)
  - Alembic migration 0002 adding telegram_message_id + caption to signals table
  - main.py wired with middleware, router, workflow_data (bot, session_factory, scheduler, binance_client, settings)
  - run_strategy_scan accepting bot=None, scheduler=None with notification + dispatch wiring
affects:
  - 04-02 (signal dispatch — imports SignalAction, _bot_state, send_signal_message)
  - 04-03 (order executor — uses confirmed signal flow)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pytest.importorskip at module level for RED-state test stubs — entire file skips until production module exists"
    - "_bot_state module-level dict pattern for pause/resume state shared between handlers and dispatch"
    - "AllowedChatMiddleware wraps entire dp.update — single choke point for security, no handler-level checks needed"
    - "send_error_alert throttle: in-memory _last_alert dict keyed by error_key, TTL=15min"
    - "Lazy imports of bot.telegram.dispatch inside run_strategy_scan — avoids circular imports at module load time"

key-files:
  created:
    - bot/telegram/__init__.py
    - bot/telegram/middleware.py
    - bot/telegram/callbacks.py
    - bot/telegram/notifications.py
    - bot/telegram/handlers/__init__.py
    - bot/telegram/handlers/commands.py
    - alembic/versions/0002_add_signal_telegram_fields.py
    - tests/test_telegram_middleware.py
    - tests/test_telegram_notifications.py
    - tests/test_telegram_commands.py
  modified:
    - bot/db/models.py
    - bot/strategy/manager.py
    - bot/main.py

key-decisions:
  - "_bot_state module-level dict in commands.py shared between handlers and Plan 02 dispatch — avoids Dispatcher workflow_data mutation complexity"
  - "Lazy imports of bot.telegram.dispatch and bot.signals.generator inside run_strategy_scan guard — prevents circular imports and allows phased deployment"
  - "AllowedChatMiddleware registered on dp.update (not message/callback separately) — covers all update types with single registration"
  - "send_error_alert throttle uses in-memory dict — sufficient for single-process bot, resets on restart (acceptable for alert deduplication)"
  - "Signal dispatch block gated on bot is not None — safe stub pattern, no-op until Plan 02 creates dispatch.py"

patterns-established:
  - "Pattern: AllowedChatMiddleware on dp.update drops all non-allowed updates before any handler fires"
  - "Pattern: _bot_state shared dict exports pause state to dispatch module"
  - "Pattern: Lazy import guards for Phase 4 inter-module dependencies"

requirements-completed:
  - TG-01
  - TG-05
  - TG-06
  - TG-09
  - TG-10
  - TG-11
  - TG-12
  - TG-13
  - TG-14
  - TG-15
  - TG-17
  - TG-18
  - TG-20
  - TG-21
  - TG-22

# Metrics
duration: 7min
completed: 2026-03-19
---

# Phase 4 Plan 01: Telegram Interface Skeleton Summary

**aiogram AllowedChatMiddleware, 13 command handlers, throttled notification helpers, Alembic migration 0002, and main.py wired with middleware + router + workflow_data**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-19T19:10:36Z
- **Completed:** 2026-03-19T19:17:52Z
- **Tasks:** 3
- **Files modified:** 13

## Accomplishments

- Alembic migration 0002 adds `telegram_message_id` and `caption` columns to signals table; Signal ORM model updated
- AllowedChatMiddleware (TG-01) blocks all non-ALLOWED_CHAT_ID updates before any handler fires
- SignalAction CallbackData with prefix="sig" ready for Plan 02 inline buttons
- send_error_alert with 15-min per-key throttle; check_and_warn_daily_loss at 80% threshold; send_skipped_coins_alert at consecutive threshold
- 13 command handlers on router (/start /status /signals /positions /history /strategies /skipped /scan /chart /pause /resume /help) with _bot_state for pause/resume
- main.py wired: AllowedChatMiddleware, commands_router, dp["bot"/"session_factory"/"scheduler"/"binance_client"/"settings"]
- run_strategy_scan updated with bot=None, scheduler=None, notification hooks, and signal dispatch stub (guarded import of Plan 02 dispatch module)
- All 13 tests pass (3 test files, TDD red-then-green)

## Task Commits

Each task was committed atomically:

1. **Task 1: Wave 0 — DB migration + test scaffolds** - `2d720ea` (test)
2. **Task 2: AllowedChatMiddleware + SignalAction + notifications** - `5d33703` (feat)
3. **Task 3: Command handlers + main.py wiring** - `d9c946a` (feat)

## Files Created/Modified

- `alembic/versions/0002_add_signal_telegram_fields.py` — Alembic migration adding telegram_message_id + caption
- `bot/db/models.py` — Signal model updated with telegram_message_id and caption columns
- `bot/telegram/__init__.py` — Package marker
- `bot/telegram/middleware.py` — AllowedChatMiddleware (TG-01)
- `bot/telegram/callbacks.py` — SignalAction CallbackData (prefix="sig")
- `bot/telegram/notifications.py` — send_error_alert, check_and_warn_daily_loss, send_skipped_coins_alert
- `bot/telegram/handlers/__init__.py` — Package marker
- `bot/telegram/handlers/commands.py` — 13 command handlers, router, _bot_state
- `bot/main.py` — Wired middleware + router + workflow_data; updated APScheduler job
- `bot/strategy/manager.py` — Added bot=None, scheduler=None; wired notification alerts + signal dispatch stub
- `tests/test_telegram_middleware.py` — 3 middleware test stubs (GREEN)
- `tests/test_telegram_notifications.py` — 5 notification test stubs (GREEN)
- `tests/test_telegram_commands.py` — 5 command test stubs (GREEN)

## Decisions Made

- `_bot_state` module-level dict in `commands.py` shared with Plan 02 dispatch avoids Dispatcher workflow_data mutation complexity
- `AllowedChatMiddleware` registered on `dp.update` (not message/callback separately) — single registration covers all update types
- `send_error_alert` throttle uses in-memory dict — sufficient for single-process bot; resets on restart (acceptable)
- Signal dispatch block inside `run_strategy_scan` uses guarded lazy imports (`if bot is not None`) — safe no-op stub until Plan 02 creates `dispatch.py`
- Lazy imports of `bot.telegram.dispatch`, `bot.signals.generator` inside strategy manager — prevents circular imports at module load time

## Deviations from Plan

None — plan executed exactly as written. The signal dispatch block in `run_strategy_scan` used proper SQLAlchemy `select()` syntax (cleaned up vs plan's pseudocode with `__import__` anti-pattern).

## Issues Encountered

None — all three test files went GREEN on first run after production module creation.

## Next Phase Readiness

- Plan 02 can now import `SignalAction` from `bot/telegram/callbacks.py` for inline keyboard buttons
- Plan 02 can import `_bot_state` from `bot/telegram/handlers/commands.py` to check pause state
- Plan 02 must create `bot/telegram/dispatch.py` with `send_signal_message` and `schedule_signal_expiry` — the calling convention is already wired in `run_strategy_scan`
- All notification helpers are available for use by Plan 02 dispatch module
- DB migration 0002 must be run (`alembic upgrade head`) before the next deployment

---
*Phase: 04-telegram-interface*
*Completed: 2026-03-19*
