# Phase 2: Strategy Pipeline - Context

**Gathered:** 2026-03-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Market Scanner discovers top-N coins from a curated whitelist, Claude API generates SMC+MACD/RSI strategies via code_execution backtesting, Strategy Filter validates against configurable criteria, and Strategy Manager handles versioned storage with expiry lifecycle. No signal generation, no chart rendering, no Telegram commands, no order execution — just the strategy production pipeline.

</domain>

<decisions>
## Implementation Decisions

### Claude Prompt Design
- Send 15m OHLCV data only (not 1h) — period determined by `backtest_period_months` setting (default 6 months, ~17,200 candles)
- 70/30 train/validation split for walk-forward validation — train on first 70%, validate on last 30%
- Strict JSON schema validation on Claude's response — must match strategy_data schema from spec exactly. If malformed, reject and retry once
- On Claude API failure (timeout, rate limit, error): send Telegram alert, fall back to existing strategies for coins that have them, retry failed coins in next scan cycle
- Sequential generation — one coin at a time, no parallel Claude calls
- 180-second timeout per Claude strategy generation call
- Claude model: `claude-sonnet-4-20250514` with `code_execution` tool (as specified in TZ)

### Scanner Coin Selection
- Curated whitelist of approved coins (stored in DB/config), not auto-discovery
- Default whitelist managed via .env/config, overridable via Telegram command at runtime
- Scanner ranks whitelist coins by 24h USDT-M Perpetual volume, selects top-N (default: 10)
- Minimum history check: coin must have at least `backtest_period_months` of 15m OHLCV data available on Binance — skip if insufficient
- Configurable via Telegram `/settings` (top-N count already in spec)

### Filter Strictness
- Default mode: relaxed (only return + drawdown must pass) — `strict_mode=false` as per spec default
- Priority queue for Claude API calls: coins with no strategy first → expired strategies → skip coins with active strategies
- When no coins pass criteria for multiple consecutive cycles: send Telegram alert with suggestion to loosen criteria (inline buttons)
- Alert threshold: configurable (e.g., after 3 consecutive empty scan cycles)

### Strategy Expiry Flow
- Old strategy stays `is_active=true` until new one passes filter — no gap in coverage during re-generation
- Expiry checked by dedicated APScheduler job (daily), separate from hourly scan
- If re-generation fails filter: deactivate old strategy (`is_active=false`), coin drops from trading until next successful generation
- Version history: old strategy marked `is_active=false`, never hard-deleted (as per spec)
- `criteria_snapshot` saved with each strategy for audit trail

### Concurrent Generation
- Sequential processing only — one Claude API call at a time per scan cycle
- No parallel Claude calls — avoids rate limiting and simplifies error handling

### Claude's Discretion
- OHLCV data serialization format (CSV vs JSON) for Claude prompt
- Exact prompt engineering for structured strategy output
- Token budget management per Claude call
- How to handle partial/incomplete backtest results from code_execution

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project spec
- `.planning/PROJECT.md` — Core value, constraints, tech stack
- `.planning/REQUIREMENTS.md` — SCAN-01 through SCAN-04, STRAT-01 through STRAT-05, FILT-01 through FILT-05, LIFE-01 through LIFE-05
- `.planning/ROADMAP.md` — Phase 2 details, success criteria, plan breakdown

### Research
- `.planning/research/STACK.md` — Validated library versions (anthropic SDK, python-binance)
- `.planning/research/FEATURES.md` — Feature landscape, MVP vs differentiators
- `.planning/research/PITFALLS.md` — Strategy overfitting pitfall, Claude context exhaustion warning
- `.planning/research/SUMMARY.md` — Phase 2 flagged for deeper research on prompt engineering

### Original spec
- `idea.md` — Full TZ v4.0: section 4 (backtesting via code_execution), section 5 (strategy criteria), section 6 (strategy JSON format), section 3.1 (Claude API model)

### User notes
- `.planning/notes/2026-03-19-claude-rate-limit-fallback.md` — User note about Claude rate limit handling and fallback to existing strategies
- `.planning/notes/2026-03-19-список-монет-торговля.md` — User note about curated coin list based on history, volume, stability

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot/db/models.py: Strategy` — ORM model with all required fields (symbol, timeframe, strategy_data JSONB, backtest_score, is_active, next_review_at, criteria_snapshot JSONB)
- `bot/db/models.py: StrategyCriteria` — Single-row config table, already seeded with spec defaults by Alembic
- `bot/db/models.py: SkippedCoin` — Ready for logging skipped coins with backtest_results JSONB and failed_criteria JSONB
- `bot/exchange/client.py: create_binance_client()` — Returns `AsyncClient` for Binance API calls (OHLCV data fetching)
- `bot/db/session.py: get_session()` — Async session generator for all DB operations
- `bot/config.py: settings` — Has all strategy criteria defaults and Binance/Anthropic keys as SecretStr

### Established Patterns
- Pydantic-settings for config validation with SecretStr masking
- SQLAlchemy async with `expire_on_commit=False`
- APScheduler `AsyncIOScheduler` with MemoryJobStore for scheduled jobs
- loguru for structured logging

### Integration Points
- Scanner registers as APScheduler CronTrigger job (hourly)
- Expiry checker registers as separate APScheduler job (daily)
- Claude Strategy Engine uses `settings.anthropic_api_key` (currently not in Settings — needs to be added or is under a different name)
- All strategy CRUD goes through `get_session()` → Strategy/SkippedCoin/StrategyCriteria models

</code_context>

<specifics>
## Specific Ideas

- The spec (section 4.2) has an example Claude API request with the exact prompt structure — use this as the starting point and add walk-forward validation instructions
- Strategy JSON format is fully defined in section 6.2 of the spec — this is the validation schema
- The user wants Claude to be called conservatively — priority queue ensures coins without strategies get served first, and existing active strategies are never re-generated unnecessarily
- Telegram alerts for Claude failures should include the error type (rate limit vs timeout vs other) so the trader understands what happened

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-strategy-pipeline*
*Context gathered: 2026-03-19*
