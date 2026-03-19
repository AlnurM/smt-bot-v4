# Roadmap: Crypto Futures Trading Bot (CTB)

## Overview

Six phases take the project from zero to a production-ready semi-automated trading bot. Phase 1 builds the foundation that every later component depends on. Phase 2 proves the AI strategy pipeline in isolation. Phase 3 wires signal generation and risk management into a verifiable trading logic layer. Phase 4 delivers the Telegram interface — the only UI. Phase 5 closes the trade loop with order execution and position monitoring. Phase 6 adds reporting, Pine Script, skipped-coin transparency, and the audit trails that make the system trustworthy before live funds touch it.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Docker stack, PostgreSQL, Alembic, Binance client, async app skeleton (completed 2026-03-19)
- [x] **Phase 2: Strategy Pipeline** - Market Scanner, Claude strategy generation, filter, lifecycle management (completed 2026-03-19)
- [ ] **Phase 3: Signal and Risk** - SMC + MACD/RSI signal generation, risk manager, chart generator
- [ ] **Phase 4: Telegram Interface** - Full Telegram bot, signal dispatch, confirm/reject flow, settings commands
- [ ] **Phase 5: Order Execution and Position Monitoring** - Binance order placement, SL/TP bracket, position monitor, dry-run
- [ ] **Phase 6: Reporting and Audit** - Daily summary, Pine Script, skipped coins, per-signal audit trail

## Phase Details

### Phase 1: Foundation
**Goal**: A running, crash-free application skeleton where the database, exchange client, and scheduler are wired together and verifiable before any trading logic exists
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INFRA-07, INFRA-08
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts both the app container and PostgreSQL with no errors; app logs confirm DB connection
  2. Alembic migrations run to completion and all required tables exist in PostgreSQL
  3. Bot connects to Binance Futures Testnet when `BINANCE_ENV=testnet` and to Production when set to `production` — confirmed by logging the active endpoint on startup
  4. APScheduler fires a test job on schedule with no drift after 3+ cycles
  5. On `SIGTERM`, open scheduler jobs stop cleanly and a "shutdown complete" log line appears with no exceptions
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffold, Docker Compose, pydantic-settings config, loguru, pytest Wave 0 infrastructure
- [x] 01-02-PLAN.md — All 10 SQLAlchemy ORM models, async session factory, Alembic initial migration with seed data
- [x] 01-03-PLAN.md — Binance client wrapper (testnet/production switch), APScheduler, main.py startup sequence, graceful shutdown, position sync

### Phase 2: Strategy Pipeline
**Goal**: The bot can autonomously discover tradeable coins, generate a non-overfit SMC+MACD/RSI strategy via Claude, validate it against configurable criteria, and store versioned strategies in PostgreSQL
**Depends on**: Phase 1
**Requirements**: SCAN-01, SCAN-02, SCAN-03, SCAN-04, STRAT-01, STRAT-02, STRAT-03, STRAT-04, STRAT-05, FILT-01, FILT-02, FILT-03, FILT-04, FILT-05, LIFE-01, LIFE-02, LIFE-03, LIFE-04, LIFE-05
**Success Criteria** (what must be TRUE):
  1. Hourly scan produces a ranked list of top-N USDT-M Perpetual coins by volume, filtered by MIN_NOTIONAL threshold, visible in DB
  2. Claude generates a strategy JSON containing all required fields (MACD/RSI params, SMC params, entry/exit conditions, backtest results) using `code_execution` with train/validation split
  3. A strategy that fails filter criteria (e.g., drawdown worse than threshold) is rejected and logged with the specific failed criteria
  4. A passing strategy is persisted in PostgreSQL with `is_active=true` and a full criteria snapshot; prior version is preserved with `is_active=false`
  5. Strategy Manager skips re-generation when an active, non-expired strategy already exists for a coin
**Plans**: 4 plans

