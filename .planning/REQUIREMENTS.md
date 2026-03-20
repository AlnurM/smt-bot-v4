# Requirements: Crypto Futures Trading Bot (CTB)

**Defined:** 2026-03-19
**Core Value:** The full trade loop must work end-to-end: Claude generates a strategy → bot identifies a signal → trader confirms in Telegram → order executes on Binance Futures.

## v1 Requirements

### Infrastructure

- [x] **INFRA-01**: System connects to Binance Futures Testnet or Production based on single env variable (`BINANCE_ENV`)
- [x] **INFRA-02**: All API keys stored in `.env` file, never in code or version control
- [x] **INFRA-03**: PostgreSQL database with all required tables created via Alembic migrations
- [x] **INFRA-04**: APScheduler runs hourly market scan and scheduled jobs without drift or missed triggers
- [x] **INFRA-05**: Application runs as single async process (asyncio event loop with aiogram + APScheduler + asyncpg)
- [x] **INFRA-06**: Docker Compose configuration for local development (app + PostgreSQL)
- [x] **INFRA-07**: Graceful shutdown — open positions synced, scheduler stopped cleanly
- [x] **INFRA-08**: On restart, bot loads open positions from Binance API and syncs with DB

### Market Scanner

- [x] **SCAN-01**: Scanner retrieves top-N coins by 24h trading volume from Binance USDT-M Perpetual Futures
- [x] **SCAN-02**: Scanner runs on configurable schedule (default: hourly)
- [x] **SCAN-03**: Scanner filters out coins that don't meet minimum volume threshold
- [x] **SCAN-04**: Number of coins (top-N) configurable via Telegram `/settings` command

### Strategy Generation

- [x] **STRAT-01**: Claude API generates trading strategy via `code_execution` tool — writes Python backtesting code, executes it, returns structured JSON
- [x] **STRAT-02**: Strategy JSON contains: indicator parameters (MACD, RSI), SMC parameters (OB lookback, FVG size, BOS/CHOCH), entry conditions (long/short), exit rules (SL/TP method, R/R), and backtest results
- [x] **STRAT-03**: Claude backtesting uses OHLCV data for configurable period (default: 6 months) on specified timeframes (1h, 15m)
- [x] **STRAT-04**: Strategy generation includes walk-forward validation (train/validation split) to prevent overfitting
- [x] **STRAT-05**: Strategy Manager checks if active strategy exists and is not expired before requesting new generation

### Strategy Filter

- [x] **FILT-01**: Filter validates strategy against configurable criteria: min total return %, max drawdown %, min win rate %, min profit factor, min trades, min avg R/R
- [x] **FILT-02**: Default criteria: return ≥200%, drawdown ≤-12%, winrate ≥55%, PF ≥1.8, trades ≥30, avg R/R ≥2.0
- [x] **FILT-03**: Strict mode (all criteria must pass) and relaxed mode (only return + drawdown required) configurable
- [x] **FILT-04**: Failed strategies logged with which criteria were not met
- [x] **FILT-05**: All filter criteria adjustable via Telegram `/criteria` command

### Strategy Lifecycle

- [x] **LIFE-01**: Strategies stored in PostgreSQL with full metadata (symbol, timeframe, strategy_data JSON, backtest_score, is_active, timestamps)
- [x] **LIFE-02**: Strategy expires after configurable interval (default: 30 days) — triggers re-generation
- [x] **LIFE-03**: Old strategy versions preserved (is_active=false), never hard-deleted
- [x] **LIFE-04**: Review interval configurable via Telegram `/settings review_interval N`
- [x] **LIFE-05**: Criteria snapshot saved with each strategy for audit trail

### Signal Generation

