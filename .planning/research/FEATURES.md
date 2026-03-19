# Feature Landscape

**Domain:** Semi-automated crypto futures trading bot (Binance USDT-M Perpetual, single user, Telegram interface)
**Researched:** 2026-03-19
**Context:** $100+ deposit, SMC + MACD/RSI strategy, AI-generated strategies via Claude code_execution, manual confirm required

---

## Table Stakes

Features users (this trader) need for the system to be usable at all. Missing any of these = broken product.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Market scanner — top-N coins by volume | Without a coin universe, nothing else runs; every serious bot scans and filters pairs | Low | Hourly cadence; filter by USDT-M Perpetual only |
| Live signal generation | The core value proposition — without signals the bot has no purpose | Medium | Requires active strategy applied to real-time OHLCV data |
| Telegram signal delivery with inline buttons | The interface layer; trader must receive and act on signals from mobile | Medium | aiogram 3.x; confirm / reject buttons mandatory |
| Manual confirmation before order placement | Project constraint AND table stakes for risk control on small capital | Low | Bot must wait for reply; timeout = auto-cancel |
| Order execution on Binance Futures | The end of the trade loop; without this, it's just a signal channel | Medium | Isolated margin, market/limit, testnet switch via env |
| Stop-loss and take-profit on every order | Industry-wide expectation; trading without SL on futures = liquidation risk | Low | Place as OCO or bracket order immediately after entry |
| Position monitoring — SL/TP hit notification | Trader must know when a position closes, especially when away from screen | Medium | Binance websocket or polling; push to Telegram |
| Risk-based position sizing | Fixed lot size on small accounts will blow the account; percentage-based is required | Low | Kelly / fixed-fraction; tied to current balance |
| Isolated margin enforcement | At $100 deposit, cross-margin risks entire account on one bad trade | Low | Pass `marginType=ISOLATED` on every position open |
| MIN_NOTIONAL check before order | Binance rejects orders below ~$5-10; silent failures confuse the trader | Low | Guard in order executor before API call |
| Testnet / production switch | Required for safe development; no one ships directly to production on live funds | Low | Single env var; all infra must honor it |
| Settings management via Telegram | If the trader must SSH to change risk %, the bot is unusable in practice | Medium | Commands: /setrisk, /setleverage, /setcriteria etc. |
| Daily summary report | Trader needs to know PnL, win rate, stake level without querying anything | Low | Scheduled job; totals since midnight UTC |
| Persistent strategy storage | Strategies must survive restarts; re-generating from scratch every boot is expensive and slow | Low | PostgreSQL; strategy JSON + metadata |
| Graceful error handling to Telegram | If something fails silently the trader is blind; errors must surface as messages | Low | Catch-all handlers; format errors for non-technical reader |

---

## Differentiators

Features that make this bot meaningfully better than a basic signal forwarder. Not expected by default, but each adds real value for this use case.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Claude AI strategy generation via code_execution | Claude writes and runs Python backtesting in sandbox, then returns structured JSON strategy — no separate backtest service needed | High | Unique to this project; Claude API + tool_use; requires prompt engineering to avoid overfit strategies |
| Strategy filter with configurable thresholds | Prevents deploying weak strategies; validates return, drawdown, winrate, profit factor, min trades, R/R before activation | Medium | Configurable via Telegram or config file; strategies below threshold are logged and discarded |
| Strategy auto-expiry and re-generation | Markets change; a strategy good last month may be bad today. Lifecycle management keeps the bot adaptive | Medium | review_interval_days per strategy; expiry triggers re-gen not panic |
| Strategy version history | Lets trader audit what changed, compare generations, and roll back if a new strategy immediately loses | Medium | Postgres strategy_versions table; no hard deletes |
| Chart image with OB/FVG zones, entry/SL/TP | Signal messages with a PNG are far more actionable than text coordinates alone; trader can visually validate the setup | High | mplfinance + matplotlib; render OB box, FVG zone, entry line, SL/TP lines; attach to Telegram message |
| Pine Script generator for TradingView overlay | Trader can cross-check the signal on TradingView with the same levels; reduces false confirmations | Medium | Pure string generation; no API call needed; output as code block in Telegram |
| Skipped coins tracking with reasons | Transparency: trader understands why coins were excluded (volume, spread, no strategy, etc.) | Low | Logged to DB; queryable via /skipped command |
| Progressive stake sizing (3% → 5% → 8%) | Capitalises on win streaks, reduces exposure during losing runs; specific to project design | Low | Streak counter in DB; tier thresholds configurable |
| Per-signal reject with feedback | Trader can reject a signal and optionally log why (bad setup, news event, etc.); builds audit trail | Low | Optional free-text after reject button; stored with signal |
| Strategy performance tracking per coin | Some strategies work on BTC but fail on alts; per-coin metrics surface this over time | Medium | Requires enough trade history; meaningful only after ~20+ trades per strategy-coin pair |
| Leverage recommendation per strategy | AI-generated strategy can include an optimal leverage suggestion based on backtest volatility profile | Medium | Part of strategy JSON schema; capped at configurable max |

