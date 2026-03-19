# Project Research Summary

**Project:** Crypto Futures Trading Bot (CTB / smt-bot-v4)
**Domain:** Semi-automated crypto futures trading bot — Binance USDT-M Perpetual, SMC + MACD/RSI signals, Claude AI strategy generation, Telegram interface, single trader
**Researched:** 2026-03-19
**Confidence:** HIGH

## Executive Summary

This is a single-user, semi-automated pipeline bot for trading Binance USDT-M Perpetual futures on a small account (~$100). The expert approach — confirmed by freqtrade's production architecture and multiple trading bot surveys — is a central orchestrator pattern: data flows one-way from exchange through analysis layers to a human decision point, then outward to execution. The defining characteristic of this bot versus a basic signal forwarder is Claude AI strategy generation using the `code_execution` tool, which eliminates the need for a separate backtesting service. The entire system runs as a single Python asyncio process with aiogram (Telegram), APScheduler (jobs), and PostgreSQL (state), deployed via Docker Compose.

The recommended technical approach is clear and well-validated: Python 3.12, python-binance 1.0.35 for Binance Futures connectivity, aiogram 3.26.0 for Telegram, anthropic 0.84.0 with `code_execution` for AI strategy generation, SQLAlchemy 2.x + asyncpg + PostgreSQL 16 for persistence, and APScheduler 3.11.2 (stable) for scheduling. All components must be async throughout — aiogram and asyncpg require it, and mixing sync code risks blocking the event loop. The stack is greenfield-friendly with no painful migration paths ahead, provided PostgreSQL is used from day one.

The critical risks for this project are concentrated at two points: the Risk Manager and the Strategy Generator. On a $100 account with leverage, incorrect liquidation price math can wipe positions instantly — the Risk Manager must compute liquidation price before every order. The Claude strategy generator will produce overfit strategies if not prompted with a train/validation/test split; strategies that show 70%+ backtest winrate will often perform at 40-50% live. A secondary risk is the Testnet→Production transition: the systems must tag every DB record with an `environment` field and validate actual Binance account type on startup. Addressing these three risks before any live funds touch the system is non-negotiable.

---

## Key Findings

### Recommended Stack

The stack is fully async Python, Binance-specific (not multi-exchange), and single-process. The core decision to use python-binance over CCXT is correct for this scope — python-binance has deeper Binance Futures feature coverage (isolated margin, testnet flag, algo orders) that CCXT abstracts away. The Claude `code_execution` tool (version `codeExecution_20260120`) is the right integration for strategy generation: Claude writes and runs Python backtesting in a sandbox and returns structured JSON — no separate backtest service, no external worker queue.

Two version warnings stand out: APScheduler 4.x is explicitly marked "do NOT use in production" by its maintainer — use 3.11.2 stable exclusively. The original `pandas-ta` package may be archived by July 2026 — use `pandas-ta-classic` (the community fork) from the start.

**Core technologies:**
- Python 3.12: Runtime — async performance improvements, current LTS
- python-binance 1.0.35: Binance REST + WebSocket — deeper Futures feature coverage than CCXT
- aiogram 3.26.0: Telegram bot — async-native, FSM support for confirm/reject flows
- anthropic 0.84.0: Claude API — `code_execution` tool for AI strategy generation in sandbox
- PostgreSQL 16 + SQLAlchemy 2.0.48 + asyncpg 0.31.0: Persistence — concurrent async writes, full async ORM
- Alembic 1.18.4: DB migrations — async template, from day one
- APScheduler 3.11.2: Scheduling — `AsyncIOScheduler` for asyncio integration, NOT 4.x alpha
- pandas-ta-classic: Technical indicators — community fork of pandas-ta; original at risk of archival
- mplfinance 0.12.10b0: Chart generation — static PNG export for Telegram; set `MPLBACKEND=Agg` in Docker
- pydantic-settings 2.13.1: Config — validates all env vars at startup, type-safe

### Expected Features

The critical path for a working bot is: Market Scanner → Strategy Generator → Strategy Filter → Strategy Store → Signal Generator → Chart Generator → Telegram Delivery → Confirm/Reject → Order Executor → Position Monitor → Notifications. Every item on this path is required for the system to function at all. Everything else is additive.

