---
phase: 03-signal-and-risk
plan: "04"
subsystem: charts
tags: [mplfinance, matplotlib, charts, smc, png, asyncio]

# Dependency graph
requires:
  - phase: 03-signal-and-risk-01
    provides: OrderBlock, FVG, StructureLevel dataclasses from bot/signals/smc.py
  - phase: 03-signal-and-risk-02
    provides: compute_macd, compute_rsi from bot/signals/indicators.py
  - phase: 03-signal-and-risk-03
    provides: signal dict shape from bot/signals/generator.py
provides:
  - async generate_chart(df, signal, zones) -> bytes — mplfinance PNG with SMC overlays
  - bot/charts/ package with __init__.py and generator.py
affects: [04-telegram, any phase that sends chart images to users]

# Tech tracking
tech-stack:
  added: [mplfinance==0.12.10b0, matplotlib (transitive), pillow (transitive)]
  patterns: [asyncio.to_thread for CPU-bound rendering, matplotlib.use('Agg') headless mode, BytesIO for disk-free PNG output]

key-files:
  created:
    - bot/charts/__init__.py
    - bot/charts/generator.py
  modified: []

key-decisions:
  - "matplotlib.use('Agg') called at module level before mplfinance import — Docker headless required"
  - "asyncio.to_thread(_render_chart) used (not run_in_executor) — cleaner asyncio pattern for CPU-bound work"
  - "plt.close(fig) mandatory after fig.savefig() — prevents memory leak in long-running bot process"
  - "panel_ratios=(3,1,1) with volume=False gives axes[0]=main, axes[2]=MACD, axes[4]=RSI"
  - "_get() accessor handles both dataclass attributes and dict keys — tests use dicts, production uses dataclasses"
  - "Dynamic candle range: minimum 60 candles, includes all OB/FVG bar_index with 10-bar margin"

patterns-established:
  - "CPU-bound matplotlib rendering always offloaded via asyncio.to_thread — never block event loop"
  - "BytesIO-only output (no disk I/O) — return buf.read() after buf.seek(0)"
  - "plt.close(fig) always paired with fig.savefig() — memory hygiene for long-running process"

requirements-completed: [CHART-01, CHART-02, CHART-03, CHART-04, CHART-05, CHART-06, CHART-07, CHART-08, CHART-09]

# Metrics
duration: 6min
completed: 2026-03-19
---

# Phase 03 Plan 04: Chart Generator Summary

**Async mplfinance chart generator producing 125KB PNG with SMC overlays (OB/FVG rectangles, BOS/CHOCH lines, entry/SL/TP, MACD+RSI panels) in 0.22s via asyncio.to_thread**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-19T20:16:51Z
- **Completed:** 2026-03-19T20:23:58Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Implemented `generate_chart(df, signal, zones) -> bytes` async function with full SMC visual overlay stack
- mplfinance multi-panel chart: main candlestick + MACD (3 addplots: line/signal/histogram) + RSI with 30/70 reference lines
- OB zones rendered as colored Rectangles with alpha=0.15; FVG zones as dashed Rectangles with alpha=0.05; BOS/CHOCH as axhlines
- All 4 test_chart_generator.py tests GREEN; full Phase 3 suite 30/30 passed

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Chart Generator with mplfinance multi-panel rendering** - `343bdef` (feat)

**Plan metadata:** _(this summary commit)_

## Files Created/Modified
- `bot/charts/__init__.py` - Package marker (empty)
- `bot/charts/generator.py` - Async generate_chart() + sync _render_chart() with all SMC overlays

## Decisions Made
- `matplotlib.use('Agg')` at module level before any mplfinance import — mandatory for Docker headless rendering
- `asyncio.to_thread()` chosen over `run_in_executor()` — idiomatic Python 3.9+ pattern for CPU-bound thread offload
- `plt.close(fig)` immediately after `fig.savefig()` — prevents matplotlib figure memory accumulation in long-running bot
- `panel_ratios=(3, 1, 1)` with `volume=False` gives deterministic axes layout: [0]=main, [2]=MACD, [4]=RSI
- `_get()` helper handles both dataclass attrs and dict keys uniformly — test fixtures use dicts, production uses dataclasses

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing mplfinance and matplotlib from requirements.txt**
- **Found during:** Task 1 (after writing generator.py, module failed to import)
- **Issue:** `mplfinance==0.12.10b0` was in requirements.txt but not installed in the venv; `import matplotlib` raised ModuleNotFoundError
- **Fix:** Ran `.venv/bin/pip install mplfinance==0.12.10b0` which pulled in matplotlib, pillow, and other transitive deps
- **Files modified:** None (venv only)
- **Verification:** `.venv/bin/python -c "import bot.charts.generator; print('OK')"` succeeded; all 4 chart tests passed
- **Committed in:** 343bdef (included in task commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — missing venv dependency)
**Impact on plan:** Necessary to unblock module import. No scope creep.

## Issues Encountered
- mplfinance not installed despite being in requirements.txt — pip install resolved it immediately

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `generate_chart()` is fully importable from `bot.charts.generator` and returns valid PNG bytes
- Phase 4 (Telegram) can call `await generate_chart(df, signal, zones)` to get a ready-to-attach PNG
- All CHART-01 through CHART-09 requirements satisfied

---
*Phase: 03-signal-and-risk*
*Completed: 2026-03-19*
