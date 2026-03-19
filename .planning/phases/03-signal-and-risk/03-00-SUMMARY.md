---
phase: 03-signal-and-risk
plan: "00"
subsystem: testing
tags: [pytest, ohlcv, smc, indicators, signal-generator, risk-manager, chart-generator, pandas-ta-classic, mplfinance]

# Dependency graph
requires:
  - phase: 02-strategy-pipeline
    provides: pytest.importorskip pattern established for RED-state test stubs
provides:
  - 200-row deterministic OHLCV fixture (seed=42) at tests/fixtures/ohlcv_sample.csv
  - RED test scaffolds for all Phase 3 production modules (5 test files, 30 tests total)
  - pandas-ta-classic==0.4.47 and mplfinance==0.12.10b0 added to requirements.txt
affects:
  - 03-01-smc (implements bot/signals/smc.py tested by test_smc.py)
  - 03-02-indicators (implements bot/signals/indicators.py tested by test_indicators.py)
  - 03-03-signal-generator (implements bot/signals/generator.py tested by test_signal_generator.py)
  - 03-04-risk-manager (implements bot/risk/manager.py tested by test_risk_manager.py)
  - 03-05-chart-generator (implements bot/charts/generator.py tested by test_chart_generator.py)

# Tech tracking
tech-stack:
  added:
    - pandas-ta-classic==0.4.47 (community fork of pandas-ta for technical indicators)
    - mplfinance==0.12.10b0 (candlestick chart rendering via matplotlib)
  patterns:
    - pytest.importorskip at module level — entire test file skips until production module exists, transitions RED on first import success
    - Deterministic fixture generation with numpy seed=42 — same CSV every run, no flaky test data
    - OHLCV fixture at tests/fixtures/ohlcv_sample.csv — shared across all signal/chart test files via pd.read_csv

key-files:
  created:
    - tests/fixtures/__init__.py
    - tests/fixtures/ohlcv_sample.csv
    - tests/test_smc.py
    - tests/test_indicators.py
    - tests/test_signal_generator.py
    - tests/test_risk_manager.py
    - tests/test_chart_generator.py
  modified:
    - requirements.txt (added pandas-ta-classic, mplfinance)

key-decisions:
  - "OHLCV fixture uses numpy seed=42 random walk — deterministic across all environments, no network calls needed in tests"
  - "pytest.importorskip at module level (not function level) — cleaner skip messaging; entire file skips rather than 30 individual skips"

patterns-established:
  - "Pattern: Phase 3 tests all use tests/fixtures/ohlcv_sample.csv via pd.read_csv with parse_dates=['open_time'] + set_index"
  - "Pattern: Async chart/generator functions tested via asyncio.run() in sync tests — avoids pytest-asyncio fixture complexity"

requirements-completed:
  - SIG-01
  - SIG-02
  - SIG-03
  - SIG-04
  - SIG-05
  - SIG-06
  - RISK-01
  - RISK-02
  - RISK-03
  - RISK-04
  - RISK-05
  - RISK-06
  - RISK-08
  - RISK-09
  - CHART-01
  - CHART-02
  - CHART-05
  - CHART-09

# Metrics
duration: 12min
completed: 2026-03-19
---

# Phase 03 Plan 00: Signal and Risk — Wave 0 Test Infrastructure Summary

**Five RED test files covering 30 tests across SMC detection, MACD/RSI indicators, signal generator, risk manager, and chart generator; plus 200-row deterministic OHLCV fixture and two new library dependencies**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-03-19T19:50:00Z
- **Completed:** 2026-03-19T20:02:00Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Added pandas-ta-classic==0.4.47 and mplfinance==0.12.10b0 to requirements.txt — exact pinned versions per project decision
- Generated tests/fixtures/ohlcv_sample.csv: 200 rows, 15m OHLCV from 2024-01-01, numpy seed=42, all OHLC validity constraints verified
- Created 5 RED test scaffolds (30 total tests) using pytest.importorskip — all skip cleanly in current state, will turn RED as production modules are created

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dependencies and generate OHLCV fixture** - `c76267c` (chore)
2. **Task 2: RED test scaffolds for SMC detector and indicators** - `5fd7757` (test)
3. **Task 3: RED test scaffolds for signal generator, risk manager, chart generator** - `7054b2f` (test)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `requirements.txt` - Added pandas-ta-classic==0.4.47 and mplfinance==0.12.10b0
- `tests/fixtures/__init__.py` - Empty package marker for fixtures directory
- `tests/fixtures/ohlcv_sample.csv` - 200-row deterministic 15m OHLCV data (seed=42)
- `tests/test_smc.py` - 7 RED tests for bot.signals.smc (SIG-02): OB detection, FVG filtering, BOS/CHOCH, determinism
- `tests/test_indicators.py` - 4 RED tests for bot.signals.indicators (SIG-03): MACD columns, RSI series, crossover/signal booleans
- `tests/test_signal_generator.py` - 5 RED tests for bot.signals.generator (SIG-01, SIG-04–06): signal fields, strength scoring, volume check, entry conditions
- `tests/test_risk_manager.py` - 10 RED tests for bot.risk.manager (RISK-01–09): position sizing, progressive stakes, circuit breakers, liquidation safety
- `tests/test_chart_generator.py` - 4 RED tests for bot.charts.generator (CHART-01, 02, 05, 09): PNG output, OB zones, no disk writes

## Decisions Made

- Used numpy seed=42 for OHLCV fixture — matches plan specification exactly; guarantees identical CSV on every generation
- pytest.importorskip at module level (not per-test) — entire file skips until module exists, avoids 30x repeated skip messages

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used .venv/bin/python instead of python/python3**
- **Found during:** Task 1 (fixture generation)
- **Issue:** System python3 (3.14) had no numpy; project .venv contains all dependencies
- **Fix:** Used .venv/bin/python for all verification commands; no file changes needed
- **Files modified:** None (execution environment fix only)
- **Verification:** Script ran successfully, 200-row CSV generated correctly
- **Committed in:** c76267c (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — Python interpreter path)
**Impact on plan:** Execution-only fix, no code changes. No scope creep.

## Issues Encountered

- System python3 (3.14.3) missing numpy — .venv/bin/python used for all script runs. This is a known-good pattern for this project.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- All 5 RED test files ready — implementation plans (03-01 through 03-05) can now drive GREEN state
- OHLCV fixture shared across all test files via `pd.read_csv("tests/fixtures/ohlcv_sample.csv")`
- Test function signatures locked to match production module interfaces defined in plan interfaces block

---
*Phase: 03-signal-and-risk*
*Completed: 2026-03-19*