---

## Anti-Features

Things to deliberately NOT build. Each has a reason and a stated alternative.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Fully automated execution (no confirm step) | At $100 deposit, one bad AI-generated signal with 10x leverage can liquidate the account. Manual confirmation is the safety net | Keep the confirm/reject step; make it fast with inline buttons |
| Multi-user support | Adds auth layer, permission model, billing complexity; zero value for single-trader use case | Single chat_id whitelist in env; reject all other users at middleware level |
| Web UI / dashboard | Duplicates Telegram interface; doubles maintenance surface; no mobile story | Telegram IS the UI; invest in better Telegram UX instead |
| Martingale position sizing | Exponential doubling after losses is catastrophic on a $100 account with leverage — 10-15 consecutive losses hits account limits | Use anti-martingale (progressive stakes on wins, reset on loss) |
| Cross-margin positions | Any single bad position can drain the entire account balance in cross-margin mode | Isolated margin only, enforced programmatically |
| Withdrawal API access | Unnecessary for trading operations; dramatically increases attack surface | Binance API key without withdrawal permission; enforce at key creation |
| Spot trading | Different asset class, different risk profile, different MIN_NOTIONAL rules; scope creep | USDT-M Perpetual Futures only; spot excluded from scanner |
| Hyperparameter grid search in live strategy gen | Exhaustive search over hundreds of parameter combos takes too long and overfits to in-sample data | Claude generates a focused set of candidates, validates with walk-forward, returns best single strategy |
| Social / copy trading | Sharing signals externally or copying others adds liability, legal complexity, and latency | Single-trader only; no external signal distribution |
| Real-time streaming chart | Browser-based charting of live prices is a web UI feature; huge complexity for marginal value | Static PNG chart per signal is sufficient; trader uses TradingView for live charts |
| Notification for every candle / tick | Notification fatigue; trader disables the bot | Notify on: new signal, confirm required, SL/TP hit, daily report, errors only |
| Strategy marketplace / sharing | Out of scope for single user; signals are based on user's own risk parameters | Local strategy storage only |
| Backtesting over raw tick data | Tick data is expensive to store and process; 1m OHLCV is sufficient for SMC signals | Use 1m/5m/15m/1h OHLCV from Binance REST; Claude's sandbox handles it |

---

## Feature Dependencies

```
Market Scanner
  └─> Strategy Generator (needs coin universe to backtest against)
        └─> Strategy Filter (validates generated strategies)
              └─> Strategy Store (persists validated strategies)
                    └─> Signal Generator (applies stored strategies to live data)
                          └─> Chart Generator (renders signal visualization)
                                └─> Telegram Signal Delivery (attaches chart, shows buttons)
                                      └─> Manual Confirm / Reject
                                            └─> Order Executor
                                                  └─> Position Monitor (watches open positions)
                                                        └─> SL/TP Notification (signals position close)
                                                              └─> Daily Summary Report (aggregates closed PnL)

Risk Manager (position sizing, leverage cap, MIN_NOTIONAL check)
  └─> feeds into Order Executor

Progressive Stake Counter
  └─> feeds into Risk Manager (determines which stake tier applies)

Strategy Auto-Expiry
  └─> triggers Strategy Generator (new cycle)
  └─> requires Strategy Version History (preserves old before replacing)

Pine Script Generator
  └─> depends on Signal Generator output (needs entry/SL/TP/OB levels)
  └─> independent of Order Executor (display only)
```