**Must have (table stakes):**
- Market scanner (hourly, top-10 USDT-M perpetuals by volume) — coin universe is prerequisite for everything
- Claude strategy generation with code_execution + Strategy Filter — core differentiation and safety gate
- Signal generator (SMC + MACD/RSI conditions on live OHLCV) — the value delivery mechanism
- Telegram signal delivery with Confirm/Reject inline buttons — the only UI; must be fast
- Risk Manager: fixed-% position sizing, isolated margin, MIN_NOTIONAL check, liquidation price validation
- Order Executor: market entry + bracket SL/TP on Binance Futures Testnet
- Position monitor: poll/WebSocket for SL/TP hits, push notification to Telegram
- Settings via Telegram (/setrisk, /setleverage minimum) — bot is unusable without mobile config
- Daily summary report — scheduled PnL and trade count aggregation
- Graceful error surfacing to Telegram — silent failures leave the trader blind

**Should have (differentiators):**
- Chart PNG with OB/FVG zones, entry/SL/TP lines — far more actionable than text coordinates
- Strategy auto-expiry + version history — keeps bot adaptive as market regimes change
- Progressive stake sizing (3→5→8% on win streak, reset on loss) — anti-martingale risk control
- Daily loss circuit breaker (halt at -10% daily) — mandatory safety net for $100 account
- Pine Script generator — TradingView cross-check reduces false confirmations
- Skipped coins tracking with reasons — transparency for coin selection decisions
- Per-signal reject reason capture — builds audit trail for signal quality review

**Defer (v2+):**
- Strategy performance tracking per coin (needs 20+ trades per strategy-coin pair to be meaningful)
- Per-coin leverage recommendation from AI (useful refinement, not MVP blocker)
- WebSocket-based position monitoring (polling is adequate for MVP; upgrade for latency)
- OB/FVG chart zones (entry/SL/TP lines on plain candlestick is MVP; zones are enhancement)

**Explicit anti-features (never build):**
- Fully automated execution (no confirm step) — too dangerous on $100 with leverage
- Multi-user support, web UI, martingale sizing, cross-margin, withdrawal API access
- Spot trading, real-time streaming charts, strategy marketplace

### Architecture Approach

The system uses a central orchestrator pattern where APScheduler triggers pipeline jobs that call components in sequence — not an event bus. This is the correct choice for a single-trader, single-process bot: simpler to debug, no message broker overhead, and directly matched by freqtrade's production architecture. All components are strictly boundary-separated: Signal Generator evaluates conditions but does not size positions (Risk Manager) or render charts (Chart Generator). Strategies are stored as structured JSON in PostgreSQL, not as Python class files — this enables version history, expiry, and re-generation without code deploys. The single env var `BINANCE_TESTNET=true` is the only difference between dev and production environments, minimizing untested code paths.

**Major components:**
1. Market Scanner — hourly coin selection from Binance 24h ticker; does NOT apply strategies
2. Strategy Manager — Claude strategy lifecycle: generate, filter, persist, expire, re-generate
3. Claude Strategy Engine — pure function wrapper; takes OHLCV context, returns strategy JSON; no DB/Telegram access
4. Strategy Filter — stateless validator; configurable thresholds for return, drawdown, winrate, profit factor, sample size
5. Signal Generator — applies active strategies to live OHLCV; computes SMC (OB/FVG/BoS/ChoCH) + MACD/RSI; outputs Signal objects
6. Risk Manager — position sizing, progressive stakes, liquidation price check, MIN_NOTIONAL guard; no order placement
7. Chart Generator — mplfinance PNG renderer; pure rendering, no exchange/DB calls; runs in thread pool executor
8. Telegram Bot (aiogram 3.x) — presentation layer only; enforces single-user via middleware; routes confirms to Order Executor
9. Order Executor — places isolated-margin entry + SL/TP bracket; handles partial fills and errors
10. Database (PostgreSQL) — coins, strategies (versioned), signals, orders, positions, config tables

