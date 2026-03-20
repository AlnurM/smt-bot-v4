# Phase 5: Order Execution and Position Monitoring - Context

**Gathered:** 2026-03-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Order Executor places isolated-margin market orders on Binance Futures with SL/TP bracket after Telegram confirmation. Position Monitor polls open positions every 60 seconds, detects SL/TP fills, sends close notifications to Telegram, updates win streak, and records trades. Dry-run mode simulates orders without touching Binance. No new Telegram commands (Phase 4 handles UI), no daily summary (Phase 6), no Pine Script (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Order Placement Flow
- Market order by default for entry — guaranteed execution, handles slippage
- SL/TP bracket placed simultaneously with entry (Binance bracket order API) — not after fill
- Partial fills: Claude's discretion on handling (Binance Futures market orders typically fill fully)
- After order fill: send Telegram confirmation with fill price and actual position size (within 5 seconds target)
- Set margin type to ISOLATED before every new position (enforced programmatically)
- No retry on any order failure — alert only, trader decides next step

### Position Monitoring
- Simple polling every 60 seconds (no WebSocket) — check SL/TP order statuses on Binance
- Close detection: monitor SL and TP order statuses — when one fills, position is closed
- On close: send Telegram notification with final PnL and close reason (SL hit / TP hit)
- On close: create Trade record in DB (entry, exit, PnL, close reason)
- On close: update win streak counter (win = TP hit, loss = SL hit) for progressive stakes
- On close: update daily stats aggregation (PnL, trade count, win rate)
- Polling job runs as APScheduler IntervalTrigger (every 60 seconds)

### Error Handling
- Insufficient balance: Telegram alert "⚠️ Недостаточно баланса: $X доступно, $Y необходимо", mark signal as 'failed', no retry
- API timeout: Telegram alert with error details, no retry (risk of duplicate orders)
- Unknown Binance errors: Telegram alert with error code and message, mark signal as 'error'
- All errors go through `send_error_alert()` from Phase 4 notifications (15-min throttle applies)
- No automatic retry on any order placement failure

### Dry-Run Mode
- Signal goes through full flow but order is logged to DB as 'dry_run' status instead of being sent to Binance
- Telegram shows "[DRY RUN]" prefix on confirmation messages
- Toggled via Telegram command `/dryrun on/off` — runtime toggle, no restart needed
- Dry-run state stored in module-level `_bot_state` dict (same pattern as `/pause` from Phase 4)
- Position monitoring skips dry-run signals (no Binance orders to monitor)

### Claude's Discretion
- Exact Binance Futures API method calls for bracket order placement
- Partial fill handling details (likely not needed for market orders on Futures)
- Position monitoring implementation (APScheduler job vs dedicated async task)
- How to reconcile DB state with Binance state on monitoring cycle
- Error code mapping (Binance error codes to user-friendly Russian messages)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec
- `.planning/PROJECT.md` — Core value (full trade loop)
- `.planning/REQUIREMENTS.md` — ORD-01 through ORD-05, MON-01 through MON-05
- `.planning/ROADMAP.md` — Phase 5 details, success criteria

### Research
- `.planning/research/STACK.md` — python-binance 1.0.35 Futures API
- `.planning/research/PITFALLS.md` — Testnet→production URL drift, order placement errors

### Original spec
- `idea.md` — Section 7.3 (position sizing formula with leverage), Section 12.3 (error handling)

### Existing code
- `bot/telegram/handlers/callbacks.py` — `handle_confirm` marks signal as 'confirmed' (trigger for order placement)
- `bot/exchange/client.py` — `create_binance_client()` returns `AsyncClient`
- `bot/risk/manager.py` — `calculate_position_size()`, `get_progressive_stake()`, `check_daily_limit()`
- `bot/telegram/notifications.py` — `send_error_alert()` with 15-min throttle
- `bot/telegram/handlers/commands.py` — `_bot_state` dict for pause/resume/dry-run state
- `bot/db/models.py` — Order, Position, Trade, DailyStats ORM models

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot/exchange/client.py: create_binance_client()` — AsyncClient for all Binance API calls
- `bot/risk/manager.py: calculate_position_size()` — Returns position size dict with contracts, risk_usdt, etc.
- `bot/risk/manager.py: get_progressive_stake()` — Returns current stake tier based on win streak
- `bot/risk/manager.py: check_daily_limit()` — Returns True if daily limit reached
- `bot/telegram/notifications.py: send_error_alert()` — Throttled error notifications
- `bot/telegram/handlers/commands.py: _bot_state` — Module-level dict for runtime state (pause, dry_run)
- `bot/db/models.py` — Order (binance_order_id, status, executed_price), Position (current_pnl), Trade (entry, exit, pnl, close_reason), DailyStats (total_pnl, trade_count, win_rate, win_streak)

### Established Patterns
- Async functions with `AsyncClient` parameter injection
- DB session via `get_session()` async generator
- APScheduler CronTrigger for scheduled jobs (hourly scan, daily expiry)
- `send_error_alert()` for Telegram error notifications
- `_bot_state` dict for runtime toggles

### Integration Points
- `handle_confirm` callback → triggers order placement (new code)
- Order Executor → Binance Futures API (market order + bracket SL/TP)
- Order Executor → Order/Position DB records
- Position Monitor → Binance API polling (order statuses)
- Position Monitor → Trade record creation on close
- Position Monitor → Win streak update → progressive stakes
- Position Monitor → DailyStats aggregation
- Position Monitor → Telegram notification on close

</code_context>

<specifics>
## Specific Ideas

- The spec (section 7.3) has the exact position sizing formula — use this with actual fill price, not signal entry price
- `handle_confirm` in callbacks.py currently marks signal as 'confirmed' — the Order Executor should be triggered from there (or the scan pipeline detects confirmed signals)
- Dry-run `/dryrun on/off` is a new Telegram command that needs to be added to the commands router
- The monitoring job should be registered in `main.py` alongside the existing scan and expiry jobs

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-order-execution-and-position-monitoring*
*Context gathered: 2026-03-20*
