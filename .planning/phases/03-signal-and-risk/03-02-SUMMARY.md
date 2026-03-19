---
phase: 03-signal-and-risk
plan: "02"
subsystem: signals
tags: [smc, macd, rsi, pandas-ta-classic, binance, scoring, htf-confirmation]

# Dependency graph
requires:
  - phase: 03-signal-and-risk
    plan: "01"
    provides: "SMC detector (smc.py) and indicator wrappers (indicators.py)"
provides:
  - "bot/signals/generator.py — async generate_signal() orchestrating SMC + indicators + HTF 4h + volume scoring"
  - "score_to_strength(), check_volume(), check_entry_conditions(), build_empty_signal_result() — pure testable helpers"
affects:
  - "04-telegram — consumes Signal dict returned by generate_signal()"
  - "03-03 — Risk Manager validates signal dict from this module"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Condition scoring: dictionary weights (CONDITION_WEIGHTS) summed from conditions_met list"
    - "HTF fetch inside async generate_signal() with try/except — failure degrades gracefully (no confirmation), does not abort signal generation"
    - "Score → direction selection: both long/short scored, highest wins; tie broken by long"
    - "SL from ob_boundary: opposite OB edge ± 0.1% buffer; fallback is 1% of current_price"
    - "Lazy import of binance inside generate_signal() — pure helpers remain importable without binance installed"

key-files:
  created:
    - "bot/signals/generator.py"
  modified: []

key-decisions:
  - "Lazy import of binance (AsyncClient, HistoricalKlinesType) inside generate_signal() body — pure helper functions (score_to_strength, check_volume, etc.) remain importable without binance dependency for unit tests"
  - "HTF 4h fetch is non-fatal — exception caught, htf_levels stays empty, signal proceeds without HTF confirmation rather than returning None"
  - "Both directions scored independently; highest score wins; long wins on tie — avoids short bias"
  - "volume_multiplier reads from strategy_data top-level key with 1.2 default — allows per-strategy override without schema change"

patterns-established:
  - "Signal generator pattern: pure helpers exported separately from async orchestrator — enables unit testing without mocks"
  - "Condition gating pattern: conditions_required list from strategy JSON gates which conditions are even evaluated — prevents false positives from unrelated strategy conditions"

requirements-completed: [SIG-01, SIG-04, SIG-05, SIG-06]

# Metrics
duration: 3min
completed: 2026-03-19
---

# Phase 3 Plan 02: Signal Generator Summary

**Async signal generator orchestrating SMC detection, MACD/RSI indicators, 4h HTF confirmation, and weighted condition scoring into a single generate_signal() entry point**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-19T15:08:16Z
- **Completed:** 2026-03-19T15:11:36Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Implemented `bot/signals/generator.py` wiring SMC detector + indicator functions from Plan 01 into a single async orchestration layer
- Pure helper functions (`score_to_strength`, `check_volume`, `check_entry_conditions`, `build_empty_signal_result`) exported for unit-testable scoring logic
- 4h HTF BOS/CHOCH confirmation fetched via `AsyncClient.KLINE_INTERVAL_4HOUR` with graceful degradation on fetch failure
- Weighted condition scoring: HTF=3, OB=2, MACD=2, RSI/BOS/volume=1; thresholds Strong>=7, Moderate>=4, Weak<4
- All 5 tests in `test_signal_generator.py` GREEN; 16/16 across smc + indicators + generator with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement Signal Generator helper functions (pure, testable)** — `68a298e` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `bot/signals/generator.py` — Async signal generator: generate_signal(), score_to_strength(), check_volume(), check_entry_conditions(), build_empty_signal_result(), _calculate_entry_sl_tp(), _check_price_in_ob(), _fetch_4h_df()

## Decisions Made

- **Lazy binance import inside generate_signal():** binance (AsyncClient, HistoricalKlinesType) imported inside the async function body only. Pure helpers remain importable without network dependencies — critical for unit testing.
- **HTF fetch non-fatal:** 4h klines fetch wrapped in try/except; on any exception htf_levels stays `[]` and signal proceeds without HTF confirmation weight rather than aborting entirely.
- **Both directions scored independently:** long and short conditions are evaluated separately; highest score wins; tie broken in favor of long to avoid short bias.
- **volume_multiplier from strategy_data:** reads `strategy_data.get("volume_multiplier", 1.2)` — allows per-strategy override without adding to StrategySchema.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `generate_signal()` ready for consumption by Phase 4 Telegram alert layer
- Signal dict contains `zones` key (order_blocks, fvgs, structure_levels) for Chart Generator in Phase 4
- Risk Manager (Plan 03-03) can validate the returned dict's entry_price/stop_loss/take_profit fields
- No blockers

---
*Phase: 03-signal-and-risk*
*Completed: 2026-03-19*
