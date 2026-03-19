# Architecture Patterns

**Domain:** Crypto Futures Trading Bot (Binance USDT-M Perpetual, SMC + MACD/RSI, Telegram-controlled)
**Researched:** 2026-03-19
**Confidence:** HIGH (synthesized from freqtrade production codebase, crypto bot architecture literature, and project requirements)

---

## System Overview

The system is a **semi-automated pipeline bot** organized around a central orchestrator pattern. Data flows in one direction — from exchange inward through analysis layers to a decision point, where the human confirms before execution flows back outward to the exchange.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                           │
│   Binance Futures API          Claude API          Telegram API     │
└────────────┬──────────────────────┬───────────────────┬────────────┘
             │                      │                   │
             ▼                      ▼                   ▼
┌────────────────────┐  ┌───────────────────┐  ┌───────────────────┐
│   Market Scanner   │  │  Claude Strategy  │  │   Telegram Bot    │
│  (coin selection)  │  │     Engine        │  │  (UI / commands)  │
└────────┬───────────┘  └────────┬──────────┘  └────────┬──────────┘
         │                       │                       │
         ▼                       ▼                       │
┌────────────────────┐  ┌───────────────────┐           │
│  Signal Generator  │◄─│  Strategy Manager │           │
│ (apply strategies) │  │ (lifecycle / CRUD)│           │
└────────┬───────────┘  └────────┬──────────┘           │
         │                       │                       │
         ▼                       ▼                       │
┌────────────────────┐  ┌───────────────────┐           │
│   Risk Manager     │  │  Chart Generator  │           │
│ (size / leverage)  │  │ (PNG with zones)  │           │
└────────┬───────────┘  └────────┬──────────┘           │
         │                       │                       │
         └──────────┬────────────┘                       │
                    ▼                                     │
         ┌─────────────────────┐                         │
         │  Signal Dispatcher  │─────────────────────────►
         │ (to Telegram)       │  (sends chart + buttons)│
         └──────────┬──────────┘                         │
                    │                     confirm/reject  │
                    │◄────────────────────────────────────┘
                    ▼
         ┌─────────────────────┐
         │   Order Executor    │
         │ (Binance API calls) │
         └──────────┬──────────┘
                    │
                    ▼
         ┌─────────────────────┐
         │      Database       │
         │ (PostgreSQL / ORM)  │
         └─────────────────────┘
```

**Core loop (simplified):**
```
APScheduler tick
  → Market Scanner selects top-N coins
  → Strategy Manager provides active strategies per coin
  → Signal Generator evaluates each coin/strategy pair
  → If signal found: Risk Manager sizes it, Chart Generator renders it
  → Signal Dispatcher sends Telegram message with confirm/reject
  → On confirm: Order Executor places order on Binance
  → Database records everything