Plans:
- [ ] 02-00-PLAN.md — Wave 0: anthropic_api_key in Settings, .env.example update, 19 failing test scaffolds across 4 files
- [ ] 02-01-PLAN.md — Market Scanner: top-N by volume from whitelist, CronTrigger job, OHLCV fetch with minimum history check
- [ ] 02-02-PLAN.md — Claude Strategy Engine: Files API + code_execution, walk-forward prompt, Pydantic schema validation, typed exceptions
- [ ] 02-03-PLAN.md — Strategy Filter (strict/relaxed modes) + Strategy Manager (save, expire, version, criteria snapshot) + APScheduler wiring in main.py

### Phase 3: Signal and Risk
**Goal**: Given an active strategy, the bot detects live trade signals using SMC and indicator logic, sizes positions safely, and renders a chart image — all verifiable without Telegram or order placement
**Depends on**: Phase 2
**Requirements**: SIG-01, SIG-02, SIG-03, SIG-04, SIG-05, SIG-06, RISK-01, RISK-02, RISK-03, RISK-04, RISK-05, RISK-06, RISK-07, RISK-08, RISK-09, RISK-10, CHART-01, CHART-02, CHART-03, CHART-04, CHART-05, CHART-06, CHART-07, CHART-08, CHART-09
**Success Criteria** (what must be TRUE):
  1. Signal Generator emits a Signal object with direction, entry, SL, TP, R/R, signal strength, and reasoning text when entry conditions are met on live OHLCV data
  2. SMC detector identifies Order Blocks, Fair Value Gaps, BOS, and CHOCH using only closed candles (`df.iloc[:-1]`) — re-running at T+1 minute produces identical results
  3. Risk Manager rejects any signal where position size would fall below MIN_NOTIONAL or where liquidation price is closer than 2x the SL distance
  4. Progressive stakes advance through configured tiers on win streaks and reset to base on any loss; daily loss circuit breaker halts new signals when the daily limit is reached
  5. Chart Generator produces a PNG BytesIO object with candlesticks, OB/FVG zones, entry/SL/TP lines, MACD panel, and RSI panel within 5 seconds
**Plans**: 5 plans

Plans:
- [ ] 03-00-PLAN.md — Wave 0: requirements.txt additions (pandas-ta-classic, mplfinance), OHLCV fixture, 5 RED test scaffolds
- [ ] 03-01-PLAN.md — SMC detector (OrderBlock, FVG, BOS/CHOCH dataclasses + pure detection functions) + MACD/RSI indicator wrappers
- [ ] 03-02-PLAN.md — Signal Generator (orchestrates SMC + indicators + 4h HTF confirmation + volume + scoring → Signal dict)
- [ ] 03-03-PLAN.md — Risk Manager (position sizing formula, progressive stakes, daily circuit breaker, liquidation safety, MIN_NOTIONAL, update_risk_settings)
- [ ] 03-04-PLAN.md — Chart Generator (mplfinance multi-panel PNG, OB/FVG rectangles, BOS/CHOCH lines, entry/SL/TP lines, asyncio.to_thread, BytesIO 200 DPI)

### Phase 4: Telegram Interface
**Goal**: The trader can receive signal messages with chart images, confirm or reject trades via inline buttons, and manage all bot settings through Telegram commands — with single-user security enforced on every interaction
**Depends on**: Phase 3
**Requirements**: TG-01, TG-02, TG-03, TG-04, TG-05, TG-06, TG-07, TG-08, TG-09, TG-10, TG-11, TG-12, TG-13, TG-14, TG-15, TG-16, TG-17, TG-18, TG-20, TG-21, TG-22
**Success Criteria** (what must be TRUE):
  1. A message from any chat ID other than `ALLOWED_CHAT_ID` is silently ignored; no handler fires
  2. A signal message arrives with chart PNG attached, all required fields (direction, entry/SL/TP, R/R, stake %, reasoning), and three inline buttons: Confirm, Reject, Pine Script
  3. Tapping Confirm marks the signal as pending in DB atomically and removes the inline keyboard; a second tap on the same message has no effect
  4. All `/risk`, `/criteria`, `/settings`, `/pause`, `/resume` commands read from and write to the DB config table — changes persist across restarts
  5. `/status`, `/positions`, `/history`, `/signals`, `/strategies`, and `/skipped` commands return non-empty, accurate data when records exist
