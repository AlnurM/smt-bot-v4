# Technology Stack

**Project:** Crypto Futures Trading Bot (CTB)
**Researched:** 2026-03-19
**Domain:** Semi-automated crypto futures trading bot — Python, Binance USDT-M Perpetual, AI strategy generation

---

## Recommended Stack

### Runtime

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Python | 3.11+ | Runtime | Required by spec; 3.11 has significant asyncio performance improvements over 3.10; 3.12 adds further improvements and is the current LTS. Use 3.12 if greenfield. | HIGH |

### Exchange Connectivity

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| python-binance | 1.0.35 | Binance REST + WebSocket | Unofficial but the most actively maintained Binance-specific library. Active as of Feb 16, 2026. Covers Futures Testnet via `testnet=True`. Deep Binance feature coverage that CCXT abstracts away. | HIGH |
| binance-futures-connector | 4.1.0 | Official Binance Futures REST | **The official SDK from Binance.** Use this for any endpoint where python-binance lags. Particularly useful as a reference for USDT-M and Testnet endpoints. | MEDIUM |

**Note on CCXT vs python-binance:** CCXT (4.5.44, updated March 17, 2026) is the right choice when multi-exchange portability is needed. For this project — Binance Futures only, single exchange, Testnet-first — python-binance provides deeper Binance-specific support (isolated margin, Testnet flag, futures algo orders). Use CCXT as a fallback reference or if python-binance lags an endpoint. Do NOT use both in the main trade loop — pick one.

### Telegram Bot

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| aiogram | 3.26.0 | Telegram bot interface | Required by spec. Fully async (asyncio-native). 3.x is the current stable branch. Latest: 3.26.0 (current as of 2026-03-19). Active release cadence (monthly releases). Supports FSM, inline keyboards, middleware — all needed for confirm/reject trade flow. | HIGH |

### AI / LLM

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| anthropic | 0.84.0 | Claude API client | Required by spec. Official Python SDK, last updated March 7, 2026. Use `code_execution` tool (version `codeExecution_20260120` — current recommended, no beta header needed) for Claude to write and execute Python backtesting code in a sandboxed environment. | HIGH |

**code_execution tool notes:**
- Version `codeExecution_20260120` is the current recommended version. Supports Claude Sonnet 4.5/4.6 and Opus 4.5/4.6.
- 50 free hours/day included, then $0.05/hour/container.
- Claude writes backtesting Python → executes it in sandbox → returns strategy as structured JSON. No separate backtest service needed.

### Database

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| PostgreSQL | 16+ (Docker) | Persistent storage | Required by spec. Correct decision: avoids SQLite→Postgres migration later. Handles concurrent writes (aiogram handlers + scheduler). Well-supported in async Python. | HIGH |
| SQLAlchemy | 2.0.48 | ORM / query builder | Industry standard for Python ORMs. Version 2.x has full async support via `create_async_engine`. Released March 2, 2026. Use declarative models with 2.x syntax, not legacy 1.x style. | HIGH |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async PostgreSQL driver for Python (5x faster than psycopg3 in benchmarks). Used as the SQLAlchemy async dialect: `postgresql+asyncpg://`. Released November 24, 2025. | HIGH |
| Alembic | 1.18.4 | Database migrations | The de facto standard for SQLAlchemy schema migrations. Use the async template (`alembic init -t async`). Released February 10, 2026. | HIGH |

### Scheduling

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| APScheduler | 3.11.2 | Cron-style job scheduling | Required by spec. Use `3.x` stable, NOT the 4.x alpha. APScheduler 4.0 is still in alpha (4.0.0a6, April 2025) and explicitly marked "do NOT use in production." APScheduler 3.11.2 (released December 22, 2025) is the current stable version and supports `AsyncIOScheduler` for asyncio integration. | HIGH |

**APScheduler 4.x warning:** The 4.0 alpha series is a ground-up redesign with breaking API changes. Even if it reaches stable before this project ships, wait one full minor version cycle before migrating. Use 3.x.

### Technical Analysis

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pandas-ta-classic | latest | MACD, RSI, EMA computation | The original `pandas-ta` (0.4.71b0) has sustainability problems — the author has stated it may be archived by July 2026 if funding doesn't improve. Use `pandas-ta-classic` (the community-maintained fork with 150+ indicators). Alternatively, consider `ta-lib` (C bindings, faster) but requires system dependencies. For this project's indicator set (MACD, RSI), either works — `pandas-ta-classic` is pure Python, easier to Docker. | MEDIUM |
| pandas | 2.x | DataFrame manipulation | Core dependency for OHLCV data processing. Required by all TA libraries. | HIGH |
| numpy | 1.x or 2.x | Numeric operations | Required by pandas and TA libraries. If using pandas-ta-openbb, it requires numpy 2. Otherwise stay on 1.x for compatibility. | HIGH |