```

---

## Component Responsibilities

### Market Scanner
**Responsibility:** Hourly job that queries Binance for all USDT-M perpetual symbols, ranks by 24h volume, returns top-N coins.

**Inputs:** Binance REST API (exchange info + 24h ticker)
**Outputs:** List of symbol strings persisted to DB; made available to Signal Generator
**Communicates with:** Binance API (inbound), Database (write), APScheduler (trigger)

**Boundary:** Does NOT apply strategies or generate signals. It only ranks and filters symbols. Strategy assignment is Strategy Manager's job.

---

### Strategy Manager
**Responsibility:** Owns the full lifecycle of strategies: request generation from Claude, validate via Strategy Filter, persist, serve to Signal Generator, expire after review_interval_days, trigger re-generation.

**Inputs:** Trigger (APScheduler or manual Telegram command), active coin list from DB
**Outputs:** Persisted strategy records in DB; active strategy lookup for Signal Generator
**Communicates with:** Claude Strategy Engine (request/response), Strategy Filter (validate before persist), Database (write/read), Telegram Bot (status notifications)

**Boundary:** Does NOT apply strategies to live data. That is Signal Generator's job.

---

### Claude Strategy Engine
**Responsibility:** Wraps the Anthropic API. Assembles prompt with coin symbol + OHLCV context, requests code_execution to write and run Python backtest, parses returned JSON strategy.

**Inputs:** Symbol, timeframe, recent OHLCV data, parameter bounds
**Outputs:** Structured strategy dict (entry conditions, SL/TP rules, parameter values, backtest stats)
**Communicates with:** Anthropic Claude API, called by Strategy Manager only

**Boundary:** Pure function from the caller's perspective — takes context, returns strategy or raises. No DB access. No Telegram access.

---

### Strategy Filter
**Responsibility:** Validates a candidate strategy against configurable thresholds (min return, max drawdown, min winrate, min profit factor, min trades, min R/R).

**Inputs:** Strategy dict + config thresholds
**Outputs:** Pass/fail with reason
**Communicates with:** Called by Strategy Manager only; reads config from DB or env

**Boundary:** Stateless validator. No external I/O.

---

### Signal Generator
**Responsibility:** Scheduled job that applies each active strategy to current OHLCV data for its assigned coin. Computes SMC structure (OB, FVG, BoS, ChoCH) and MACD/RSI values. Produces a Signal object when conditions are met.

**Inputs:** Active strategies from DB, OHLCV data from Binance (via data fetcher)
**Outputs:** Signal objects passed to Risk Manager and Chart Generator
**Communicates with:** Database (read strategies), Binance API (OHLCV), Risk Manager, Chart Generator

**Boundary:** Signal Generator evaluates conditions. It does NOT calculate position size (Risk Manager) and does NOT render charts (Chart Generator). One output: a Signal describing what to trade and why.

---

### Risk Manager
**Responsibility:** Given a signal and account state, computes: position size (USDT), leverage, isolated margin amount. Enforces MAX concurrent positions. Applies progressive stake logic (3% → 5% → 8% based on win streak). Checks Binance MIN_NOTIONAL.

**Inputs:** Signal object, account balance from DB (or live Binance query), open position count
**Outputs:** Annotated signal with size/leverage or a rejection if risk limits exceeded
**Communicates with:** Signal Generator (receives signal), Binance API (optional live balance check), Database (open position count)

**Boundary:** No order placement. No Telegram. Pure calculation + validation.

---

### Order Executor
**Responsibility:** Places orders on Binance Futures after human confirmation. Creates isolated-margin market/limit entry + stop-loss + take-profit orders atomically. Handles errors and partial fills. Monitors open positions for SL/TP hits.

**Inputs:** Confirmed signal (from Telegram callback), strategy parameters
**Outputs:** Order records in DB, confirmation message to Telegram Bot
**Communicates with:** Binance Futures API, Database (write orders/positions), Telegram Bot (confirmation + position update messages)

**Boundary:** Only executes what it receives. Does not re-evaluate signals. Does not size positions (Risk Manager did that).

---

### Chart Generator
**Responsibility:** Produces PNG candlestick charts using mplfinance. Annotates with OB rectangles, FVG bands, BoS/ChoCH markers, entry/SL/TP lines, MACD panel, RSI panel.

**Inputs:** OHLCV DataFrame, signal object (entry, SL, TP, OB/FVG zone coordinates)
**Outputs:** PNG bytes in memory (not persisted to disk by default)
**Communicates with:** Called by Signal Generator pipeline; output goes to Telegram Bot

**Boundary:** Pure rendering. No exchange calls. No DB writes. Deterministic given same inputs.

---

### Telegram Bot (aiogram 3.x)
**Responsibility:** Single-user interface for everything. Sends signal notifications (chart + text + inline keyboard). Receives confirm/reject callbacks. Handles /settings, /status, /stats, /strategies commands. Enforces single-user authorization by chat_id.

**Inputs:** aiogram dispatcher (webhook or polling), callbacks from Order Executor and Strategy Manager
**Outputs:** Messages to Telegram, callbacks routed to Order Executor
**Communicates with:** All components that need to notify the user; Order Executor for confirm/reject

**Boundary:** Presentation layer only. Does not contain trading logic. All commands delegate to appropriate service.

---

### Database (PostgreSQL + SQLAlchemy)
**Responsibility:** Persistent state for everything: coins, strategies (with version history), signals, orders, positions, account stats, config.

**Key tables:**
- `coins` — symbol, last_selected_at, skip_reason
- `strategies` — symbol, version, parameters, backtest_stats, active, expires_at
- `signals` — strategy_id, entry, sl, tp, side, created_at, status
- `orders` — signal_id, binance_order_id, status, filled_at
- `positions` — order_id, entry_price, current_price, pnl, status
- `config` — key/value for runtime-tunable parameters

**Communicates with:** Every component reads/writes through SQLAlchemy ORM

**Boundary:** No business logic in DB layer. All validation happens before persistence.

---

## Recommended Project Structure

```
smt-bot-v4/
├── bot/
│   ├── __init__.py
│   ├── main.py                  # entry point — wires everything, starts scheduler + bot
│   ├── config.py                # settings from env (pydantic-settings)
│   │
│   ├── exchange/
│   │   ├── __init__.py
│   │   ├── client.py            # Binance API wrapper (python-binance or ccxt)
│   │   └── models.py            # exchange-specific DTOs
│   │
│   ├── scanner/
│   │   ├── __init__.py
│   │   └── market_scanner.py    # hourly coin ranking
│   │
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── manager.py           # lifecycle: create, expire, re-generate
│   │   ├── claude_engine.py     # Anthropic API wrapper
│   │   ├── filter.py            # validation against thresholds
│   │   └── pinescript.py        # Pine Script generator
│   │
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── generator.py         # applies strategies to live OHLCV
│   │   ├── smc.py               # OB/FVG/BoS/ChoCH detection
│   │   └── indicators.py        # MACD, RSI via pandas-ta
│   │
│   ├── risk/
│   │   ├── __init__.py
│   │   └── manager.py           # position sizing, progressive stakes, MIN_NOTIONAL
│   │
│   ├── execution/
│   │   ├── __init__.py
│   │   └── executor.py          # place orders, monitor SL/TP
│   │
│   ├── charts/
│   │   ├── __init__.py
│   │   └── generator.py         # mplfinance PNG renderer
│   │
│   ├── telegram/
│   │   ├── __init__.py
│   │   ├── bot.py               # aiogram app setup, dispatcher
│   │   ├── handlers/
│   │   │   ├── commands.py      # /start /status /settings /strategies /stats
│   │   │   └── callbacks.py     # confirm/reject inline button handlers
│   │   └── keyboards.py         # InlineKeyboardMarkup builders
│   │
│   └── db/
│       ├── __init__.py
│       ├── session.py           # async engine + session factory
│       ├── models.py            # SQLAlchemy ORM models
│       └── repositories/        # one repo class per model group
│           ├── strategy_repo.py
│           ├── signal_repo.py
│           └── position_repo.py
│
├── alembic/                     # DB migrations
├── tests/
├── .env
├── docker-compose.yml
└── Dockerfile
```

---

## Data Flow

### Flow 1: Hourly Coin Selection

```
APScheduler (hourly)
  → MarketScanner.run()
      → Binance REST: GET /fapi/v1/ticker/24hr
      → rank by quoteVolume
      → write top-N to coins table
