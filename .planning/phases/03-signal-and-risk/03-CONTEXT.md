# Phase 3: Signal and Risk - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

SMC signal detection (Order Blocks, Fair Value Gaps, BOS/CHOCH), MACD/RSI indicator analysis, signal generation with strength scoring, risk-based position sizing with progressive stakes and daily circuit breaker, and chart PNG rendering with full SMC overlay. All verifiable without Telegram or order placement — this phase produces Signal objects, risk calculations, and chart images that Phase 4 (Telegram) and Phase 5 (Order Execution) will consume.

</domain>

<decisions>
## Implementation Decisions

### SMC Detection Parameters
- SMC params (ob_lookback_bars, fvg_min_size_pct, require_bos_confirm, use_choch, htf_confirmation) come from strategy JSON per coin — Claude optimized these during backtesting
- Always exclude the current (incomplete) candle: `df.iloc[:-1]` — signals only on fully closed data, deterministic results
- Higher timeframe confirmation: fetch 4h OHLCV data separately, run BOS/CHOCH detection on it, require alignment with 15m signal direction
- Order Block identification: combined approach — OB = last opposite candle before a BOS, AND must show significant body relative to surrounding candles (imbalance characteristic)
- Fair Value Gap: standard 3-candle gap, but only registered if gap size >= `fvg_min_size_pct` from strategy JSON
- BOS vs CHOCH: standard ICT definitions — BOS = break in trend direction (continuation), CHOCH = break against trend (reversal)

### Signal Strength Logic
- Weighted scoring system: each entry condition has a weight (e.g., HTF BOS confirmation = 3, OB zone = 2, MACD cross = 2, RSI confirmation = 1, volume = 1)
- Signal strength derived from total score: Strong (≥7), Moderate (4-6), Weak (1-3) — thresholds TBD during implementation
- ALL signals sent to Telegram regardless of strength — labeled with strength for trader to decide
- Entry conditions: which conditions are required vs optional is defined by strategy JSON (not hardcoded 4-of-4)
- Signal object includes: direction, entry price, SL, TP, R/R ratio, signal strength label, reasoning text listing which conditions were met

### Chart Visual Style
- Follow spec exactly for colors: green OB (demand), red OB (supply), transparent FVG with dashed borders, blue dashed entry line, red solid SL, green solid TP
- Dynamic candle range: auto-adjust to include all relevant OB/FVG zones in view (not fixed 100-150)
- 200 DPI for sharper display on high-res phones
- MACD panel below chart: histogram + signal lines, crossover point marked
- RSI panel below MACD: 30/70 levels, signal zone highlighted
- Chart title: symbol, timeframe, direction, R/R ratio
- Render to BytesIO, no disk I/O

### Risk Edge Cases
- MIN_NOTIONAL: when position size is too small, still send signal to Telegram but mark as "too small to execute" — informational only, no Confirm button
- Liquidation safety: configurable multiplier stored in risk_settings (default 2x SL distance) — reject if liquidation price is closer than threshold
- Daily loss limit (5%): stop generating new signals, keep existing positions open with their SL/TP, send prominent Telegram alert
- Progressive stakes: advance through tiers (3→5→8%) on consecutive wins, reset to base on any loss (from spec, already in RiskSettings)
- Max open positions: enforce before allowing new signals (default 5, from risk_settings)
- R/R minimum: signals below min_rr_ratio are filtered out before reaching Telegram

### Claude's Discretion
- Exact weighted scoring values for signal strength
- Signal strength threshold breakpoints (Strong/Moderate/Weak)
- mplfinance chart configuration details (figure size, spacing, panel ratios)
- Thread pool executor configuration for chart rendering
- How to handle edge cases in SMC detection (e.g., overlapping OBs, nested FVGs)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec
- `.planning/PROJECT.md` — Core value, constraints
- `.planning/REQUIREMENTS.md` — SIG-01 through SIG-06, RISK-01 through RISK-10, CHART-01 through CHART-09
- `.planning/ROADMAP.md` — Phase 3 details, success criteria, plan breakdown

### Research
- `.planning/research/STACK.md` — pandas-ta-classic, mplfinance versions
- `.planning/research/ARCHITECTURE.md` — Signal pipeline data flow
- `.planning/research/PITFALLS.md` — SMC detection parameter ranges not standardized (needs validation)

### Original spec
- `idea.md` — Section 6.2 (strategy_data JSON with SMC/indicator params), Section 7 (risk management), Section 9 (chart visualization with color specs)

### Existing code
- `bot/strategy/claude_engine.py` — StrategySchema defines the strategy JSON structure that SMC detector reads params from
- `bot/db/models.py` — Signal, RiskSettings, Position, DailyStats ORM models
- `bot/scanner/market_scanner.py` — `fetch_ohlcv_15m()` for candle data

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot/scanner/market_scanner.py: fetch_ohlcv_15m()` — fetches 15m OHLCV data, returns DataFrame with open_time/OHLCV/volume columns
- `bot/strategy/claude_engine.py: StrategySchema` — Pydantic model defining strategy JSON structure (indicators, smc, entry, exit, backtest fields)
- `bot/strategy/filter.py: filter_strategy()` — pure function, pattern for stateless analysis modules
- `bot/db/models.py: Signal` — ORM model with direction, entry_price, stop_loss, take_profit, rr_ratio, signal_strength, reasoning, chart_image fields
- `bot/db/models.py: RiskSettings` — Single-row table with all risk params (base_stake_pct, progressive_stakes JSONB, daily_loss_limit_pct, leverage, etc.)
- `bot/db/models.py: DailyStats` — date, total_pnl, trade_count, win_rate, win_streak fields
- `bot/config.py: settings` — Has all risk defaults as .env fallbacks

### Established Patterns
- Async functions with `AsyncClient` parameter (not imported globally)
- Pydantic models for schema validation (StrategySchema pattern)
- Pure functions for analysis logic (filter_strategy pattern)
- loguru for structured logging with SecretStr masking
- pytest with mock fixtures in conftest.py

### Integration Points
- Signal Generator reads active strategies from DB → applies to live OHLCV → produces Signal objects
- Risk Manager reads RiskSettings from DB → sizes positions → validates MIN_NOTIONAL + liquidation
- Chart Generator receives Signal + OHLCV DataFrame → produces BytesIO PNG
- Phase 4 (Telegram) will consume Signal objects + chart BytesIO
- Phase 5 (Order Executor) will consume risk-calculated position sizes

</code_context>

<specifics>
## Specific Ideas

- The spec (section 9.1) has a detailed chart specification including exact visual elements — follow this as the source of truth
- The spec (section 7.3) has an exact position sizing formula: `risk_usdt = balance × current_stake_pct / 100`, `sl_distance = |entry - SL| / entry`, `position_usdt = risk_usdt / sl_distance`, `contracts = position_usdt × leverage / entry`
- SMC detection should produce structured zone objects (OB/FVG with coordinates) that both Signal Generator and Chart Generator can consume
- Chart rendering should use `asyncio.to_thread()` to avoid blocking the event loop (mplfinance is CPU-bound)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-signal-and-risk*
*Context gathered: 2026-03-19*