**Recommended project structure:**
```
bot/
├── main.py, config.py
├── exchange/        # Binance client wrapper
├── scanner/         # hourly coin ranking
├── strategy/        # manager, claude_engine, filter, pinescript
├── signals/         # generator, smc, indicators
├── risk/            # manager
├── execution/       # executor
├── charts/          # generator
├── telegram/        # bot, handlers/, keyboards
└── db/              # session, models, repositories/
```

**Dependency-driven build order:** DB layer → Exchange client → Market Scanner → Claude Engine + Filter → Strategy Manager → SMC + Indicators → Signal Generator → Risk Manager → Chart Generator → Telegram Bot → Order Executor → APScheduler wiring → Position Monitor → Daily Summary.

### Critical Pitfalls

1. **Liquidation price math blindness** — At $100 + leverage, `account_balance * risk_percent` does not equal safe position size. Compute `liquidation_price = entry * (1 - 1/(leverage * (1 + maintenance_margin_rate)))` before every order; enforce that liquidation distance >= 2x SL distance. Store `liquidation_price` on every position record. This is a hard gate before any live order execution.

2. **Claude strategy overfitting** — Claude optimizes for whatever criteria you give it; without a train/validation/test split in the prompt, backtested strategies are almost certainly overfit. Enforce: backtest on data[-90d:-30d], validate on data[-30d:-7d], reject if validation Sharpe drops >30% vs train, require 30+ trades in sample. Backtest winrate >65% with >2.5 Sharpe is a red flag. Build this into the Claude prompt and the Strategy Filter from the start.

3. **Testnet→Production silent differences** — Testnet accounts reset monthly, fill behavior differs from production, and API endpoint routing can be misrouted. Tag every DB record (order, position, strategy) with an `environment` field; validate actual Binance account type on startup; implement dry-run mode (logs orders without placing them) as a separate production rehearsal step.

4. **Telegram Confirm race condition / double execution** — At-least-once Telegram callback delivery means double-taps create duplicate orders. Use a DB-level unique constraint on `(signal_id, action='confirmed')`, update signal to `pending_execution` atomically before order placement, and remove the inline keyboard from the message after confirmation fires.

5. **Look-ahead bias in SMC pattern detection** — Pandas-based OB/FVG detection code that uses `shift(-N)` or processes the full DataFrame at once will silently use future candle data. Signal Generator must use only `df.iloc[:-1]` (closed candles only). Write a regression test: signals must be identical whether called at candle close or 1 minute into the next candle.

---

## Implications for Roadmap

Based on the dependency graph from ARCHITECTURE.md and the risk profile from PITFALLS.md, 6 phases are suggested.

### Phase 1: Foundation — Infrastructure and Exchange Client

**Rationale:** Every component in the system depends on the database layer and the exchange client wrapper. Building these first eliminates "where do I persist this?" blocking on every subsequent phase. This phase has no trading logic and is the safest to build and test in isolation.

**Delivers:** Running Docker Compose stack (bot + PostgreSQL), Alembic migration baseline, pydantic-settings config validation, python-binance client with Testnet flag, async SQLAlchemy session factory, loguru structured logging, environment tagging on all DB records.

**Addresses:** Table stakes: Testnet/production switch, persistent storage, graceful error handling foundation.

**Avoids:** Pitfall 3 (Testnet→Production differences) — `environment` field on every table from day one, never retrofitted.

**Research flag:** Standard patterns — well-documented. No phase research needed.

---

### Phase 2: Market Scanner and Strategy Pipeline

**Rationale:** The coin universe must exist before signals can be generated. The Strategy Manager/Claude Engine/Strategy Filter pipeline is the most novel component (AI-generated strategies) and needs the most iteration time — it should be built and validated in isolation before the signal loop depends on it.

**Delivers:** Hourly Market Scanner (top-10 USDT-M by volume, MIN_NOTIONAL filtered), Claude Strategy Engine (`code_execution` with train/validation split prompt), Strategy Filter (configurable thresholds: winrate, drawdown, profit factor, regime consistency), Strategy Manager lifecycle (generate, persist versioned JSON, expire), strategy_versions table.

