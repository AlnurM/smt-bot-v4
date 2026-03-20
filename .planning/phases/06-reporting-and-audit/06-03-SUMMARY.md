---
phase: 06-reporting-and-audit
plan: 03
subsystem: telegram
tags: [aiogram, callback_data, inline_keyboard, strategy_criteria, skipped_coins]

# Dependency graph
requires:
  - phase: 06-02
    provides: Pine Script generation and reporting infrastructure
  - phase: 04-telegram-interface
    provides: callback handler pattern (callback.answer first, session_factory kwargs)
provides:
  - LoosenCriteria CallbackData class (prefix "lc") in bot/telegram/callbacks.py
  - send_skipped_coins_alert with InlineKeyboardMarkup loosen buttons
  - handle_loosen_criteria handler updating StrategyCriteria in DB
  - Enhanced cmd_skipped with compact + drill-down display modes
affects:
  - bot/telegram/handlers/callbacks.py (router registration)
  - bot/strategy/manager.py (caller of send_skipped_coins_alert)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - LoosenCriteria(CallbackData, prefix="lc") follows SignalAction pattern
    - Lazy imports inside async function body for circular-import safety (notifications.py)
    - _LOOSEN_RULES dict with lambda adjustments + floor clamping per criterion

key-files:
  created: []
  modified:
    - bot/telegram/callbacks.py
    - bot/telegram/notifications.py
    - bot/telegram/handlers/callbacks.py
    - bot/telegram/handlers/commands.py

key-decisions:
  - "LoosenCriteria prefix 'lc' + field name fits well within 64-byte Telegram callback_data limit"
  - "Lazy imports of InlineKeyboardBuilder and LoosenCriteria inside send_skipped_coins_alert body to avoid circular import at module level"
  - "send_skipped_coins_alert throttle logic moved inline (no longer delegates to send_error_alert) because keyboard markup requires direct bot.send_message call"
  - "noop field value on LoosenCriteria removes keyboard without DB write — avoids phantom updates"
  - "cmd_skipped 'week' keyword arg takes precedence over time-format args; symbol arg always triggers drill-down regardless of case"
  - "_LOOSEN_RULES uses floor values per criterion (50% floor on return, 30% on win rate, 1.0 on profit factor and avg rr, min 5 on trades)"

patterns-established:
  - "LoosenCriteria pattern: CallbackData subclass with single field: str for DB column routing"
  - "Loosen button flow: alert fires → user taps button → handler updates single StrategyCriteria column → removes keyboard → confirms to user"

requirements-completed: [SKIP-01, SKIP-02, SKIP-03, SKIP-04]

# Metrics
duration: 3min
completed: 2026-03-20
---

# Phase 6 Plan 03: Skipped Coins — Loosen Buttons and Enhanced Drill-down Summary

**LoosenCriteria inline keyboard on consecutive-skip alerts with StrategyCriteria DB update, plus cmd_skipped compact list and symbol drill-down with backtest details**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-20T08:10:39Z
- **Completed:** 2026-03-20T08:13:51Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- LoosenCriteria CallbackData class (prefix "lc", single `field` str) added to callbacks.py
- send_skipped_coins_alert rewritten with InlineKeyboardBuilder showing top-3 most-failed criteria buttons sorted by frequency; falls back to default 3 fields when no counts provided
- handle_loosen_criteria callback handler with _LOOSEN_RULES dict covering all 6 StrategyCriteria numeric fields; noop field removes keyboard without DB write
- cmd_skipped enhanced with "week" keyword arg, Nh/Nd time args, and symbol drill-down showing per-entry backtest_results (return, drawdown, WR, PF, trade count)

## Task Commits

Each task was committed atomically:

1. **Task 1: LoosenCriteria callback + send_skipped_coins_alert with loosen buttons** - `84d631c` (feat)
2. **Task 2: handle_loosen_criteria callback + enhanced cmd_skipped** - `d26b7f4` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified
- `bot/telegram/callbacks.py` - Added LoosenCriteria(CallbackData, prefix="lc") after SignalAction
- `bot/telegram/notifications.py` - Rewrote send_skipped_coins_alert with inline keyboard and throttle logic inlined
- `bot/telegram/handlers/callbacks.py` - Added StrategyCriteria import, LoosenCriteria import, _LOOSEN_RULES dict, handle_loosen_criteria handler
- `bot/telegram/handlers/commands.py` - Replaced cmd_skipped with compact list + drill-down + "week" arg support

## Decisions Made
- Lazy imports of InlineKeyboardBuilder and LoosenCriteria inside send_skipped_coins_alert body to avoid circular imports at module load time
- Throttle check moved inline (no longer delegating to send_error_alert) because keyboard markup requires direct bot.send_message rather than the plain-text send_error_alert helper
- noop field value removes keyboard via edit_reply_markup(None) without touching DB — clean UX for "continue waiting"
- _LOOSEN_RULES floors: min_total_return_pct floor 50%, min_win_rate_pct floor 30%, min_profit_factor floor 1.0, min_avg_rr floor 1.0, min_trades floor 5

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All SKIP-01 through SKIP-04 requirements complete
- Phase 6 (reporting and audit) is now fully complete
- Callers of send_skipped_coins_alert in bot/strategy/manager.py can optionally pass failed_criteria_counts dict to show most-relevant loosen buttons

---
*Phase: 06-reporting-and-audit*
*Completed: 2026-03-20*

## Self-Check: PASSED

- FOUND: bot/telegram/callbacks.py
- FOUND: bot/telegram/notifications.py
- FOUND: bot/telegram/handlers/callbacks.py
- FOUND: bot/telegram/handlers/commands.py
- FOUND: commit 84d631c
- FOUND: commit d26b7f4
