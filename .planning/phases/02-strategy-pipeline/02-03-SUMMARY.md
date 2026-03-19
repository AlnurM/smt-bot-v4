---
phase: 02-strategy-pipeline
plan: "03"
subsystem: strategy
tags: [sqlalchemy, apscheduler, crontrigger, dataclass, filter, strategy-lifecycle]

# Dependency graph
requires:
  - phase: 02-01
    provides: get_top_n_by_volume, fetch_ohlcv_15m (market scanner)
  - phase: 02-02
    provides: generate_strategy, ClaudeTimeoutError, ClaudeRateLimitError, StrategySchemaError (claude engine)
provides:
  - filter_strategy pure function with FilterResult dataclass (strict + relaxed mode)
  - Strategy Manager: get_coins_needing_strategy, save_strategy, log_skipped_coin
  - Strategy Manager: get_expired_active_strategies, deactivate_strategy
  - Strategy Manager: run_strategy_scan (hourly), run_expiry_check (daily)
  - APScheduler CronTrigger jobs registered in bot/main.py
affects: [03-signal-detector, 04-telegram-bot, 05-order-execution]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FilterResult dataclass (not Pydantic) for lightweight filter output"
    - "Relaxed vs strict mode filter: only total_return + drawdown required in relaxed mode"
    - "Strategy lifecycle: save_strategy is the ONLY place deactivation happens — run_expiry_check logs only"
    - "Expired strategies stay is_active=True until save_strategy atomically replaces — no coverage gap"
    - "APScheduler jobs use asyncio.create_task() to fire async work outside scheduler window"
    - "CronTrigger (not IntervalTrigger) for drift-free scheduling"

key-files:
  created:
    - bot/strategy/filter.py
    - bot/strategy/manager.py
  modified:
    - bot/main.py

key-decisions:
  - "filter_strategy is a pure stateless function — no DB access, fully unit testable"
  - "Relaxed mode (default): only total_return_pct and max_drawdown_pct required — allows initial strategy accumulation"
  - "win_rate comparison: criteria stores percent (55.0), backtest stores decimal (0.58) — divide criteria by 100"
  - "run_expiry_check does NOT deactivate expired strategies — logs only; save_strategy owns the atomic deactivate+insert"
  - "backtest_score = profit_factor * win_rate stored for ranking/analytics"
  - "criteria_snapshot persisted with every Strategy row for audit trail (LIFE-05)"

patterns-established:
  - "Pattern: Strategy filter separates validation logic from persistence — filter.py has zero DB imports"
  - "Pattern: Priority queue — no_strategy coins processed before expired coins each scan cycle"
  - "Pattern: In-memory _consecutive_empty_cycles counter for alert threshold; resets on any activity"

requirements-completed: [STRAT-05, FILT-01, FILT-02, FILT-03, FILT-04, FILT-05, LIFE-01, LIFE-02, LIFE-03, LIFE-04, LIFE-05]

# Metrics
duration: 4min
completed: 2026-03-19
---

# Phase 02 Plan 03: Strategy Filter, Manager, and APScheduler Jobs Summary

**Pure filter function with relaxed/strict modes, full Strategy lifecycle (save/expire/version), and two CronTrigger APScheduler jobs closing the Scanner -> Claude -> Filter -> Manager pipeline**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-19T13:13:05Z
- **Completed:** 2026-03-19T13:17:03Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Strategy Filter (`filter.py`): pure stateless function, FilterResult dataclass, relaxed mode (total_return + drawdown only), strict mode (all 6 criteria)
- Strategy Manager (`manager.py`): full lifecycle — get_coins_needing_strategy, save_strategy (deactivate old + insert new), log_skipped_coin, get_expired_active_strategies, deactivate_strategy
- run_strategy_scan (hourly) + run_expiry_check (daily) registered as CronTrigger APScheduler jobs in main.py
- All 11 tests GREEN (3 filter + 8 manager); full suite 56 passed

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Strategy Filter (filter.py)** - `dcf15a8` (feat)
2. **Task 2: Implement Strategy Manager and wire APScheduler jobs** - `0c06232` (feat)

**Plan metadata:** (docs commit — this summary)

## Files Created/Modified
- `bot/strategy/filter.py` - FilterResult dataclass + filter_strategy pure function (FILT-01..03)
- `bot/strategy/manager.py` - Full strategy lifecycle management + run_strategy_scan + run_expiry_check (STRAT-05, FILT-04..05, LIFE-01..05)
- `bot/main.py` - APScheduler job registrations: strategy_scan (hourly :05 UTC) + expiry_check (02:00 UTC)

## Decisions Made
- win_rate unit conversion: criteria dict holds `min_win_rate_pct` as percent (55.0), backtest dict holds `win_rate` as decimal (0.58) — filter divides criteria by 100 before comparison
- run_expiry_check is logging/alerting only — it does NOT deactivate expired strategies; this preserves uninterrupted trading coverage until save_strategy atomically replaces the old strategy
- backtest_score formula: `profit_factor * win_rate` — combines two key metrics into a single sortable score

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None — all tests passed first run without debugging required.

## Next Phase Readiness
- Phase 2 complete: full strategy production pipeline operational — Scanner -> Claude Engine -> Filter -> Manager -> APScheduler
- Phase 3 (signal detector) can import `get_coins_needing_strategy` and use active strategies from DB
- Phase 4 (Telegram bot) can wire Telegram alerts into the `# TODO: send Telegram alert` placeholder in run_strategy_scan

---
*Phase: 02-strategy-pipeline*
*Completed: 2026-03-19*