```

### Flow 2: Strategy Generation

```
APScheduler (daily or on-demand)
  → StrategyManager.generate_for_coin(symbol)
      → fetch recent OHLCV from Binance
      → ClaudeEngine.request_strategy(symbol, ohlcv)
          → POST to Anthropic API (code_execution enabled)
          → Claude writes backtest Python → executes in sandbox
          → returns JSON strategy
      → StrategyFilter.validate(strategy)
          → if PASS: persist to strategies table (new version)
          → if FAIL: log reason, optionally retry
      → notify Telegram: "New strategy for BTC/USDT generated"
```

### Flow 3: Signal Detection (core loop, every N minutes)

```
APScheduler (5–15 min interval, configurable)
  → SignalGenerator.scan()
      → for each active coin:
          → fetch fresh OHLCV (1h + 15m)
          → for each active strategy for that coin:
              → SMC.detect(ohlcv) → OB/FVG zones
              → Indicators.compute(ohlcv) → MACD, RSI values
              → evaluate entry conditions
              → if signal found:
                  → RiskManager.size(signal, account) → sized signal or reject
                  → if sized:
                      → ChartGenerator.render(ohlcv, signal) → PNG bytes
                      → TelegramBot.send_signal(signal, chart_png)
```

### Flow 4: Trade Confirmation and Execution

```
User taps "Confirm" in Telegram
  → aiogram callback_query handler
      → OrderExecutor.execute(signal_id)
          → POST /fapi/v1/order (entry, isolated margin)
          → POST /fapi/v1/order (stop-loss)
          → POST /fapi/v1/order (take-profit)
          → write order records to DB
          → TelegramBot.send("Order placed: BTC/USDT LONG @ 45000")