- [x] **SIG-01**: Signal Generator applies active strategy to current OHLCV data and detects entry conditions
- [x] **SIG-02**: SMC analysis: identifies Order Blocks, Fair Value Gaps, Break of Structure, Change of Character
- [x] **SIG-03**: Indicator analysis: MACD crossovers, RSI oversold/overbought exits
- [x] **SIG-04**: Higher timeframe confirmation (e.g., 4h BOS/CHOCH) required before signal emission
- [x] **SIG-05**: Volume confirmation: volume must exceed average by configurable multiplier
- [x] **SIG-06**: Signal includes: direction (long/short), entry price, stop loss, take profit, R/R ratio, signal strength, reasoning text

### Risk Management

- [x] **RISK-01**: Position size calculated as percentage of current balance, divided by SL distance, multiplied by leverage
- [x] **RISK-02**: Progressive stakes: configurable tiers (default 3→5→8%) based on consecutive win count
- [x] **RISK-03**: Win streak resets to base stake on any loss
- [x] **RISK-04**: Maximum open positions limit (default: 5) enforced before new order
- [x] **RISK-05**: Daily loss limit (default: 5%) — trading paused when reached, notification sent
- [x] **RISK-06**: Minimum R/R ratio filter — signals below threshold ignored
- [x] **RISK-07**: Isolated margin enforced on every position
- [x] **RISK-08**: MIN_NOTIONAL check before order submission — reject if position too small
- [x] **RISK-09**: Liquidation price calculated and validated before every order
- [x] **RISK-10**: All risk parameters adjustable via Telegram `/risk` command

### Chart Generation

- [x] **CHART-01**: PNG chart with candlestick data (last 100-150 bars) generated per signal
- [x] **CHART-02**: Chart shows Order Block zones (green=demand, red=supply rectangles)
- [x] **CHART-03**: Chart shows Fair Value Gap zones (transparent rectangles with dashed borders)
- [x] **CHART-04**: Chart shows BOS/CHOCH levels (horizontal lines with labels)
- [x] **CHART-05**: Chart shows entry (blue dashed), stop loss (red solid), take profit (green solid) lines
- [x] **CHART-06**: Chart includes MACD panel (histogram + lines, crossover point marked)
- [x] **CHART-07**: Chart includes RSI panel (30/70 levels, signal zone highlighted)
- [x] **CHART-08**: Chart title shows symbol, timeframe, direction, R/R ratio
- [x] **CHART-09**: Chart rendered to BytesIO (no disk I/O) at 150 DPI

### Pine Script

- [x] **PINE-01**: Pine Script v5 generated per signal with entry/SL/TP levels, OB zones, FVG zones, BOS/CHOCH lines
- [x] **PINE-02**: Pine Script sent via Telegram on `/chart SYMBOL` command or inline button
- [x] **PINE-03**: Script is copy-paste ready for TradingView Pine Editor

### Telegram Bot

- [x] **TG-01**: Bot accepts commands only from configured `ALLOWED_CHAT_ID`
- [x] **TG-02**: Signal message includes: direction, symbol, timeframe, entry/SL/TP prices, R/R, stake %, position size, signal strength, reasoning, chart image
- [x] **TG-03**: Signal has inline buttons: Confirm (execute trade), Reject, Pine Script
- [x] **TG-04**: Reject button optionally captures free-text reason
- [x] **TG-05**: `/start` — system status, current stake, deposit balance
- [x] **TG-06**: `/status` — balance, open positions, daily PnL, current streak/stake
- [x] **TG-07**: `/risk` — view and modify all risk parameters
- [x] **TG-08**: `/criteria` — view and modify strategy filter criteria
- [x] **TG-09**: `/signals` — last 10 signals (accepted/rejected with reasons)
- [x] **TG-10**: `/positions` — open positions with current PnL
- [x] **TG-11**: `/history` — last 20 closed trades
- [x] **TG-12**: `/strategies` — active strategies with next review dates
- [x] **TG-13**: `/skipped` — coins skipped due to criteria (with time filters, per-coin history)
- [x] **TG-14**: `/scan` — trigger manual market scan
- [x] **TG-15**: `/chart SYMBOL` — get Pine Script for last signal
- [x] **TG-16**: `/settings` — general settings (top-N, timeframes, review interval)
- [x] **TG-17**: `/pause` and `/resume` — pause/resume signal generation
- [x] **TG-18**: `/help` — full command reference
- [x] **TG-19**: Daily summary at 21:00 — PnL, trades, win rate, current stake
- [x] **TG-20**: Warning at 80% of daily loss limit
- [x] **TG-21**: Error notifications — API errors, order failures, insufficient balance
- [x] **TG-22**: Notification when strategy criteria causes all coins to be skipped repeatedly