**Addresses:** Table stakes: persistent strategy storage. Differentiators: Claude AI strategy generation, strategy filter with configurable thresholds, strategy version history.

**Avoids:** Pitfall 2 (strategy overfitting) — train/validation split in Claude prompt and filter built together; Pitfall 8 (APScheduler job drift) — Market Scanner and Strategy Generator run as separate staged jobs.

**Research flag:** Needs deeper research during planning — Claude `code_execution` prompt engineering for walk-forward validation is novel; the prompt structure for enforcing train/test split needs experimentation.

---

### Phase 3: Signal Generation and Risk Management

**Rationale:** Signal generation is the core trading logic. It must be built on top of validated strategies (Phase 2) and the exchange client (Phase 1). The Risk Manager is built in the same phase because a signal without position sizing is incomplete and cannot be safely passed to execution.

**Delivers:** SMC detector (OB, FVG, BoS, ChoCH using only closed candles), MACD/RSI indicators via pandas-ta-classic, Signal Generator (applies active strategies to live OHLCV, emits Signal objects), Risk Manager (fixed-% sizing, progressive stakes 3→5→8%, daily loss circuit breaker at -10%, liquidation price computation, MIN_NOTIONAL guard), Chart Generator (mplfinance PNG in thread pool executor).

**Addresses:** Table stakes: live signal generation, risk-based position sizing, isolated margin enforcement, MIN_NOTIONAL check. Differentiators: progressive stake sizing, chart image with OB/FVG zones.

**Avoids:** Pitfall 1 (liquidation math blindness) — liquidation_price computed and stored before any order; Pitfall 4 (progressive stakes path-to-ruin) — daily circuit breaker and stake tier validation against MIN_NOTIONAL; Pitfall 5 (look-ahead bias) — `df.iloc[:-1]` enforced with regression test; Pitfall 6 (funding rate erosion) — funding rate fetched before entry, warning in Telegram signal.

**Research flag:** Signal Generator (SMC implementation) may benefit from phase research — OB/FVG detection edge cases and SMC parameter choices are not well-standardized.

---

### Phase 4: Telegram Interface and Trade Confirmation Loop

**Rationale:** The Telegram bot is the sole UI. It must be built before Order Executor because the executor requires the confirm/reject callback infrastructure. The single-user auth middleware is a security requirement that must be in place before any order placement is possible.

**Delivers:** aiogram 3.x bot with single-user middleware (chat_id validation on every handler), signal message dispatch (chart PNG + text + Confirm/Reject inline keyboard), confirm/reject callback handler with DB unique constraint and signal status atomicity, keyboard removal after confirmation, /start /status /settings /strategies /stats commands, /setrisk and /setleverage at minimum, settings persisted to DB `config` table.

**Addresses:** Table stakes: Telegram signal delivery, manual confirmation, settings management. Security: chat_id middleware, callback nonces to prevent replay.

**Avoids:** Pitfall 5 (double execution race condition) — DB unique constraint + atomic status update + keyboard removal; Pitfall 12 (chart generation blocking event loop) — chart pre-generated in thread pool executor before send.

**Research flag:** Standard aiogram 3.x patterns. No phase research needed.

---

### Phase 5: Order Execution and Position Monitoring

**Rationale:** Execution is the final step of the trade loop and depends on all prior phases. Position monitoring is an extension of Order Executor and is built in the same phase. This is the first phase that touches real money (on Testnet), so it requires the most thorough pre-completion checklist before any production switch.

**Delivers:** Order Executor (isolated-margin entry + bracket SL/TP, all Binance error codes handled including -4164 MIN_NOTIONAL, -4164, partial fill handling), position monitor (polling primary, WebSocket heartbeat with reconnect), SL/TP hit notifications to Telegram with PnL, win streak counter update, `environment` field validated on connect, orders/positions table records with `environment` tag, dry-run mode (logs orders without placing), pre-production checklist validation milestone.

**Addresses:** Table stakes: order execution, SL/TP on every order, position monitoring, graceful error handling. Critical: testnet→production switch safety.

