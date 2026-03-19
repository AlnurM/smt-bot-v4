---
phase: 03-signal-and-risk
plan: "01"
subsystem: signals
tags: [smc, indicators, order-blocks, fvg, bos-choch, macd, rsi, pandas-ta-classic]
dependency_graph:
  requires:
    - 03-00 (test stubs, OHLCV fixture)
    - bot/strategy/claude_engine.py (SMCParams, MACDParams, RSIParams interface contracts)
  provides:
    - bot/signals/smc.py (OrderBlock, FairValueGap, StructureLevel dataclasses + detection functions)
    - bot/signals/indicators.py (compute_macd, compute_rsi, detect_macd_crossover, detect_rsi_signal)
  affects:
    - 03-02 (signal generator consumes detect_order_blocks, detect_fvg, detect_bos_choch)
    - 03-04 (chart generator consumes OrderBlock, FairValueGap, StructureLevel dataclasses)
tech_stack:
  added:
    - pandas-ta-classic==0.4.47 (installed into .venv — was in requirements.txt but missing from venv)
  patterns:
    - Pure stateless functions — no DB, no network, no side effects
    - df.iloc[:-1] applied internally in every public function (forming candle excluded)
    - Lazy import of pandas_ta_classic inside functions (fail-fast if missing)
    - Column name normalisation: pandas-ta-classic returns MACDh_/MACDs_ (lowercase), normalised to uppercase MACDH_/MACDS_
key_files:
  created:
    - bot/signals/__init__.py
    - bot/signals/smc.py
    - bot/signals/indicators.py
  modified: []
decisions:
  - "pandas_ta_classic is the correct import name for pandas-ta-classic package (not pandas_ta)"
  - "MACD column names from pandas-ta-classic use lowercase h/s suffixes; normalised to uppercase at function boundary to match contract"
  - "body_ratio threshold of 0.4 for Order Block candidate candles — filters out doji/indecision candles"
  - "detect_bos_choch returns at most 1 event (first structural break found after last swing) — prevents noise"
metrics:
  duration_minutes: 7
  completed_date: "2026-03-19"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
  deviations: 2
---

# Phase 03 Plan 01: SMC Detection and Indicator Wrappers Summary

**One-liner:** Pure stateless SMC zone detection (OrderBlock/FVG/BOS-CHOCH) and pandas-ta-classic MACD/RSI wrappers with closed-candle contract enforced internally in every function.

## What Was Built

### bot/signals/smc.py
Three dataclasses (`OrderBlock`, `FairValueGap`, `StructureLevel`) and three detection pure functions:

- `detect_bos_choch(df)` — swing high/low analysis (window=5 bars each side) determines trend direction, then scans for structural closes above/below last swing levels. Returns BOS (trend-direction break) or CHOCH (counter-trend break).
- `detect_order_blocks(df, ob_lookback_bars)` — calls `detect_bos_choch` internally, then searches backwards from each structural break for the last opposite-color candle with `body_ratio >= 0.4`. Returns list sorted most-recent first.
- `detect_fvg(df, fvg_min_size_pct)` — three-candle imbalance scan, registers gaps where `gap_size / candle[i-1].close * 100 >= fvg_min_size_pct`.

### bot/signals/indicators.py
Four wrapper functions over pandas-ta-classic:

- `compute_macd(df, fast, slow, signal)` — calls `df.ta.macd()`, normalises lowercase column suffixes to uppercase (MACDH/MACDS).
- `compute_rsi(df, period)` — calls `df.ta.rsi(length=period)`, returns Series named `RSI_{period}`.
- `detect_macd_crossover(macd_df, fast, slow, signal, direction)` — uses `iloc[:-1]` on the already-computed MACD DataFrame to detect cross on last closed candle.
- `detect_rsi_signal(rsi_series, oversold, overbought, direction)` — uses `iloc[:-1]` to detect exit from oversold/overbought zones.

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/test_smc.py | 7/7 | GREEN |
| tests/test_indicators.py | 4/4 | GREEN |
| **Total** | **11/11** | **GREEN** |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1: SMC detector | 11ea66c | feat(03-01): implement SMC detection pure functions |
| Task 2: Indicator wrappers | df8915c | feat(03-01): implement MACD/RSI indicator wrappers using pandas-ta-classic |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pandas-ta-classic not installed in .venv**
- **Found during:** Task 2 execution — `pytest` collected tests but all 4 failed with `ModuleNotFoundError: No module named 'pandas_ta'`
- **Issue:** `pandas-ta-classic==0.4.47` was listed in `requirements.txt` but was not present in the `.venv` site-packages.
- **Fix:** Ran `.venv/bin/pip install pandas-ta-classic==0.4.47`
- **Files modified:** None (runtime environment fix)
- **Commit:** Included in df8915c

**2. [Rule 1 - Bug] pandas-ta-classic column names use lowercase h/s suffixes**
- **Found during:** Task 2 — `test_compute_macd_columns` failed: `MACDH_12_26_9 not in ['MACD_12_26_9', 'MACDh_12_26_9', 'MACDs_12_26_9']`
- **Issue:** The `pandas_ta_classic` package uses `MACDh_` and `MACDs_` (lowercase) for the histogram and signal columns; the plan contract and test expect uppercase `MACDH_` and `MACDS_`.
- **Fix:** Added `macd_df.columns = [col.upper() for col in macd_df.columns]` after calling `df.ta.macd()` in `compute_macd()`.
- **Files modified:** bot/signals/indicators.py
- **Commit:** df8915c

## Self-Check: PASSED

All files exist and both commits verified in git history.