### Order Execution

- [x] **ORD-01**: Market order placed on Binance Futures after Telegram confirmation
- [x] **ORD-02**: SL and TP orders placed immediately after entry fill
- [x] **ORD-03**: Order confirmation sent to Telegram with fill price and actual position size
- [x] **ORD-04**: Order errors sent to Telegram immediately with actionable description
- [x] **ORD-05**: Double-tap protection — DB-level unique constraint prevents duplicate orders from concurrent callbacks

### Position Monitoring

- [x] **MON-01**: Open positions tracked with current PnL (via Binance API polling or WebSocket)
- [x] **MON-02**: Notification sent when SL or TP is hit with final PnL
- [x] **MON-03**: Trade record created on position close (entry, exit, PnL, close reason)
- [x] **MON-04**: Win streak counter updated on position close
- [x] **MON-05**: Daily stats aggregated (PnL, trade count, win rate)

### Skipped Coins

- [ ] **SKIP-01**: Coins that fail strategy criteria are logged with: symbol, backtest results, which criteria failed
- [ ] **SKIP-02**: Optional Telegram notification when coin is skipped (configurable)
- [ ] **SKIP-03**: `/skipped` command shows history with time filters (24h, 7d) and per-coin drill-down
- [ ] **SKIP-04**: Alert when no coins pass criteria for multiple consecutive scan cycles

## v2 Requirements

### Notifications Enhancement

- **NOTF-01**: Configurable notification preferences per event type
- **NOTF-02**: Quiet hours setting (no non-critical notifications during sleep)

### Analytics

- **ANAL-01**: Per-strategy performance tracking (win rate, PnL by strategy version)
- **ANAL-02**: Per-coin performance tracking
- **ANAL-03**: Weekly/monthly performance reports
- **ANAL-04**: Leverage recommendation per strategy based on backtest volatility

### Production Hardening

