# Domain Pitfalls: Crypto Futures Trading Bot

**Domain:** Semi-automated crypto futures trading bot (Binance USDT-M Perpetual, $100 deposit, Claude AI strategy generation, Telegram confirmation)
**Researched:** 2026-03-19
**Confidence:** MEDIUM-HIGH (core trading/API pitfalls from official sources; some async/integration patterns from community knowledge)

---

## Critical Pitfalls

Mistakes that cause account wipeout, rewrites, or fundamental system failure.

---

### Pitfall 1: Liquidation via Leverage + Small Account Math Blindness

**What goes wrong:**
The bot calculates position size in dollar terms but ignores how isolated margin interacts with leverage. At $100 account with 10x leverage, a 1% adverse move = 10% margin loss. A position that "looks safe" at 2% risk actually liquidates after a 0.2% move if leverage is miscalculated. The Risk Manager module silently compounds this: `progressive_stake * leverage` can create notional positions where the actual liquidation distance is under 2%.

**Why it happens:**
Risk is modeled as "% of account" without converting to "distance to liquidation price." With isolated margin, liquidation price is calculated from the initial margin posted, not total account size. Many implementations confuse account_balance * risk_percent with the actual margin math Binance uses.

**Consequences:**
Instant position liquidation. At $100 account, a single mis-sized position wipes 5-20% of capital in seconds. Progressive stake mode (3→5→8%) amplifies this on a winning streak right before a reversal.

**Prevention:**
- Always compute `liquidation_price` before placing any order using Binance's formula: `Liquidation Price = Entry * (1 - 1/(leverage * (1 + maintenance_margin_rate)))`
- Hard-cap: liquidation distance must be >= 2x the stop-loss distance
- Risk Manager must validate: `initial_margin / notional_value >= 1/max_leverage`
- Store `liquidation_price` in DB for every open position; alert if price approaches within 20%
- Use isolated margin exclusively (already planned) — never let a test accidentally switch to cross

**Warning signs:**
- Stop-loss distance is larger than liquidation distance
- Position size calculation doesn't reference current leverage setting
- No `liquidation_price` field in the positions table

**Phase to address:** Risk Manager implementation phase (before any live order execution)

---

### Pitfall 2: Strategy Overfitting via Claude Code Execution Backtesting

**What goes wrong:**
Claude generates Python backtesting code, runs it in its sandbox, and optimizes parameters until the strategy passes all filter criteria (winrate, drawdown, PF). The problem: Claude's code execution environment has no concept of walk-forward validation, out-of-sample testing, or survivorship bias. A strategy that returns 60% winrate on 3 months of BTC data is almost certainly overfit to that exact period.

**Why it happens:**
Claude optimizes for the criteria you give it. If the prompt says "find parameters that maximize Sharpe ratio on this data," it will — by overfitting. The backtest uses the same data for parameter selection and performance evaluation. SMC Order Blocks and FVGs are particularly susceptible because their detection parameters (lookback windows, size thresholds) have huge combinatorial spaces to overfit into.

**Consequences:**
Strategies that show 70%+ winrate in backtests perform at 40-50% or worse in live trading. Strategy lifecycle (auto-expiry + regeneration) will churn through strategies without ever finding a durable edge. API costs balloon as Claude continuously regenerates failing strategies.

**Prevention:**
- Structure Claude prompts to enforce a train/validation/test split: backtest on data[-90d:-30d], validate on data[-30d:-7d], reject if validation Sharpe drops >30% vs train
- Require Claude to report performance across at least 2 distinct market regimes (trending vs ranging)
- Set a minimum of 30 trades in backtest period (not just winrate — sample size matters)
- Flag strategies where any single parameter change >10% destroys performance (brittleness indicator)
- The Strategy Filter should include a `regime_consistency_score` check, not just aggregate metrics

**Warning signs:**
- Backtest winrate > 65% with > 2.5 Sharpe — almost always overfit
- Strategy fails within first 10 live trades
- All passing strategies cluster around same parameter ranges (overfitting convergence)

**Phase to address:** Strategy Filter implementation; Claude prompt engineering phase

---

### Pitfall 3: Testnet → Production Switch Creates Silent Behavioral Differences

