---
phase: 06-reporting-and-audit
plan: "01"
subsystem: reporting
tags: [daily-summary, apscheduler, telegram, tg-19]
dependency_graph:
  requires: [bot.db.models, bot.exchange.client, APScheduler]
  provides: [bot.reporting.daily_summary.send_daily_summary]
  affects: [bot/main.py]
tech_stack:
  added: []
  patterns: [APScheduler CronTrigger at UTC+5, async session_factory context manager, exception containment for scheduler jobs]
key_files:
  created:
    - bot/reporting/__init__.py
    - bot/reporting/daily_summary.py
    - tests/test_daily_summary.py
  modified:
    - bot/main.py
decisions:
  - "pnl_sign_fmt uses abs(pnl) with explicit sign — avoids Python float formatting placing minus after $ sign"
  - "Etc/GMT-5 timezone used in CronTrigger (APScheduler format for UTC+5)"
  - "stake_pct falls back to 3.0 if RiskSettings row is missing — safe default"
metrics:
  duration: 3 minutes
  completed_date: "2026-03-20"
  tasks_completed: 2
  files_created: 3
  files_modified: 1
---

# Phase 06 Plan 01: Daily Summary Notification Summary

**One-liner:** 21:00 UTC+5 APScheduler CronTrigger sending Telegram daily PnL/win-rate/trade-count/balance report with best/worst trade and strategy counts.

## What Was Built

`bot/reporting/daily_summary.py` implements `send_daily_summary()` — an async coroutine that:

1. Queries `DailyStats` for today's PnL, trade count, win rate
2. Queries `Trade` table for best (max realized_pnl) and worst (min realized_pnl) trades today
3. Counts active `Strategy` rows and strategies due for review within 7 days
4. Fetches current `RiskSettings.current_stake_pct`
5. Calls `binance_client.futures_account()` for live balance
6. Composes and sends a Telegram message to `settings.allowed_chat_id`
7. Catches all exceptions — sends fallback error alert, never propagates to APScheduler

Zero-trade day produces: "Нет сделок за сегодня. Баланс: $X. Ставка: Y%"

`bot/main.py` registers the job with `CronTrigger(hour=21, minute=0, timezone="Etc/GMT-5")` and `id="daily_summary"`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement send_daily_summary() | f7d892e | bot/reporting/__init__.py, bot/reporting/daily_summary.py, tests/test_daily_summary.py |
| 2 | Register daily summary job in main.py | 20bf126 | bot/main.py |

## Verification Results

- `from bot.reporting.daily_summary import send_daily_summary` — OK
- `ast.parse(open('bot/main.py').read())` — OK (syntax valid)
- `grep -c "daily_summary" bot/main.py` — 4 (import + lambda + id= + log message)
- `grep "Etc/GMT-5" bot/main.py` — 1 match (CronTrigger timezone)
- All 6 pytest tests pass (pnl_sign_fmt, zero-trade day, trade day, exception containment)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pnl_sign_fmt sign placement**
- **Found during:** Task 1 verify step
- **Issue:** `f"{sign}${pnl:.2f}"` produced `$-3.10` for negative values because Python's `:.2f` format includes its own minus sign when `sign` is empty string
- **Fix:** Changed to `f"{sign}${abs(pnl):.2f}"` with explicit `sign = "-"` for negatives
- **Files modified:** bot/reporting/daily_summary.py
- **Commit:** f7d892e (included in implementation commit)

## Decisions Made

- `pnl_sign_fmt` uses `abs(pnl)` with explicit sign character — avoids Python's automatic float sign conflicting with explicit prefix
- `Etc/GMT-5` is the correct APScheduler timezone string for UTC+5 (inverted POSIX convention)
- Balance fetch failure (Binance unreachable) is non-fatal — logs warning, uses 0.0, message still sends

## Self-Check: PASSED

- [x] `bot/reporting/__init__.py` exists
- [x] `bot/reporting/daily_summary.py` exists and exports `send_daily_summary`, `pnl_sign_fmt`
- [x] `tests/test_daily_summary.py` exists (6 tests, all passing)
- [x] `bot/main.py` modified with import + job registration
- [x] Commit f7d892e exists
- [x] Commit 20bf126 exists
