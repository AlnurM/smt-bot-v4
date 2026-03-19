---
phase: 02-strategy-pipeline
plan: "01"
subsystem: scanner
tags: [python-binance, apscheduler, pandas, asyncclient, crontrigger, ohlcv, futures]

# Dependency graph
requires:
  - phase: 02-00
    provides: RED test stubs in tests/test_scanner.py, Settings with coin_whitelist/top_n_coins/min_volume_usdt, AsyncClient factory
  - phase: 01-foundation
    provides: bot package scaffold, config.py Settings, scheduler setup, pytest infrastructure
provides:
  - bot/scanner/market_scanner.py with get_top_n_by_volume, fetch_ohlcv_15m, register_scanner_job
  - MIN_HISTORY_CANDLES constant (15_000) for callers to enforce minimum OHLCV history
  - CronTrigger-based APScheduler job registration for hourly market scans
affects:
  - 02-02 (claude engine consumes fetch_ohlcv_15m output)
  - 02-03 (strategy manager calls get_top_n_by_volume and fetch_ohlcv_15m)
  - bot/main.py (calls register_scanner_job after scheduler.start())

# Tech tracking
tech-stack:
  added:
    - pandas 3.0.1 (was not installed in .venv; installed via pip during execution)
  patterns:
    - AsyncClient passed as parameter to scanner functions — never imported directly (dependency inversion)
    - MIN_HISTORY_CANDLES as module constant — callers check after fetch, not inside fetch
    - CronTrigger with timezone=UTC for drift-free scheduling (not IntervalTrigger)

key-files:
  created:
    - bot/scanner/__init__.py
    - bot/scanner/market_scanner.py
  modified: []

key-decisions:
  - "MIN_HISTORY_CANDLES check logs warning but returns data to caller — fetch_ohlcv_15m is a pure fetch function; callers decide whether to skip the symbol"
  - "pandas installed in .venv (was missing despite being in requirements.txt) — Rule 3 blocking fix"

patterns-established:
  - "Pattern: Scanner functions receive AsyncClient as parameter, never import it — enables mock injection in tests without patching"
  - "Pattern: fetch_ohlcv_15m returns all available data and warns on insufficient history — callers own the skip logic"

requirements-completed:
  - SCAN-01
  - SCAN-02
  - SCAN-03
  - SCAN-04
  - STRAT-03

# Metrics
duration: 4min
completed: 2026-03-19
---

# Phase 2 Plan 01: Market Scanner Summary

**Async market scanner ranking whitelist coins by 24h quoteVolume using python-binance USDT-M Futures API, with 15m OHLCV fetch and CronTrigger APScheduler job registration**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-19T13:04:42Z
- **Completed:** 2026-03-19T13:08:42Z
- **Tasks:** 1 (TDD: RED confirmed → GREEN)
- **Files modified:** 2

## Accomplishments
- Implemented `get_top_n_by_volume` — filters whitelist by 24h quoteVolume, excludes coins below `min_volume_usdt`, returns top-N ranked symbols
- Implemented `fetch_ohlcv_15m` — fetches USDT-M Futures 15m OHLCV via `futures_historical_klines` with `HistoricalKlinesType.FUTURES`, returns 6-column DataFrame with correct dtypes
- Implemented `register_scanner_job` — adds APScheduler job with `CronTrigger(hour=*, minute=0, timezone=UTC)`, avoiding IntervalTrigger drift
- All 5 scanner tests (`test_scanner.py`) pass GREEN; all 5 existing config tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Market Scanner module** - `ac888a7` (feat)

**Plan metadata:** (see final docs commit below)

_Note: TDD — RED state confirmed (5 tests skipped via importorskip), then GREEN after implementation._

## Files Created/Modified
- `bot/scanner/__init__.py` - Package marker (empty)
- `bot/scanner/market_scanner.py` - Market Scanner: `get_top_n_by_volume`, `fetch_ohlcv_15m`, `register_scanner_job`, `MIN_HISTORY_CANDLES`

## Decisions Made
- `MIN_HISTORY_CANDLES` check moved to caller responsibility: `fetch_ohlcv_15m` logs a warning when `len(df) < 15_000` but returns the DataFrame. The test (`test_ohlcv_fetch_format`) provides 10 candles and asserts `len(df) == 10` — returning empty on insufficient data would fail this format-check test. Callers (the scan loop) own the skip logic.
- `pandas` was not installed in `.venv` despite being in `requirements.txt`; installed it as a Rule 3 blocking fix.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Minimum history check returned empty DataFrame — broke STRAT-03 format test**
- **Found during:** Task 1 (running tests after initial implementation)
- **Issue:** `fetch_ohlcv_15m` initially returned an empty DataFrame when `len(df) < MIN_HISTORY_CANDLES`. The test `test_ohlcv_fetch_format` provides 10 fake klines and asserts `len(df) == 10` with correct dtypes, but empty DataFrame has `object` dtype — causing `assert df.dtypes["open"] == float` to fail.
- **Fix:** Changed the history check to log a warning but still return the full DataFrame. Callers are responsible for skipping symbols with insufficient history by checking against `MIN_HISTORY_CANDLES`.
- **Files modified:** `bot/scanner/market_scanner.py`
- **Verification:** All 5 scanner tests pass GREEN
- **Committed in:** `ac888a7` (Task 1 commit)

**2. [Rule 3 - Blocking] pandas not installed in .venv**
- **Found during:** Task 1 (import attempt)
- **Issue:** `ModuleNotFoundError: No module named 'pandas'` — pandas was in requirements.txt but not installed in the active virtualenv
- **Fix:** `.venv/bin/pip install pandas` (installed pandas 3.0.1 + numpy 2.4.3)
- **Files modified:** None (pip install only)
- **Verification:** `from bot.scanner.market_scanner import ...` succeeds without error
- **Committed in:** Not committed (pip environment change)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 blocking)
**Impact on plan:** Both fixes necessary for correctness. The MIN_HISTORY_CANDLES design aligns with the test contract — the constant remains in the module for callers to use. No scope creep.

## Issues Encountered
- Test `test_ohlcv_fetch_format` is a format-only test that can't simultaneously verify minimum history behavior — the two concerns are correctly separated: `fetch_ohlcv_15m` fetches and formats, callers enforce minimum history using `MIN_HISTORY_CANDLES`.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Market Scanner module fully implemented and tested
- `bot/scanner/market_scanner.py` ready to be called from `bot/main.py` via `register_scanner_job(scheduler, ...)`
- `fetch_ohlcv_15m` output format (6-column DataFrame with correct dtypes) ready for Claude Engine consumption in 02-02
- Callers must check `len(df) >= MIN_HISTORY_CANDLES` after calling `fetch_ohlcv_15m` to skip coins with insufficient history

## Self-Check: PASSED

All created files verified present. Commit ac888a7 confirmed in git log.

---
*Phase: 02-strategy-pipeline*
*Completed: 2026-03-19*