```

### Flow 5: Position Monitoring

```
APScheduler (1–2 min interval)
  → OrderExecutor.monitor_positions()
      → for each open position:
          → GET /fapi/v2/positionRisk
          → if SL or TP hit:
              → update position status in DB
              → TelegramBot.send("TP hit: +$12.40 (+2.3%)")
              → update win streak counter → adjusts next stake level
```

### Flow 6: Daily Summary

```
APScheduler (daily at configured time)
  → DB aggregate query: trades today, PnL, win rate, current stake %
  → TelegramBot.send(formatted daily report)
```

---

## Integration Points

### Binance Futures API
- **Library:** python-binance (preferred for testnet support) or ccxt with exchange-specific config
- **Testnet toggle:** Single `BINANCE_TESTNET=true` env var switches base URL
- **Endpoints used:** ticker/24hr (scanner), klines (OHLCV), account (balance), positionRisk (monitoring), order (execution)
- **Auth:** API key + secret from .env; no withdrawal permission needed or wanted
- **Rate limits:** Weight-based; scanner and OHLCV fetches should be batched and cached

### Anthropic Claude API
- **Used only by:** ClaudeEngine — no other component calls it directly
- **Model:** claude-3-5-sonnet (or latest available with code_execution)
- **Tool:** code_execution enabled — Claude writes Python backtest and runs it in sandbox
- **Response parsing:** Expect structured JSON; define a Pydantic model for validation
- **Cost control:** Cache OHLCV context; avoid re-generating strategy for coin that already has a valid one

### Telegram (aiogram 3.x)
- **Mode:** Polling during development; webhook on VPS
- **Auth:** Check `message.from_user.id == ALLOWED_CHAT_ID` on every handler
- **Async:** aiogram 3.x is fully async; all DB and API calls must be awaitable
- **Bot token:** .env only

### PostgreSQL
- **Driver:** asyncpg (async SQLAlchemy engine)
- **ORM:** SQLAlchemy 2.x with async session
- **Migrations:** Alembic from day one
- **Connection:** Single async engine, scoped async session per request/job

### APScheduler
- **Version:** APScheduler 3.x (or 4.x — check compatibility with async)
- **Backend:** AsyncIOScheduler for async jobs
- **Persistence:** Use PostgreSQL job store for scheduler state (avoids re-running jobs after restart)
- **Key jobs:** market_scan (hourly), signal_scan (5–15 min), position_monitor (1–2 min), daily_summary (daily cron)

---

## Suggested Build Order

The dependency graph dictates this sequence:

```
1. Database layer (models, session, Alembic migrations)
   └─ Everything depends on DB; build first

2. Exchange client wrapper
   └─ Scanner and Signal Generator both need it

3. Market Scanner
   └─ Produces the coin list that Strategy Manager and Signal Generator consume