- **PROD-01**: Health check endpoint for monitoring
- **PROD-02**: Structured logging with log levels
- **PROD-03**: Dry-run mode (signals generated but no orders placed)
- **PROD-04**: Database backup automation

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-user support | Single trader only — no auth layer, permissions, or billing needed |
| Web UI / dashboard | Telegram is the only interface — avoids duplicating UI surface |
| Fully automated execution | Manual confirmation required for every trade — safety on small capital |
| Spot trading | Futures only (USDT-M Perpetual) — different asset class and risk profile |
| Mobile app | Telegram serves as mobile interface |
| Martingale position sizing | Catastrophic on $100 leveraged account — use anti-martingale (progressive on wins) |
| Cross-margin | Isolated margin only — limits loss to allocated margin per position |
| Withdrawal API access | Unnecessary, dramatically increases attack surface |
| Social / copy trading | Single user, no external signal distribution |
| Real-time streaming chart | Static PNG per signal sufficient; trader uses TradingView for live charts |
| Tick-level backtesting | 1m/15m/1h OHLCV sufficient for SMC signals |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Complete |
| INFRA-05 | Phase 1 | Complete |
| INFRA-06 | Phase 1 | Complete |
| INFRA-07 | Phase 1 | Complete |
| INFRA-08 | Phase 1 | Complete |
| SCAN-01 | Phase 2 | Complete |
| SCAN-02 | Phase 2 | Complete |
| SCAN-03 | Phase 2 | Complete |
| SCAN-04 | Phase 2 | Complete |
| STRAT-01 | Phase 2 | Complete |
| STRAT-02 | Phase 2 | Complete |
| STRAT-03 | Phase 2 | Complete |
| STRAT-04 | Phase 2 | Complete |
| STRAT-05 | Phase 2 | Complete |
| FILT-01 | Phase 2 | Complete |
| FILT-02 | Phase 2 | Complete |
| FILT-03 | Phase 2 | Complete |
| FILT-04 | Phase 2 | Complete |
| FILT-05 | Phase 2 | Complete |
| LIFE-01 | Phase 2 | Complete |
| LIFE-02 | Phase 2 | Complete |
| LIFE-03 | Phase 2 | Complete |
| LIFE-04 | Phase 2 | Complete |
| LIFE-05 | Phase 2 | Complete |
| SIG-01 | Phase 3 | Complete |
| SIG-02 | Phase 3 | Complete |
| SIG-03 | Phase 3 | Complete |
| SIG-04 | Phase 3 | Complete |
| SIG-05 | Phase 3 | Complete |
| SIG-06 | Phase 3 | Complete |
| RISK-01 | Phase 3 | Complete |
| RISK-02 | Phase 3 | Complete |
| RISK-03 | Phase 3 | Complete |
| RISK-04 | Phase 3 | Complete |
| RISK-05 | Phase 3 | Complete |
| RISK-06 | Phase 3 | Complete |
| RISK-07 | Phase 3 | Complete |
| RISK-08 | Phase 3 | Complete |
| RISK-09 | Phase 3 | Complete |
| RISK-10 | Phase 3 | Complete |
| CHART-01 | Phase 3 | Complete |
| CHART-02 | Phase 3 | Complete |
| CHART-03 | Phase 3 | Complete |
| CHART-04 | Phase 3 | Complete |
| CHART-05 | Phase 3 | Complete |
| CHART-06 | Phase 3 | Complete |
| CHART-07 | Phase 3 | Complete |
| CHART-08 | Phase 3 | Complete |
| CHART-09 | Phase 3 | Complete |
| TG-01 | Phase 4 | Complete |
| TG-02 | Phase 4 | Complete |
| TG-03 | Phase 4 | Complete |
| TG-04 | Phase 4 | Complete |
| TG-05 | Phase 4 | Complete |
| TG-06 | Phase 4 | Complete |
| TG-07 | Phase 4 | Complete |
| TG-08 | Phase 4 | Complete |
| TG-09 | Phase 4 | Complete |
| TG-10 | Phase 4 | Complete |
| TG-11 | Phase 4 | Complete |
| TG-12 | Phase 4 | Complete |
| TG-13 | Phase 4 | Complete |
| TG-14 | Phase 4 | Complete |
| TG-15 | Phase 4 | Complete |
| TG-16 | Phase 4 | Complete |
| TG-17 | Phase 4 | Complete |
| TG-18 | Phase 4 | Complete |
| TG-20 | Phase 4 | Complete |
| TG-21 | Phase 4 | Complete |
| TG-22 | Phase 4 | Complete |
| ORD-01 | Phase 5 | Complete |
| ORD-02 | Phase 5 | Complete |
| ORD-03 | Phase 5 | Complete |
| ORD-04 | Phase 5 | Complete |
| ORD-05 | Phase 5 | Complete |
| MON-01 | Phase 5 | Complete |
| MON-02 | Phase 5 | Complete |
| MON-03 | Phase 5 | Complete |
| MON-04 | Phase 5 | Complete |
| MON-05 | Phase 5 | Complete |
| TG-19 | Phase 6 | Complete |
| PINE-01 | Phase 6 | Complete |
| PINE-02 | Phase 6 | Complete |
| PINE-03 | Phase 6 | Complete |
| SKIP-01 | Phase 6 | Pending |
| SKIP-02 | Phase 6 | Pending |
| SKIP-03 | Phase 6 | Pending |
| SKIP-04 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 91 total
- Mapped to phases: 91
- Unmapped: 0

**Note:** Header previously stated 71 requirements; actual count from requirement list is 91.

---
*Requirements defined: 2026-03-19*
*Last updated: 2026-03-19 — traceability completed after roadmap creation*
