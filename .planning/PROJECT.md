# Crypto Futures Trading Bot (CTB)

## What This Is

A semi-automated crypto futures trading bot for Binance USDT-M Perpetual Futures, built and shipped as v1.0. Claude AI generates and backtests SMC + MACD/RSI strategies via code_execution, the bot detects signals with weighted scoring, sends chart-annotated trade signals to Telegram, and executes orders on Binance after manual confirmation. Position monitoring with SL/TP close detection, progressive stakes, daily loss circuit breaker, and daily performance reports complete the trade loop. The entire system runs as a single async Python process controlled through a 14-command Telegram bot.

## Core Value

The full trade loop must work end-to-end: Claude generates a strategy → bot identifies a signal → trader confirms in Telegram → order executes on Binance Futures. Everything else supports this loop.

## Requirements

### Validated

- ✓ Market Scanner selects top-N coins from curated whitelist by volume hourly — v1.0
- ✓ Claude API generates optimized SMC + MACD/RSI strategies via code_execution with walk-forward validation — v1.0
- ✓ Strategy Filter validates strategies against configurable criteria (return, drawdown, winrate, PF, trades, R/R) — v1.0
- ✓ Signal Generator applies active strategies to live market data with SMC + indicator analysis and weighted scoring — v1.0
- ✓ Risk Manager calculates position sizes with progressive stakes, liquidation safety, and daily loss circuit breaker — v1.0
- ✓ Telegram bot sends signals with chart images and inline confirm/reject buttons — v1.0
- ✓ Order Executor places confirmed trades on Binance Futures with isolated margin and SL/TP bracket — v1.0
- ✓ Chart Generator produces PNG visualizations with OB/FVG zones, entry/SL/TP levels, MACD/RSI panels — v1.0
- ✓ Pine Script v5 generator for TradingView overlay with full SMC zones — v1.0
- ✓ All trading parameters (risk, criteria, settings) manageable via Telegram commands — v1.0
- ✓ Position monitoring with SL/TP hit notifications, trade recording, win streak tracking — v1.0
- ✓ Daily summary reports at 21:00 UTC+5 (PnL, trades, win rate, stake, balance, best/worst trade) — v1.0
- ✓ Strategy lifecycle: auto-expiry, re-generation, version history, criteria snapshots — v1.0
- ✓ Skipped coins tracking with reasons, /skipped drill-down, loosen-criteria buttons — v1.0
- ✓ Dry-run mode with /dryrun toggle — v1.0

### Active

(None — v1.0 complete. Define v2 requirements via /gsd:new-milestone)

### Out of Scope

- Multi-user support — single trader only
- Spot trading — futures only (USDT-M Perpetual)
- Web UI — Telegram is the only interface
- Fully automated trading — manual confirmation required for every trade
- Mobile app — Telegram serves as the mobile interface
- Withdrawal API access — disabled for security
- Martingale position sizing — anti-martingale only (progressive on wins)
- Cross-margin — isolated margin only

## Context

- **Shipped:** v1.0 on 2026-03-20 — 7 phases, 23 plans, ~10,500 LOC Python (6,111 bot + 4,375 tests)
- **Tech stack (actual):** Python 3.12, aiogram 3.26, SQLAlchemy 2.0 + asyncpg, APScheduler 3.11.2, python-binance 1.0.35, pandas-ta-classic 0.4.47, mplfinance 0.12.10b0, anthropic SDK with code_execution, Docker Compose + PostgreSQL 16
- **Architecture:** Single async process — asyncio event loop with aiogram polling + APScheduler (4 jobs: hourly scan, daily expiry check, 60s position monitor, daily summary) + asyncpg DB pool
- **Testing:** ~150+ unit tests (pytest + pytest-asyncio), all passing. Integration verified via milestone audit.
- **Known tech debt:** Signal.caption column never populated (display-only), check_margin_type() orphaned (enforcement done elsewhere), stale VERIFICATION.md frontmatter in Phases 1/2/4

## Constraints

- **Tech stack**: Python 3.12, aiogram 3.26, PostgreSQL 16 + SQLAlchemy 2.0 + asyncpg, APScheduler 3.11.2, python-binance 1.0.35, pandas-ta-classic, mplfinance, Docker
- **Database**: PostgreSQL with Alembic migrations (5 migrations through v1.0)
- **Language**: Code/comments/logs in English, Telegram messages in Russian with English data
- **Security**: API keys in .env with SecretStr masking, Telegram restricted to single chat_id, Binance API without withdrawal permission
- **Environment**: Docker Compose for local dev, VPS deployment planned

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Semi-automated (manual confirm) | Risk control on small deposit, trader stays in the loop | ✓ Good — core safety net |
| Claude code_execution for backtesting | No separate backtest service needed | ✓ Good — works with Files API |
| PostgreSQL from start | Avoids migration later | ✓ Good — 10 tables, 5 migrations |
| Telegram-only interface | Simplicity, mobile-ready | ✓ Good — 14 commands + inline buttons |
| Progressive stakes (3→5→8%) | Capitalize on winning streaks | ✓ Good — implemented with daily circuit breaker |
| Isolated margin | Limits loss per position | ✓ Good — enforced programmatically |
| APScheduler MemoryJobStore | Avoids psycopg2 sync dependency | ✓ Good — 4 jobs, no persistence needed |
| Walk-forward 70/30 validation | Prevents overfitting in Claude backtesting | ✓ Good — mandatory in every prompt |
| Sequential Claude calls | Avoids rate limits, simpler error handling | ✓ Good — priority queue manages order |
| Curated coin whitelist | History, volume, stability criteria | ✓ Good — configurable via .env + Telegram |

---
*Last updated: 2026-03-20 after v1.0 milestone*