4. Claude Strategy Engine + Strategy Filter
   └─ Strategy Manager depends on both

5. Strategy Manager
   └─ Signal Generator needs active strategies

6. SMC + Indicators (smc.py, indicators.py)
   └─ Core of Signal Generator; isolate for unit testing

7. Signal Generator
   └─ Core loop; depends on 2, 5, 6

8. Risk Manager
   └─ Depends on Signal Generator output and DB (positions)

9. Chart Generator
   └─ Depends on Signal Generator output (zones, levels)

10. Telegram Bot (commands + basic messaging)
    └─ Needed before Order Executor so confirm/reject exists

11. Order Executor
    └─ Depends on Telegram confirm callback and Exchange client

12. APScheduler wiring
    └─ Wire all jobs together; requires all components complete

13. Position Monitoring
    └─ Extension of Order Executor; add after basic execution works

14. Daily Summary + reporting
    └─ DB aggregation; add last
```

**Why this order:**
- DB first avoids "where do I persist this?" blocking every other component
- Exchange client early because OHLCV fetching is needed for strategy generation AND signal generation
- Strategy path (3→4→5) before signal path (6→7) because signals require active strategies
- Telegram before Order Executor because the executor needs the confirm callback infrastructure
- APScheduler wired last because it connects all the others into a running system

---

## Key Architectural Decisions

### Central Orchestrator vs. Pure Event Bus
**Decision:** Central orchestrator (APScheduler jobs call components directly).
**Why:** Event buses add indirection complexity that is not justified for a single-user bot with fewer than 10 concurrent jobs. Freqtrade-style orchestrator is simpler to debug and extend.

### Async Throughout
**Decision:** All components use async/await.
**Why:** aiogram 3.x requires async. asyncpg requires async. Mixing sync code introduces blocking risks. SQLAlchemy 2.x async sessions are mature enough for this use case.

### Strategy as Data, Not Code
**Decision:** Strategies are stored as structured JSON in PostgreSQL, not as Python class files.
**Why:** Claude generates strategy parameters, not Python classes. Storing as JSON enables version history, expiry, filtering, and re-generation without code deploys.

### Single-Process Architecture
**Decision:** All components run in one Python process.
**Why:** Single trader, single server, low throughput. No message queue or microservices needed. APScheduler manages concurrent jobs within one asyncio event loop.

### Testnet Parity
**Decision:** BINANCE_TESTNET env var is the only difference between dev and prod.
**Why:** Minimizes untested code paths. Every execution code path is exercised on testnet before touching real funds.

---

## Scalability Notes

This architecture is intentionally scoped to a single trader. If requirements change:

| Concern | Current approach | Would need |
|---------|-----------------|-----------|
| Multiple users | Single chat_id auth | User table, per-user config, message routing |
| Higher frequency | 5-min scan loop | WebSocket streams, async event processing |
| More exchanges | Binance-only client | CCXT abstraction layer (already used by freqtrade) |
| Strategy parallelism | Sequential scan | Background workers or asyncio.gather |

None of these are needed now. The current design avoids premature complexity.

---

## Sources

- [Freqtrade Architecture (DeepWiki)](https://deepwiki.com/freqtrade/freqtrade) — production-grade open-source trading bot; strong architectural reference
- [Crypto Trading Bot Architecture — Why Architecture Matters](https://quantitativepy.substack.com/p/building-a-crypto-trading-bot-from) — practical component design and build-order rationale
- [Stock Trading Bot Architecture: Core Components](https://medium.com/@halljames9963/stock-trading-bot-architecture-core-components-explained-d46f5d77c019) — component responsibilities breakdown
- [Automated Trading System Architecture (QuantInsti)](https://www.quantinsti.com/articles/automated-trading-system/) — industry-standard layer descriptions
- [Architectural Design Patterns for HFT Bots](https://medium.com/@halljames9963/architectural-design-patterns-for-high-frequency-algo-trading-bots-c84f5083d704) — event-driven vs pipeline patterns
