# CTB — Crypto Futures Trading Bot

Semi-automated trading bot for **Binance USDT-M Perpetual Futures** with AI-powered strategy generation.

Claude AI generates and backtests SMC + MACD/RSI strategies, the bot detects signals with weighted scoring, sends chart-annotated trade signals to Telegram, and executes orders after manual confirmation.

## How It Works

```
Claude AI  ──►  Strategy  ──►  Signal     ──►  Telegram   ──►  Binance
(backtest)      (filter)       (SMC+MACD)      (confirm?)      (order)
                                    │                              │
                                    ▼                              ▼
                               Chart PNG                    Position Monitor
                               Pine Script                  SL/TP ──► Trade Record
```

1. **Market Scanner** scans top-N coins from your whitelist every hour
2. **Claude Strategy Engine** generates optimized strategies via `code_execution` backtesting with walk-forward validation
3. **Signal Generator** detects entry conditions using Smart Money Concepts (Order Blocks, FVG, BOS/CHOCH) + MACD/RSI
4. **Telegram Bot** sends signal with chart image — you tap Confirm or Reject
5. **Order Executor** places isolated-margin market order with SL/TP bracket on Binance
6. **Position Monitor** watches positions, notifies on close, updates win streak and daily stats

## Features

- **AI Strategy Generation** — Claude writes and runs Python backtesting code in sandbox, returns optimized parameters
- **Smart Money Concepts** — Order Blocks, Fair Value Gaps, Break of Structure, Change of Character detection
- **Risk Management** — Progressive stakes (3% → 5% → 8%), daily loss circuit breaker, liquidation safety check
- **Chart Visualization** — PNG with OB/FVG zones, entry/SL/TP levels, MACD/RSI panels
- **Pine Script** — TradingView overlay generated per signal (.txt file)
- **14 Telegram Commands** — Full control: `/risk`, `/criteria`, `/settings`, `/signals`, `/positions`, `/history`, `/strategies`, `/skipped`, `/scan`, `/chart`, `/pause`, `/resume`, `/dryrun`, `/help`
- **Daily Summary** — 21:00 report with PnL, trades, win rate, balance, best/worst trade
- **Dry-Run Mode** — Test signals without placing real orders

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Binance Futures Testnet account ([testnet.binancefuture.com](https://testnet.binancefuture.com))
- Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Anthropic API key with `code_execution` access

### Setup

```bash
# Clone the repo
git clone https://github.com/AlnurM/smt-bot-v4.git
cd smt-bot-v4

# Configure environment
cp .env.example .env
# Edit .env with your API keys:
#   BINANCE_API_KEY, BINANCE_API_SECRET
#   TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_ID
#   ANTHROPIC_API_KEY

# Start
docker compose up --build
```

The bot will:
1. Connect to PostgreSQL and run migrations
2. Verify Binance API keys and Telegram bot token
3. Send a "Bot started" message to your Telegram
4. Start the hourly market scan

### Switching to Production

```env
# In .env — change only these:
BINANCE_ENV=production
BINANCE_API_KEY=<your_real_key>
BINANCE_API_SECRET=<your_real_secret>
```

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BINANCE_ENV` | yes | `testnet` | `testnet` or `production` |
| `BINANCE_API_KEY` | yes | — | Binance Futures API key |
| `BINANCE_API_SECRET` | yes | — | Binance Futures API secret |
| `TELEGRAM_BOT_TOKEN` | yes | — | Telegram bot token |
| `ALLOWED_CHAT_ID` | yes | — | Your Telegram chat ID |
| `ANTHROPIC_API_KEY` | yes | — | Anthropic API key |
| `DATABASE_URL` | yes | (docker-compose) | PostgreSQL connection string |
| `LEVERAGE` | no | `5` | Default leverage |
| `BASE_STAKE_PCT` | no | `3.0` | Starting stake % |
| `MAX_OPEN_POSITIONS` | no | `5` | Max concurrent positions |
| `DAILY_LOSS_LIMIT_PCT` | no | `5.0` | Daily loss halt threshold % |
| `TOP_N_COINS` | no | `10` | Coins to scan per cycle |
| `COIN_WHITELIST` | no | (built-in) | Comma-separated approved coins |

See `.env.example` for the full list with descriptions.

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | System status, balance, current stake |
| `/status` | Balance, open positions, daily PnL |
| `/risk` | View/modify risk parameters (`/risk stake 5`) |
| `/criteria` | View/modify strategy filter criteria (`/criteria return 150`) |
| `/settings` | General settings (top_n, review interval) |
| `/signals` | Last 10 signals (accepted/rejected) |
| `/positions` | Open positions with current PnL |
| `/history` | Last 20 closed trades |
| `/strategies` | Active strategies with next review dates |
| `/skipped` | Coins skipped due to criteria (24h/week/per-coin) |
| `/scan` | Trigger manual market scan |
| `/chart SYMBOL` | Pine Script for last signal |
| `/pause` / `/resume` | Pause/resume signal generation |
| `/dryrun on\|off` | Toggle dry-run mode |
| `/help` | Full command reference |

## Architecture

```
bot/
├── main.py                  # Entry point, startup sequence, APScheduler jobs
├── config.py                # Pydantic settings with SecretStr masking
├── scanner/
│   └── market_scanner.py    # Top-N coins by volume, OHLCV fetch
├── strategy/
│   ├── claude_engine.py     # Claude API + code_execution backtesting
│   ├── filter.py            # Strategy criteria validation
│   └── manager.py           # Lifecycle: generate, save, expire, version
├── signals/
│   ├── smc.py               # Order Blocks, FVG, BOS/CHOCH detection
│   ├── indicators.py        # MACD/RSI via pandas-ta-classic
│   └── generator.py         # Signal orchestration + weighted scoring
├── risk/
│   └── manager.py           # Position sizing, progressive stakes, circuit breakers
├── charts/
│   └── generator.py         # mplfinance PNG with SMC overlay
├── order/
│   └── executor.py          # Binance Futures order placement + SL/TP bracket
├── monitor/
│   └── position.py          # 60s polling, close detection, trade recording
├── reporting/
│   ├── daily_summary.py     # 21:00 daily report
│   └── pine_script.py       # TradingView Pine Script v5 generator
├── telegram/
│   ├── middleware.py         # Single-user security (ALLOWED_CHAT_ID)
│   ├── dispatch.py          # Signal message with chart + inline buttons
│   ├── notifications.py     # Error alerts, 80% loss warning, skip alerts
│   ├── callbacks.py         # CallbackData factories
│   └── handlers/
│       ├── commands.py       # 14 command handlers
│       ├── callbacks.py      # Confirm/Reject/Pine button handlers
│       └── settings.py       # /risk, /criteria, /settings handlers
├── db/
│   ├── models.py            # 10 SQLAlchemy ORM models
│   └── session.py           # Async session factory
├── exchange/
│   └── client.py            # Binance AsyncClient wrapper
└── scheduler/
    └── setup.py             # APScheduler factory
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12 |
| Telegram | aiogram 3.26 |
| Database | PostgreSQL 16 + SQLAlchemy 2.0 + asyncpg |
| Migrations | Alembic (async) |
| Exchange | python-binance 1.0.35 |
| AI | Anthropic Claude API (`code_execution`) |
| Indicators | pandas-ta-classic 0.4.47 |
| Charts | mplfinance 0.12.10b0 + matplotlib |
| Scheduler | APScheduler 3.11.2 |
| Deploy | Docker Compose |

## Security

- API keys stored in `.env` only, masked via `SecretStr` (never logged)
- Telegram restricted to single `ALLOWED_CHAT_ID`
- Binance API: Futures Trading only, **no Withdrawal permission**
- Isolated margin enforced on every position
- Double-tap protection via `SELECT ... FOR UPDATE`

## Development

```bash
# Run tests (inside Docker)
docker compose run --rm --no-deps bot sh -c \
  "pip install pytest pytest-asyncio -q && pytest tests/ -q"

# Run specific test file
docker compose run --rm --no-deps bot sh -c \
  "pip install pytest pytest-asyncio -q && pytest tests/test_risk_manager.py -v"

# View logs
docker compose logs -f bot
```

## License

Private project.