**Critical path for MVP:** Market Scanner → Strategy Generator → Strategy Filter → Strategy Store → Signal Generator → Chart Generator → Telegram Delivery → Confirm → Order Executor → Position Monitor → Notification.

Everything else is additive.

---

## MVP Recommendation

**Minimum viable trade loop** — proves end-to-end system works before any polish.

### Must Have (MVP)

1. Market Scanner — hourly, top-10 coins by USDT-M volume
2. Claude strategy generation with code_execution — single strategy per coin, validated by filter
3. Signal Generator — applies strategy to live data, emits signal when conditions met
4. Chart Generator — PNG with entry, SL, TP lines (OB/FVG zones are enhancement, not MVP blocker)
5. Telegram signal delivery — message + chart + Confirm / Reject inline buttons
6. Risk Manager — fixed percentage position sizing, isolated margin, MIN_NOTIONAL guard
7. Order Executor — market entry + bracket SL/TP on Binance Testnet
8. Position Monitor — poll open positions, notify on SL/TP hit
9. Settings via Telegram — /setrisk and /setleverage at minimum
10. Daily summary — scheduled message with session PnL and trade count

### Defer to Later Phases

- Progressive stake sizing — implement after the core loop is stable and producing real trades
- Strategy auto-expiry + version history — implement once strategies are proven to degrade over time
- Pine Script generator — useful but not in the critical path; implement after MVP is confirmed working
- Skipped coins tracking with full audit — basic logging is enough for MVP
- Per-signal reject feedback / reason capture — confirm/reject is sufficient; reason logging is polish
- OB/FVG zones in chart — SMC zone rendering is High complexity; entry/SL/TP lines on plain candlestick chart is MVP

---

## Sources

- [Best Crypto Futures Trading Bots 2026](https://newyorkcityservers.com/blog/best-crypto-futures-trading-bot) — feature comparison across major platforms
- [AI Trading Bot Risk Management Guide 2025](https://3commas.io/blog/ai-trading-bot-risk-management-guide-2025) — position sizing, drawdown circuit breakers
- [Crypto Trading Bot Risk Management Strategies](https://www.fourchain.com/trading-bot/crypto-trading-bot-risk-management-strategies) — leverage management for small accounts
- [Martingale vs Anti-Martingale — Futures Risk](https://wundertrading.com/journal/en/learn/article/understanding-and-optimizing-futures-trading-with-martingale) — why martingale fails on small accounts
- [Backtesting AI Crypto Strategies — Pitfalls](https://3commas.io/blog/comprehensive-2025-guide-to-backtesting-ai-trading) — overfitting, look-ahead bias, survivorship bias
- [Trading Bot Checklist 2026](https://darkbot.io/blog/trading-bot-checklist-2026-essential-criteria-for-crypto-success) — industry-standard feature baseline
- [What Is a Crypto Signal Bot](https://wundertrading.com/journal/en/learn/article/best-signal-bots-for-crypto-traders) — signal delivery patterns, confirm-before-execute flows
- [Smart Money Concepts Python Package](https://github.com/joshyattridge/smart-money-concepts) — OB/FVG detection library reference
- [Binance Futures Bot — Position Tracking](https://github.com/hgnx/binance-position-tracking-bot) — SL/TP notification implementation reference
- [Phemex — Futures Bot Feature Overview](https://phemex.com/academy/best-crypto-exchange-trading-bots-2026) — what features are now considered standard