**Plans**: TBD

Plans:
- [ ] 04-01: aiogram 3.x bot skeleton, single-user middleware, `/start` `/help` `/status` basic commands
- [ ] 04-02: Signal message dispatch (chart PNG send, inline keyboard, confirm/reject callbacks, DB unique constraint, keyboard removal)
- [ ] 04-03: Settings and query commands (/risk, /criteria, /settings, /strategies, /signals, /positions, /history, /skipped, /scan, /chart, /pause, /resume)

### Phase 5: Order Execution and Position Monitoring
**Goal**: A confirmed trade signal results in an isolated-margin market order on Binance Futures with bracket SL/TP, followed by real-time monitoring and a Telegram notification when the position closes
**Depends on**: Phase 4
**Requirements**: ORD-01, ORD-02, ORD-03, ORD-04, ORD-05, MON-01, MON-02, MON-03, MON-04, MON-05
**Success Criteria** (what must be TRUE):
  1. After Confirm is tapped, a market order appears on Binance Testnet with isolated margin and the SL/TP bracket orders placed immediately after fill confirmation
  2. Order fill price and actual position size are sent to Telegram within 5 seconds of fill
  3. When SL or TP is hit, Telegram receives a notification with final PnL and close reason within one monitoring cycle
  4. A second Confirm tap (double-tap) on the same signal produces no additional order due to the DB unique constraint
  5. Order errors (MIN_NOTIONAL failure, insufficient balance, API errors) surface to Telegram immediately with a descriptive message
**Plans**: TBD

Plans:
- [ ] 05-01: Order Executor (isolated-margin entry, SL/TP bracket, all Binance error codes, partial fill handling, dry-run mode, environment validation)
- [ ] 05-02: Position Monitor (polling + WebSocket fallback, SL/TP hit detection, close notification, win streak update, daily stats aggregation, trade record creation)

### Phase 6: Reporting and Audit
**Goal**: The trader has full visibility into daily performance, skipped coins, per-signal decisions, and strategy review schedules — and TradingView cross-check is available via Pine Script on every signal
**Depends on**: Phase 5
**Requirements**: TG-19, PINE-01, PINE-02, PINE-03, SKIP-01, SKIP-02, SKIP-03, SKIP-04
**Success Criteria** (what must be TRUE):
  1. At 21:00 daily, a summary message arrives in Telegram with PnL, trade count, win rate, and current stake tier for the day
  2. Tapping "Pine Script" on a signal message or running `/chart SYMBOL` returns a copy-paste-ready Pine Script v5 block in Telegram
  3. `/skipped` returns a list of coins skipped in the last 24h or 7d with the specific criteria that caused each rejection
  4. An alert fires in Telegram when no coins pass criteria across multiple consecutive scan cycles
**Plans**: TBD

Plans:
- [ ] 06-01: Daily summary report (scheduled 21:00, PnL/trades/win rate/stake aggregation) + TG-19 scheduler job
- [ ] 06-02: Pine Script generator (v5 output with entry/SL/TP, OB zones, FVG zones, BOS/CHOCH lines) + inline button wiring + `/chart` command
- [ ] 06-03: Skipped coins tracking (log symbol/results/failed criteria, optional notification, `/skipped` with time filters, consecutive-skip alert)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete   | 2026-03-19 |
| 2. Strategy Pipeline | 4/4 | Complete   | 2026-03-19 |
| 3. Signal and Risk | 2/5 | In Progress|  |
| 4. Telegram Interface | 0/3 | Not started | - |
| 5. Order Execution and Position Monitoring | 0/2 | Not started | - |
| 6. Reporting and Audit | 0/3 | Not started | - |