**What goes wrong:**
The bot runs perfectly on Binance Futures Testnet. When the env variable flips to production, orders start failing, positions aren't tracked correctly, or — worst case — orders execute in unexpected ways. Testnet and production differ in: order fill behavior, latency, funding rate schedules, leverage tier limits, and sometimes API response formats after Binance updates.

**Why it happens:**
Testnet is not a perfect mirror of production. Known issues (confirmed in CCXT GitHub issues):
- Private API calls on Testnet can be misrouted to live endpoints, producing "Invalid API-Key ID" errors
- Binance periodically updates Testnet API base URLs without notice
- Testnet accounts reset/wipe approximately monthly — any open positions or DB state referencing testnet order IDs becomes invalid
- Testnet fills are instantaneous (no queue); production fills have realistic latency and can be partial

**Consequences:**
First production order fails silently or routes incorrectly. DB has stale testnet position records that the bot treats as open production positions. Position monitoring sends false SL/TP alerts.

**Prevention:**
- Store `environment` field (testnet/production) on every order, position, and strategy record in DB
- On startup, validate API connectivity and compare returned account type against configured env
- Implement a "dry run" mode separate from testnet: same production endpoints, but all orders logged-only (no actual placement)
- Before production switch: wipe or archive all testnet positions; validate DB state
- Pin CCXT/python-binance versions; don't auto-upgrade — each upgrade may change endpoint routing
- Use `ENVIRONMENT` env var but also log and validate the actual Binance account type on connect

**Warning signs:**
- Bot doesn't verify which environment it's connected to on startup
- Position table lacks an `environment` column
- No integration test that validates order placement end-to-end before production switch

**Phase to address:** Infrastructure/Order Executor phase; pre-production checklist milestone

---

### Pitfall 4: Progressive Stakes Create Path-to-Ruin on Losing Streaks

**What goes wrong:**
The progressive stake system (3→5→8% of account per trade) is anti-martingale on wins — which is reasonable. But the reset mechanism matters critically. If a losing trade resets stakes to 3%, consecutive losses at 3% each are survivable. If stakes don't reset cleanly — or if the bot enters a period where signal quality is poor and loss frequency is high — account drawdown accelerates.

**Why it happens:**
At $100 account:
- 3 consecutive losses at 8% stake = -24% (after a winning streak escalated stakes)
- 3 consecutive losses at 3% stake = -9%
The sequence matters. A winning streak that escalates to 8% followed by a losing streak hits at the worst time. Additionally, if position sizing rounds up to meet MIN_NOTIONAL, the effective stake percentage can exceed configured limits.

**Consequences:**
Account drawdown of 30-50% before the stake counter resets. At $100 starting capital, hitting $50-70 makes many pairs untradeable due to MIN_NOTIONAL.

**Prevention:**
- Implement a hard daily loss limit: if daily PnL drops below -10% of account, halt all new entries, alert via Telegram
- Track `consecutive_losses` in DB; reset progressive stakes immediately on any loss (not just after review)
- Validate that `stake_percent * account_balance >= MIN_NOTIONAL * 1.5` before escalating stake tier — if not, do not escalate
- Add a "max concurrent position" check: never have 3 positions simultaneously at 8% stake = 24% of account committed at once
- Make stake progression configurable and resettable via Telegram command

**Warning signs:**
- Risk Manager doesn't check MIN_NOTIONAL before stake escalation
- No daily loss circuit breaker
- Stake level persists across bot restarts without explicit reset logic

**Phase to address:** Risk Manager phase; first live trading phase review

---

### Pitfall 5: Telegram Confirmation Callback Race Condition / Double Execution

**What goes wrong:**
User taps "Confirm" on a Telegram signal message. Due to network issues or accidental double-tap, the callback fires twice. The aiogram handler places two orders for the same signal. At $100 account, even one duplicate order can be catastrophic.

**Why it happens:**
Telegram's Bot API guarantees at-least-once delivery of callbacks. On mobile with poor connectivity, a tap may register twice. aiogram 3.x's async handlers process callbacks concurrently by default — two near-simultaneous callbacks for the same `callback_data` will both enter the handler before the first one has set a "processing" flag.

**Consequences:**
Two orders opened for one signal. If both have SL/TP, the bot now has two positions to manage but may only track one in DB. Account margin used is 2x expected.