**Avoids:** Pitfall 3 (Testnet→Production differences) — environment validation on connect, dry-run mode, DB state archive before production switch; Pitfall 11 (rate limit accumulation) — shared HTTP client with weight tracking; Pitfall 13 (strategy expiry during active position) — expiry blocked when active positions reference strategy.

**Research flag:** Binance error codes and partial fill handling are well-documented. Dry-run mode implementation is straightforward. No phase research needed beyond official Binance Futures API docs.

---

### Phase 6: Reporting, Polish, and Production Hardening

**Rationale:** Everything needed for a working trade loop exists after Phase 5. This phase adds visibility, audit trails, and production-grade reliability before live funds are committed.

**Delivers:** Daily summary report (scheduled PnL, win rate, trade count, funding fees paid, current stake tier), Pine Script generator (string output to Telegram code block), skipped coins tracking with reasons (/skipped command), per-signal reject feedback capture, strategy performance tracking per coin (after sufficient trade history), APScheduler PostgreSQL job store (scheduler state survives restarts), config snapshot stored per trade record (audit: why was this trade sized this way), limit order support for entries (reduce taker fees).

**Addresses:** Differentiators: daily summary, Pine Script, skipped coins transparency, per-signal audit trail.

**Avoids:** Technical debt: hardcoded pair specs (fetch from exchangeInfo at startup), bot state in memory only (all state reconstructed from DB on restart), market-only orders (taker fee drag).

**Research flag:** Standard patterns. No phase research needed.

---

### Phase Ordering Rationale

- Phase 1 first because DB and exchange client are pure dependencies with no business logic — safest to build and validate before any complexity.
- Phases 2 and 3 in that order because Signal Generator requires active strategies — the strategy pipeline must produce valid output before the signal loop can run end-to-end.
- Phase 4 before Phase 5 because Order Executor requires the Telegram confirm callback — building execution without the confirm flow would require mocking it, which defers testing the actual integration.
- Phase 6 last because it adds visibility and polish on top of a working system — none of it is in the critical trade path.
- The Risk Manager (Phase 3) is built before Order Executor (Phase 5) and its liquidation math validated on paper before any order placement. This is the most important sequencing decision in the entire roadmap given the $100 account constraint.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Strategy Pipeline):** Claude `code_execution` prompt engineering for walk-forward backtesting is not well-documented. The prompt structure that reliably produces non-overfit strategies with train/validation splits needs discovery-phase experimentation. Plan for iteration budget here.
- **Phase 3 (Signal Generation):** SMC (Smart Money Concepts) pattern detection — OB/FVG/BoS/ChoCH detection parameters and confirmation logic are not standardized. The `smart-money-concepts` Python package can be used as a reference, but the implementation will require testing against known setups.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** SQLAlchemy 2.x async, Alembic, Docker Compose, python-binance — all have extensive documentation and community examples.
- **Phase 4 (Telegram):** aiogram 3.x FSM, middleware, inline keyboards — fully documented with examples.
- **Phase 5 (Execution):** Binance Futures order placement — official API docs are comprehensive; python-binance covers all required endpoints.
- **Phase 6 (Reporting):** DB aggregation queries, APScheduler PostgreSQL job store — standard patterns.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All library versions verified on PyPI as of 2026-03-19. Critical version warnings (APScheduler 4.x, pandas-ta original) confirmed from official sources. |
| Features | HIGH | Feature set derived from spec requirements + industry-standard trading bot feature surveys (2025-2026). Anti-features well-reasoned against $100 account math. |
| Architecture | HIGH | Synthesized from freqtrade production codebase (deep wiki), QuantInsti, and architectural pattern literature. Central orchestrator pattern is battle-tested for this use case. |
| Pitfalls | MEDIUM-HIGH | Liquidation math, funding rates, and testnet endpoint routing from official Binance/CCXT sources (HIGH). Overfitting, look-ahead bias, and async integration gotchas from community/practitioner sources (MEDIUM). |

**Overall confidence:** HIGH

### Gaps to Address