**pandas-ta original warning:** `pypi.org/project/pandas-ta/` now shows the project requires Python 3.12+, is in beta (0.4.71b0), and may be archived. Do not use the original `pandas-ta` package for greenfield projects. Use `pandas-ta-classic` from the outset.

### Chart Generation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| mplfinance | 0.12.10b0 | OHLCV candlestick charts + PNG export | Required by spec. The current version (0.12.10b0) is the only available release — no updates since August 2023. Despite the "beta" label, it is the most widely used and battle-tested library for financial candlestick charts in Python. Supports `savefig` for PNG export (required to send via Telegram). Part of the official `matplotlib` org. Use with caution — it is functionally stable but not receiving new features. | MEDIUM |

**mplfinance alternatives:** For custom OB/FVG overlays and multi-panel charts (MACD, RSI sub-panels), `mplfinance`'s `addplot` API is adequate. If complex overlays become painful, `matplotlib` directly (which mplfinance wraps) is the escape hatch — no new dependency needed.

### Configuration and Environment

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| pydantic-settings | 2.13.1 | Config + env management | Validates all config at startup (API keys, thresholds, credentials). Reads from `.env` files via `python-dotenv` integration. Provides type-safe access to environment variables. Released February 19, 2026. Preferred over raw `python-dotenv` for this project's complexity. | HIGH |
| python-dotenv | latest | `.env` file loading | Required by pydantic-settings to load `.env` files. Minimal dependency. | HIGH |

### Infrastructure

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Docker + Docker Compose | latest stable | Container runtime | Required by spec. Single-service bot + PostgreSQL service. Enables consistent local dev and VPS deployment with a single `docker compose up`. | HIGH |

---

## Supporting Libraries (Dev and Ops)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.x | Unit and integration tests | All test runs |
| pytest-asyncio | 0.24+ | Async test support | Required for testing aiogram handlers and async DB code |
| loguru | 0.7+ | Structured logging | Replace stdlib `logging` — simpler API, colored output, file rotation |
| httpx | 0.28+ | HTTP client | Used internally by `anthropic` SDK; useful for any custom API calls |
| aiofiles | 23.x+ | Async file I/O | If PNG charts need async write before sending to Telegram |
| black | 24.x | Code formatter | Enforce consistent formatting |
| ruff | 0.8+ | Linter | Faster than flake8/pylint, replaces multiple tools |
| mypy | 1.x | Static type checking | Catches type errors in async code, config models |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Exchange library | python-binance 1.0.35 | CCXT 4.5.44 | CCXT abstracts Binance-specific features (isolated margin, testnet flag). Useful for multi-exchange; overkill for Binance-only. |
| Exchange library | python-binance | binance-futures-connector (official) | Official SDK is lower-level / more verbose. python-binance has more ecosystem examples for futures trading patterns. Use official as a reference. |
| Scheduler | APScheduler 3.11.2 | Celery + Redis | Celery requires a separate broker process. APScheduler integrates directly in the asyncio event loop — no extra infrastructure for a single-process bot. |
| Scheduler | APScheduler 3.x | APScheduler 4.x alpha | 4.x is explicitly "do NOT use in production" — API is not stable. |
| TA library | pandas-ta-classic | TA-Lib (C bindings) | TA-Lib requires system-level C library install, complicates Docker builds. pandas-ta-classic is pure Python. Only use TA-Lib if performance profiling reveals a bottleneck. |
| TA library | pandas-ta-classic | original pandas-ta | Original may be archived July 2026. Avoid new dependencies on it. |
| Database | PostgreSQL + SQLAlchemy | SQLite | SQLite→Postgres migration is painful later. Project spec correctly mandates Postgres from day one. |
| Config | pydantic-settings | raw python-dotenv | pydantic-settings validates config types at startup, catching missing keys before runtime failures. |
| Chart | mplfinance | Plotly | Plotly generates interactive HTML, not static PNG. Telegram requires static image files. mplfinance's PNG export is the right tool. |
| Chart | mplfinance | matplotlib directly | mplfinance wraps matplotlib with financial-specific defaults (candlesticks, OHLCV). Less boilerplate for this use case. |
| Telegram framework | aiogram 3.x | python-telegram-bot | python-telegram-bot 20.x is also async, but aiogram 3.x has better FSM (finite state machine) support for multi-step interaction flows (confirm/reject trades, settings updates). |