**Prevention:**
- Use a DB-level unique constraint on `(signal_id, action='confirmed')` — the second insert fails, preventing duplicate execution
- After callback received: immediately update signal status to `'pending_execution'` in a single atomic DB transaction; check status before placing order
- Use `asyncio.Lock` per signal_id to prevent concurrent handler execution for the same signal
- After order placement, edit the original Telegram message to remove the inline keyboard (prevents re-confirmation)
- Set callback answer timeout with `alert=True` to give user feedback that action was received

**Warning signs:**
- Confirmation handler doesn't check signal state before placing order
- No unique constraint on order table linking to signal_id
- Inline keyboard not removed after confirmation

**Phase to address:** Telegram bot / Order Executor integration phase

---

## Moderate Pitfalls

---

### Pitfall 6: Funding Rate Fees Erode Small Account on Held Positions

**What goes wrong:**
Perpetual futures charge funding rates every 8 hours. When funding is positive (longs pay shorts), a long position held for 24+ hours pays 3 funding cycles. At extreme funding rates (seen during bull markets: 0.1-0.3% per 8h), a $10 position might pay $0.03-$0.09 per day in funding — which sounds small but is 0.03-0.09% of $100 account daily just from one position.

**Why it happens:**
Funding rates are not factored into backtesting by default. Claude's code execution backtesting won't include funding costs unless explicitly prompted. Signal Generator identifies an entry; nothing warns that the position will be held over a high-funding window.

**Prevention:**
- Fetch current funding rate before entry; if rate > 0.05% per 8h, add a warning to the Telegram signal message
- Include funding rate in Strategy Filter: require that expected PnL (to TP) exceeds estimated funding cost for holding period
- Daily summary report must include total funding fees paid (separate line from trade PnL)
- Instruct Claude to include funding cost estimates in backtesting when holding period exceeds 8h

**Warning signs:**
- Strategy assumes zero cost of carry
- Funding fees not tracked in PnL calculations
- No funding rate fetch before signal generation

**Phase to address:** Signal Generator / Strategy Filter phase

---

### Pitfall 7: MIN_NOTIONAL Violations Cause Silent Order Failures

**What goes wrong:**
Binance USDT-M Futures has a minimum notional value of $5-$10 per order (varies by pair). At $100 account with 3% stake ($3), even at 5x leverage, notional = $15 which clears the minimum. But if account drops to $60 (after drawdown) and stake is still 3%: $1.80 * 5x = $9 — right at the edge. Certain altcoin pairs have higher minimums ($10-20). Order gets rejected with error code -4164 (`MIN_NOTIONAL`).

**Why it happens:**
MIN_NOTIONAL is pair-specific and not always documented in one place. Market Scanner selects top-N by volume without validating that selected pairs are tradeable at current account size and stake level.

**Prevention:**
- Market Scanner must fetch `filters` from `exchangeInfo` for each selected pair; store `min_notional` in DB
- Risk Manager validates `stake_amount * leverage >= min_notional * 1.2` (20% buffer) before generating a signal
- If validation fails, Market Scanner should skip that pair and log reason in skipped_coins table
- Alert via Telegram if available tradeable pairs drops below 3 (account too small)

**Warning signs:**
- Order Executor doesn't handle `-4164` error with meaningful logging
- No `min_notional` field in coin metadata table
- Market Scanner doesn't filter by tradability at current account size

**Phase to address:** Market Scanner + Risk Manager phase

---

### Pitfall 8: APScheduler Job Drift and Missed Scans

**What goes wrong:**
The hourly Market Scanner job starts to drift. The first run at T+0 takes 45 seconds (API calls + Claude strategy generation). APScheduler interval scheduler schedules next run at T+1h from trigger, but if the job is still running from the previous hour, the next execution is delayed or missed. After several hours, scans happen at unpredictable times. Signal Generator is now working on stale hourly candles.

**Why it happens:**
APScheduler's `IntervalTrigger` by default does not allow concurrent execution of the same job (`max_instances=1`), so if the previous run exceeds the interval, the next trigger is "missed." Long Claude API calls (strategy generation can take 30-60 seconds) plus Binance API pagination mean Market Scanner routinely exceeds a safe execution window.

