# Crypto Futures Trading Bot (CTB)

## What This Is

A semi-automated crypto futures trading bot for Binance USDT-M Perpetual Futures, designed for a single trader with a $100+ starting deposit. The bot uses Claude AI to generate and backtest SMC + MACD/RSI strategies, sends trade signals via Telegram with chart visualizations, and executes trades on Binance after manual confirmation. The entire system is controlled through a Telegram bot interface.

## Core Value

The full trade loop must work end-to-end: Claude generates a strategy → bot identifies a signal → trader confirms in Telegram → order executes on Binance Futures. Everything else supports this loop.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Market Scanner selects top-N coins by volume hourly
- [ ] Claude API generates optimized SMC + MACD/RSI strategies via code_execution backtesting
- [ ] Strategy Filter validates strategies against configurable criteria (return, drawdown, winrate, PF, trades, R/R)
- [ ] Signal Generator applies active strategies to live market data and produces trade signals
- [ ] Risk Manager calculates position sizes with progressive stakes and leverage
- [ ] Telegram bot sends signals with chart images and inline confirm/reject buttons
- [ ] Order Executor places confirmed trades on Binance Futures (Testnet first, Production via env switch)
- [ ] Chart Generator produces PNG visualizations with OB/FVG zones, entry/SL/TP levels, MACD/RSI panels
- [ ] Pine Script generator for TradingView overlay
- [ ] All trading parameters (risk, criteria, settings) manageable via Telegram commands
- [ ] Position monitoring with SL/TP hit notifications
- [ ] Daily summary reports (PnL, trades, win rate, current stake)
- [ ] Strategy lifecycle: auto-expiry after review_interval_days, re-generation, version history
- [ ] Skipped coins tracking with reasons and history

### Out of Scope

- Multi-user support — single trader only
- Spot trading — futures only (USDT-M Perpetual)
- Web UI — Telegram is the only interface
- Fully automated trading — manual confirmation required for every trade
- Mobile app — Telegram serves as the mobile interface
- Real-time chat / social features
- Withdrawal API access — disabled for security

## Context

- **Trading approach**: Smart Money Concepts (SMC) — Order Blocks, Fair Value Gaps, Break of Structure, Change of Character — combined with MACD and RSI indicators for confirmation
- **AI component**: Claude API with code_execution tool — Claude writes Python backtesting code, runs it in sandbox, optimizes parameters, returns strategy as structured JSON
- **Small deposit reality**: $100 starting capital means MIN_NOTIONAL checks are critical, max 2-3 concurrent positions recommended, isolated margin mandatory
- **Testnet-first**: All development and testing on Binance Futures Testnet. Production switch is a single env variable change
- **Existing keys**: Binance Testnet API keys and Anthropic API key (with code_execution) are ready

## Constraints

- **Tech stack**: Python 3.11+, aiogram 3.x, PostgreSQL + SQLAlchemy, APScheduler, python-binance/CCXT, pandas-ta, mplfinance, Docker
- **Database**: PostgreSQL from day one (no SQLite phase)
- **Language**: Code/comments/logs in English, Telegram messages and user-facing strings in Russian
- **Security**: API keys in .env only, Telegram restricted to single chat_id, Binance API without withdrawal permission, IP whitelist
- **Environment**: Local development, VPS deployment later
- **Binance limits**: MIN_NOTIONAL ~$5-10 per order, isolated margin required at small deposit sizes

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Semi-automated (manual confirm) | Risk control on small deposit, trader stays in the loop | — Pending |
| Claude code_execution for backtesting | No separate backtest service needed, Claude writes and runs Python in sandbox | — Pending |
| PostgreSQL from start | Single-user but avoids SQLite→Postgres migration later | — Pending |
| Telegram-only interface | Simplicity, mobile-ready, no web UI to build | — Pending |
| Progressive stakes (3→5→8%) | Capitalize on winning streaks while capping risk | — Pending |
| Isolated margin | Limits loss to allocated margin per position, critical at $100 deposit | — Pending |

---
*Last updated: 2026-03-19 after initialization*