---

## What NOT to Use

| Technology | Why Avoid |
|------------|-----------|
| APScheduler 4.0.0a6 (alpha) | Explicitly marked by maintainer as "do NOT use in production." Breaking API changes expected. |
| Original `pandas-ta` (pip: pandas-ta) | At risk of archival by July 2026. Use `pandas-ta-classic` fork instead. |
| SQLite | Spec mandates PostgreSQL. SQLite is not suitable for concurrent asyncio writers and would require a painful migration. |
| Plotly / Bokeh for chart export | These produce interactive HTML, not PNG. Telegram bots require static image files. |
| Celery | Introduces a message broker (Redis/RabbitMQ) as additional infrastructure. APScheduler handles the scheduling needs within the same asyncio process. |
| FastAPI / Flask | No web UI is in scope. Adding a web framework is unnecessary complexity. |
| `python-binance` < 1.0.20 | Pre-1.0.20 versions have deprecated endpoints. The maintainers explicitly recommend 1.0.20+ minimum. |

---

## Installation

```bash
# Core runtime dependencies
pip install \
  python-binance==1.0.35 \
  aiogram==3.26.0 \
  anthropic==0.84.0 \
  sqlalchemy==2.0.48 \
  asyncpg==0.31.0 \
  alembic==1.18.4 \
  apscheduler==3.11.2 \
  pandas-ta-classic \
  pandas \
  numpy \
  mplfinance==0.12.10b0 \
  pydantic-settings==2.13.1 \
  python-dotenv \
  loguru

# Dev dependencies
pip install \
  pytest \
  pytest-asyncio \
  black \
  ruff \
  mypy \
  aiofiles
```

```dockerfile
# docker-compose.yml service skeleton
services:
  bot:
    build: .
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: ctb
      POSTGRES_USER: ctb
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ctb"]
      interval: 5s
      timeout: 5s
      retries: 5
```

---

## Version Summary Table

| Package | Verified Version | Released | Source |
|---------|-----------------|----------|--------|
| Python | 3.11+ (3.12 preferred) | — | Spec |
| python-binance | 1.0.35 | 2026-02-16 | PyPI |
| binance-futures-connector | 4.1.0 | — | PyPI |
| ccxt | 4.5.44 | 2026-03-17 | PyPI (reference only) |
| aiogram | 3.26.0 | 2026-03-03 | PyPI / docs.aiogram.dev |
| anthropic | 0.84.0 | 2026-03-07 | PyPI |
| SQLAlchemy | 2.0.48 | 2026-03-02 | PyPI |
| asyncpg | 0.31.0 | 2025-11-24 | PyPI |
| alembic | 1.18.4 | 2026-02-10 | PyPI |
| APScheduler | 3.11.2 (stable) | 2025-12-22 | PyPI |
| pandas-ta-classic | community fork | — | PyPI |
| mplfinance | 0.12.10b0 | 2023-08-02 | PyPI |
| pydantic-settings | 2.13.1 | 2026-02-19 | PyPI |

---

## Sources

- [python-binance PyPI / changelog](https://python-binance.readthedocs.io/en/latest/changelog.html)
- [binance-futures-connector PyPI](https://pypi.org/project/binance-futures-connector/)
- [aiogram 3.26.0 docs](https://docs.aiogram.dev/)
- [aiogram PyPI](https://pypi.org/project/aiogram/)
- [Anthropic code_execution tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)
- [anthropic PyPI](https://pypi.org/project/anthropic/)
- [SQLAlchemy async docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy PyPI](https://pypi.org/project/SQLAlchemy/)
- [asyncpg PyPI](https://pypi.org/project/asyncpg/)
- [Alembic PyPI](https://pypi.org/project/alembic/)
- [APScheduler PyPI](https://pypi.org/project/APScheduler/)
- [APScheduler 3.x asyncio scheduler](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html)
- [APScheduler 4.0 progress tracking issue](https://github.com/agronholm/apscheduler/issues/465)
- [pandas-ta PyPI](https://pypi.org/project/pandas-ta/)
- [pandas-ta-classic PyPI](https://pypi.org/project/pandas-ta-classic/)
- [mplfinance PyPI](https://pypi.org/project/mplfinance/)
- [pydantic-settings](https://pypi.org/project/pydantic-settings/)
- [ccxt PyPI](https://pypi.org/project/ccxt/)