**Prevention:**
- Use `CronTrigger` instead of `IntervalTrigger` for time-sensitive scans (exact HH:00 runs)
- Separate the Market Scanner into two stages: (1) fast scan for coin selection (runs at :00), (2) strategy generation runs as background task (doesn't block scanner)
- Set `misfire_grace_time=60` for the scanner job; log when a job is missed
- Monitor job execution duration; alert if scan exceeds 50% of its interval

**Warning signs:**
- Market Scanner and Strategy Generator run in the same APScheduler job
- No logging of job start/end times with duration
- Scanner interval and Claude API call timeout are in the same order of magnitude

**Phase to address:** Market Scanner architecture phase

---

### Pitfall 9: Look-Ahead Bias in SMC Pattern Detection

**What goes wrong:**
The Order Block and FVG detection code uses future candle data to "confirm" a pattern. For example: "an Order Block is confirmed when the next candle closes above the high." In backtesting, the confirmation candle's data is already in the DataFrame — so the signal fires on the confirmation candle but appears to have fired on the setup candle, giving an unrealistically early entry.

**Why it happens:**
Pandas-based detection code processes the full DataFrame at once. When you write `df['ob_confirmed'] = df['high'].shift(-1) > df['close']`, you're using future data. This is easy to miss when code works in both backtest and live contexts because the DataFame structure looks the same.

**Prevention:**
- In live trading: Signal Generator must only use `df.iloc[:-1]` (all candles except the forming candle) when detecting patterns on completed candles
- In backtesting: enforce a "simulation clock" — process candle by candle, never allow index N to access N+1
- Write a unit test that verifies Signal Generator produces identical signals whether called at candle close or 1 minute into next candle
- Document which patterns require "next candle confirmation" vs "same candle" — these need different handler logic

**Warning signs:**
- Pattern detection uses `shift(-N)` for any N > 0
- Backtesting DataFame is processed all-at-once with pandas operations
- Live winrate significantly lower than backtest winrate from first week

**Phase to address:** Signal Generator implementation phase; backtesting code review

---

### Pitfall 10: Claude API Context Window Exhaustion in Strategy Generation

**What goes wrong:**
Claude's code execution flow sends OHLCV data + strategy requirements + previous attempts as conversation context. For a 90-day hourly dataset (2160 candles, ~10 columns), the raw data alone is ~200KB+. After 2-3 strategy iterations with code outputs included, context window fills. Claude starts making more errors, "forgetting" constraints from earlier in the conversation, or producing truncated code.

**Why it happens:**
Claude's code execution tool is powerful but stateless between API calls — state must be passed in context. Iterative refinement ("try again with tighter SL") accumulates previous attempts in the message history. Anthropic's context window is large (200K tokens for claude-3-5-sonnet) but passing raw OHLCV data is extremely token-inefficient.

**Prevention:**
- Never pass raw OHLCV data in the prompt. Pass only summary statistics + a data file reference that Claude's code execution can load from its sandbox
- Limit strategy generation to 3 iterations per symbol per cycle; if no passing strategy found, skip and log
- Start a fresh conversation (new API call, no history) for each new strategy attempt — don't chain refinements
- Set `max_tokens` limit on Claude response to prevent runaway code generation
- Track Claude API cost per strategy; alert if daily cost exceeds threshold

**Warning signs:**
- OHLCV data appears inline in the Claude prompt as JSON/CSV
- Strategy generation retries accumulate in a single messages array
- No iteration limit on strategy generation loop

**Phase to address:** Strategy Generator / Claude integration phase

---

## Minor Pitfalls

---

### Pitfall 11: Position Monitoring Polling Frequency vs Rate Limits

**What goes wrong:**
Position monitoring polls Binance every N seconds to check if SL/TP has been hit. With multiple positions open, each poll is multiple API calls. Binance IP-based rate limit is 2400 weight/minute for REST API. Each `GET /fapi/v2/positionRisk` call costs 5 weight. With 3 positions and 10-second polling: 3 * 6 = 18 calls/minute = 90 weight/minute — fine. But if scanner, monitor, and signal generator all poll simultaneously, weight accumulates.

**Prevention:**
- Use a single shared HTTP client with rate limit tracking
- Prefer Binance WebSocket streams for position/order updates instead of REST polling
- Implement exponential backoff on 429 responses; log rate limit warnings before hitting hard limits

**Phase to address:** Position Monitor implementation phase

---

### Pitfall 12: Chart Generation Blocking Telegram Response

**What goes wrong:**
mplfinance chart generation with OB/FVG zones, two indicator panels, and PNG export takes 2-5 seconds per chart. If this runs synchronously in the Telegram handler, aiogram's event loop blocks for that duration. All other Telegram interactions (including other user commands) queue up.

**Prevention:**
- Run chart generation in `asyncio.get_event_loop().run_in_executor(None, generate_chart, ...)` to offload to thread pool
- Pre-generate charts at signal detection time, not at message send time
- Use `asyncio.create_task` for chart generation; send "Analyzing..." message immediately, then edit with chart when ready

**Phase to address:** Chart Generator + Telegram integration phase

---

### Pitfall 13: Strategy Auto-Expiry Triggering During Active Position

**What goes wrong:**
A strategy expires (review_interval_days elapsed) while a position opened under that strategy is still active. The bot either keeps managing the position with a "dead" strategy or the SL/TP levels reference strategy parameters that are no longer in DB.

**Prevention:**
- Strategy expiry must check for active positions using that strategy; defer expiry until position closes
- Store SL/TP levels directly on the position record at entry time — never re-derive from strategy at management time

**Phase to address:** Strategy lifecycle + Position Monitor integration

---

## Technical Debt Patterns

Shortcuts that feel fine initially but cause rewrites at scale.

| Pattern | What It Causes | When It Bites | Better Approach |
|---------|---------------|---------------|-----------------|
| Hardcoding pair-specific settings (min_notional, leverage limits) | Breaks when Binance changes pair specs | On first altcoin trade, or after exchange maintenance | Fetch from `exchangeInfo` at startup; cache in DB |
| Single `config.json` for all risk parameters | Can't A/B test changes; hard to audit why a trade was sized a given way | After first unexplained large loss | Snapshot config at trade entry; store in DB with trade record |
| Bot state in memory only (current strategy, stake level) | Bot restart loses state; position monitoring stops | First VPS reboot or crash | All state in PostgreSQL; bot reconstructs state from DB on startup |
| Using market orders for all entries | 0.04% taker fee vs 0.02% maker fee — doubles transaction cost | After 100+ trades, noticeable P&L drag | Use limit orders near BBO for entries; market order only for emergency exits |
| Telegram message edits for status updates | If original message is deleted by user, edit fails with exception | Immediately on first user cleanup | Handle `MessageNotModified` and `MessageToEditNotFound` exceptions gracefully |

---

## Integration Gotchas

Issues specific to how this stack's components interact.

| Integration Point | Gotcha | Mitigation |
|-------------------|--------|------------|
| aiogram 3.x + APScheduler | Both use asyncio; sharing event loop requires `AsyncIOScheduler` — not `BackgroundScheduler`. Using BackgroundScheduler in an async app causes "no current event loop" errors | Initialize `AsyncIOScheduler` inside the async startup handler, not at module level |
| python-binance testnet | `testnet=True` only works for USDT-M futures with `AsyncClient.create(testnet=True)` — spot testnet has different endpoint now (`demo-api.binance.com`). Futures testnet URL is `testnet.binancefuture.com` | Explicitly set `futures_url` in client; never rely on library defaults for testnet routing |
| SQLAlchemy async + PostgreSQL | `async_session` cannot be shared across coroutines directly — each task needs its own session. Sharing sessions in concurrent async handlers causes `DetachedInstanceError` | Use `sessionmaker` with `async_scoped_session` or pass session factory, not session instance |
| Claude code_execution + OHLCV data | Code execution sandbox does not persist files between API calls. If Claude writes a CSV and then a second call tries to read it, the file is gone | All data must be passed inline or regenerated per call; treat each code_execution call as stateless |
| mplfinance + Docker | mplfinance requires a display server for rendering. In headless Docker containers, default matplotlib backend raises `_tkinter` errors | Set `MPLBACKEND=Agg` in Docker environment; use `matplotlib.use('Agg')` before any import of mplfinance |
| Binance WebSocket + asyncio reconnect | python-binance WebSocket streams disconnect silently after ~24h or on exchange maintenance. The bot continues without realizing it's receiving no data | Implement heartbeat monitoring; restart stream if no message received in 30 seconds |

---

## Security Mistakes

Specific to this bot's architecture.

| Mistake | Consequence | Prevention |
|---------|-------------|------------|
| Logging API keys in debug mode | Keys leaked to log files or monitoring services | Explicitly redact `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `ANTHROPIC_API_KEY` from all log formatters |
| Chat ID validation in handler only (not middleware) | If chat ID check is bypassed by a code bug, any Telegram user can trigger trades | Use aiogram middleware for chat_id validation — it runs before any handler, cannot be bypassed |
| Storing API keys in DB instead of env | DB compromise = all keys exposed | Keys in `.env` only; DB stores only non-sensitive config |
| Binance API without IP whitelist | Key theft enables trades from any IP | Always set IP restriction on Binance API key; even without withdrawal permission, trading access is dangerous |
| No command rate limiting in Telegram | Flood of `/confirm` callbacks can be replayed or spammed | Throttle middleware on sensitive commands; use nonces in callback_data to prevent replay |

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Market Scanner | Selecting pairs that are untradeable at $100 | Filter by `min_notional` at current account size before adding to candidate list |
| Strategy Generator (Claude) | Overfit strategies passing filter | Enforce train/validation split in Claude prompt; require 30+ trade sample |
| Signal Generator | Look-ahead bias in SMC pattern detection | Use only closed candles (`df.iloc[:-1]`); write regression test |
| Risk Manager | Leverage + isolated margin liquidation math | Compute and store `liquidation_price` before any order placement |
| Order Executor | Testnet/production routing errors; partial fills | Validate environment on connect; handle all Binance error codes explicitly |
| Telegram Bot | Double-tap confirmation race condition | DB unique constraint + inline keyboard removal on confirm |
| Position Monitor | Silent WebSocket disconnection | Heartbeat with stream restart; never rely on stream alone for SL/TP |
| Strategy Lifecycle | Expiry during active position | Block expiry if open positions reference the strategy |
| Production Switch | Stale testnet state in DB | Wipe/archive testnet records; validate `environment` tags before going live |

---

## Sources

- [Common Pitfalls to Avoid When Building Your First Crypto Trading Bot](https://coinbureau.com/guides/crypto-trading-bot-mistakes-to-avoid/) — MEDIUM confidence
- [Binance: How Liquidation Works in Futures Trading](https://www.binance.com/en/support/faq/how-liquidation-works-in-futures-trading-7ba80e1b406f40a0a140a84b3a10c387) — HIGH confidence (official)
- [Binance: Introduction to Futures Funding Rates](https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031) — HIGH confidence (official)
- [Binance: Leverage and Margin of USDT-M Futures](https://www.binance.com/en/support/faq/leverage-and-margin-of-usd%E2%93%A2-m-futures-360033162192) — HIGH confidence (official)
- [CCXT Issue: Binance Futures Testnet private API calls misrouted](https://github.com/ccxt/ccxt/issues/26487) — HIGH confidence (confirmed bug)
- [CCXT Issue: Binance Spot Testnet endpoint updated](https://github.com/ccxt/ccxt/issues/27266) — HIGH confidence (confirmed issue)
- [From Slippage to Overfitting: Common Pitfalls in Crypto Bot Trading](https://blog.bitunix.com/en/2025/06/02/common-pitfalls-crypto-trading-bots/) — MEDIUM confidence
- [Backtesting Traps: Common Errors to Avoid](https://www.luxalgo.com/blog/backtesting-traps-common-errors-to-avoid/) — MEDIUM confidence
- [Binance: What Is Slippage](https://www.binance.com/en/support/faq/what-is-slippage-01f6dd67d54e4dca902914700818e739) — HIGH confidence (official)
- [APScheduler GitHub](https://github.com/agronholm/apscheduler) — HIGH confidence (official repo)
- [Telegram Crypto Trading Bots: Convenience vs Security Risks (Hacken)](https://hacken.io/discover/telegram-crypto-trading-bots-risks/) — MEDIUM confidence
- [Building an AI Trading Bot with Claude Code — real-world cost/context analysis](https://dev.to/ji_ai/building-an-ai-trading-bot-with-claude-code-14-sessions-961-tool-calls-4o0n) — MEDIUM confidence
- [Crypto Trading Bot Pitfalls, Risks & Mistakes 2025](https://en.cryptonomist.ch/2025/08/22/crypto-trading-bot-pitfalls/) — MEDIUM confidence
