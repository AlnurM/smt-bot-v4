# Phase 4: Telegram Interface - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Full Telegram bot UI using aiogram 3.x: signal dispatch with chart PNG and inline buttons (Confirm/Reject/Pine Script), single-user security middleware, all 14 commands from the spec (/start, /status, /risk, /criteria, /signals, /positions, /history, /strategies, /skipped, /scan, /chart, /settings, /pause, /resume, /help), plus error notifications, 80% loss warning, and "all coins skipped" alert. No order execution (Phase 5), no daily summary (Phase 6), no Pine Script generation (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Signal Message UX
- Signals auto-expire after configurable timeout (default 15 min) — marked as 'expired' in DB, inline buttons removed from message
- After Confirm tap: original message edited to "✅ Confirmed — placing order...", buttons removed. Second tap has no effect (DB unique constraint)
- After Reject tap: message edited to "❌ Rejected", buttons removed. Reason is optional — trader can type a freeform reason as a follow-up message if they want, but no forced prompt
- Signal message includes chart PNG as attached photo with caption containing all required fields (direction, symbol, entry/SL/TP, R/R, stake %, reasoning)
- Three inline buttons: ✅ Confirm | ❌ Reject | 📊 Pine Script
- MIN_NOTIONAL signals sent as informational only (no Confirm button, "too small" warning label)

### Command Response Style
- Language: Russian labels, English data (symbol names, percentages, timestamps in standard format) — follow spec section 8 templates
- Compact responses: key metrics only, one-line per item, fits mobile screen without scrolling
- Empty states: friendly Russian message (e.g., "Нет открытых позиций. Сигналы появятся, когда условия будут выполнены.")
- All commands only respond to `ALLOWED_CHAT_ID` — other users silently ignored

### Settings Commands UX
- Inline text commands as defined in spec section 7.4 and 5.3 (e.g., `/risk stake 3`, `/criteria return 200`)
- Validation errors: "❌ Неверное значение: stake должен быть 1-100%. Текущее: 3%" — show allowed range and current value
- Successful changes: "✅ base_stake_pct: 3% → 5%" — show old and new value
- `/risk` and `/criteria` without params show current settings table
- `/risk reset` and `/criteria reset` restore spec defaults from Alembic seed values

### Error & Alert Messages
- User-friendly: no stack traces, actionable info only ("⚠️ Binance API: connection timeout. Retry through 60s.")
- 80% daily loss limit warning: prominent alert with 🚨 emoji emphasis ("🚨 ВНИМАНИЕ: Дневной убыток 80% от лимита ($4.00/$5.00). Следующий убыток может остановить торговлю.")
- Repeated error throttling: alert on first occurrence, suppress for 15 min, repeat if still happening
- Claude API errors include error type (rate limit vs timeout vs other) in the alert
- "All coins skipped" alert: fires after consecutive_empty_cycles_alert threshold, suggest loosening criteria

### Claude's Discretion
- aiogram router/handler organization (single router vs multiple)
- Callback data format for inline buttons
- Message parsing approach for settings commands
- How to wire the bot into the existing main.py event loop
- Telegram message length limits handling (split long responses)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec
- `.planning/PROJECT.md` — Core value, constraints
- `.planning/REQUIREMENTS.md` — TG-01 through TG-18, TG-20 through TG-22 (21 requirements)
- `.planning/ROADMAP.md` — Phase 4 details, success criteria, plan breakdown

### Research
- `.planning/research/STACK.md` — aiogram 3.26 version
- `.planning/research/PITFALLS.md` — Telegram double-tap race condition, aiogram 60s callback deadline

### Original spec
- `idea.md` — Section 8 (all Telegram commands, signal format, notifications), Section 7.4 (/risk commands), Section 5.3 (/criteria commands)

### Existing code
- `bot/main.py` — Bot and Dispatcher already created, needs handler registration
- `bot/config.py` — `telegram_bot_token`, `allowed_chat_id`
- `bot/signals/generator.py` — `generate_signal()` produces Signal dict
- `bot/charts/generator.py` — `generate_chart()` returns PNG bytes
- `bot/risk/manager.py` — Risk calculation functions
- `bot/strategy/manager.py` — `run_strategy_scan()`, strategy lifecycle
- `bot/strategy/filter.py` — `filter_strategy()`
- `bot/db/models.py` — Signal, RiskSettings, StrategyCriteria, Position, Trade, DailyStats models

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot/main.py` — `Bot(token=...)` and `Dispatcher()` already instantiated; needs router registration and handler wiring
- `bot/config.py: settings.allowed_chat_id` — Single-user chat ID for middleware filter
- `bot/signals/generator.py: generate_signal()` — Returns Signal dict with all fields needed for TG-02
- `bot/charts/generator.py: generate_chart()` — Returns PNG bytes for attachment
- `bot/risk/manager.py` — `calculate_position_size()`, `check_daily_limit()`, `get_progressive_stake()`, `update_risk_settings()`
- `bot/strategy/manager.py` — `run_strategy_scan()`, `get_coins_needing_strategy()`
- `bot/db/models.py` — All ORM models for queries (Signal, Position, Trade, Strategy, SkippedCoin, RiskSettings, StrategyCriteria, DailyStats)

### Established Patterns
- Async functions with dependency injection (session, client as params)
- Pydantic for validation (StrategySchema, Settings)
- loguru for logging with SecretStr masking
- DB session via `get_session()` async generator
- APScheduler CronTrigger for scheduled jobs

### Integration Points
- Signal dispatch: when `run_strategy_scan()` finds a signal → needs to call Telegram send function
- Confirm callback: marks signal as 'confirmed' in DB → Phase 5 Order Executor consumes this
- Settings commands: read/write RiskSettings and StrategyCriteria tables
- Query commands: SELECT from Signal, Position, Trade, Strategy, SkippedCoin, DailyStats tables
- Error notifications: catch-all handler needs access to the bot instance for sending alerts

</code_context>

<specifics>
## Specific Ideas

- The spec (section 8.2) has the exact signal message format with all fields and emoji — use this as the template
- Section 8.1 lists all 14 commands with descriptions — implement exactly as specified
- The double-tap protection must use a DB-level unique constraint (from pitfalls research), not just in-memory state
- Signal expiry should use APScheduler `date` trigger (fire once after timeout) to edit the message and remove buttons

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-telegram-interface*
*Context gathered: 2026-03-19*