- **Claude prompt for walk-forward backtesting:** The exact prompt structure that reliably produces non-overfit strategies (with enforced train/validation split, regime consistency requirement, brittleness check) must be developed and tested during Phase 2. The research confirms this is necessary but does not prescribe the prompt. Budget 2-3 iterations of prompt engineering.
- **SMC detection parameter ranges:** Which lookback windows and size thresholds produce reliable OB/FVG signals on Binance USDT-M Perpetuals is not documented in research. The `smart-money-concepts` reference library provides starting defaults; validation against known historical setups is needed during Phase 3.
- **APScheduler PostgreSQL job store compatibility:** ARCHITECTURE.md notes "check 4.x compatibility with async" but the recommendation is firmly 3.x. The PostgreSQL job store in APScheduler 3.x requires `psycopg2` (sync), which means a secondary sync DB connection for scheduler state. This should be validated during Phase 1 planning — if the overhead is unacceptable, an in-memory job store (acceptable for a restartable bot) is the fallback.
- **mplfinance thread pool performance:** Chart generation time under Docker + headless Agg backend with OB/FVG overlay rendering has not been profiled. If generation exceeds 5 seconds, pre-generation at signal detection time (before Telegram send) is the mitigation already identified in PITFALLS.md.

---

## Sources

### Primary (HIGH confidence)
- [Binance: How Liquidation Works in Futures Trading](https://www.binance.com/en/support/faq/how-liquidation-works-in-futures-trading-7ba80e1b406f40a0a140a84b3a10c387) — liquidation price formula
- [Binance: Introduction to Futures Funding Rates](https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031) — funding rate mechanics
- [Binance: Leverage and Margin of USDT-M Futures](https://www.binance.com/en/support/faq/leverage-and-margin-of-usd%E2%93%A2-m-futures-360033162192) — margin math
- [CCXT Issue #26487: Binance Futures Testnet private API misrouting](https://github.com/ccxt/ccxt/issues/26487) — confirmed testnet routing bug
- [Anthropic code_execution tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool) — tool version, pricing, capabilities
- [APScheduler GitHub](https://github.com/agronholm/apscheduler) — 4.x production warning confirmed
- [Freqtrade Architecture (DeepWiki)](https://deepwiki.com/freqtrade/freqtrade) — central orchestrator pattern reference
- PyPI verified versions: aiogram 3.26.0, anthropic 0.84.0, SQLAlchemy 2.0.48, asyncpg 0.31.0, APScheduler 3.11.2, pydantic-settings 2.13.1

### Secondary (MEDIUM confidence)
- [AI Trading Bot Risk Management Guide 2025 — 3commas](https://3commas.io/blog/ai-trading-bot-risk-management-guide-2025) — position sizing, drawdown circuit breakers
- [Backtesting AI Crypto Strategies — Pitfalls (3commas)](https://3commas.io/blog/comprehensive-2025-guide-to-backtesting-ai-trading) — overfitting, look-ahead bias, survivorship bias
- [Crypto Trading Bot Architecture — QuantitativePy](https://quantitativepy.substack.com/p/building-a-crypto-trading-bot-from) — component design and build-order rationale
- [Martingale vs Anti-Martingale — WunderTrading](https://wundertrading.com/journal/en/learn/article/understanding-and-optimizing-futures-trading-with-martingale) — why martingale fails on small accounts
- [Building an AI Trading Bot with Claude Code — dev.to](https://dev.to/ji_ai/building-an-ai-trading-bot-with-claude-code-14-sessions-961-tool-calls-4o0n) — Claude context/cost analysis
- [Telegram Crypto Trading Bots: Security Risks (Hacken)](https://hacken.io/discover/telegram-crypto-trading-bots-risks/) — middleware auth patterns

### Tertiary (LOW confidence — general surveys)
- [Best Crypto Futures Trading Bots 2026](https://newyorkcityservers.com/blog/best-crypto-futures-trading-bot) — feature baseline
- [Trading Bot Checklist 2026 — DarkBot](https://darkbot.io/blog/trading-bot-checklist-2026-essential-criteria-for-crypto-success) — industry standard features
- [Smart Money Concepts Python Package](https://github.com/joshyattridge/smart-money-concepts) — OB/FVG detection reference

---
*Research completed: 2026-03-19*
*Ready for roadmap: yes*
