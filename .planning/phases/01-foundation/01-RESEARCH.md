# Phase 1: Foundation - Research

**Researched:** 2026-03-19
**Domain:** Python async application scaffold — Docker Compose, PostgreSQL + SQLAlchemy async, Alembic migrations, pydantic-settings config, python-binance testnet client, APScheduler 3.x, graceful startup/shutdown
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Runtime settings (risk params, criteria, top-N, etc.) stored in DB with .env providing initial defaults
- .env contains both secrets (API keys, tokens, DB URL) AND initial default values for risk/criteria/settings
- On first boot, Alembic migration seeds default rows in risk_settings and strategy_criteria tables from the spec defaults
- DB values override .env defaults — once a setting is changed via Telegram, the DB value wins
- .env.example included in repo with all variables documented, comments explaining each, placeholder values
- Pydantic validates all env vars on boot — missing required var = immediate exit with clear error message naming the var
- API keys, tokens never appear in any log output — strict masking, no partial reveals even in debug mode
- ALL 10 tables created in the first Alembic migration — schema is stable from spec, no per-phase migrations
- UUID primary keys on all tables (as specified in the TZ)
- created_at/updated_at use PostgreSQL server_default=now() — always UTC, DB handles timestamps
- JSONB for strategy_data and criteria_snapshot columns
- Boot sequence verifies ALL three dependencies before accepting work: DB connection + migrations current, Binance API ping (confirm keys work + log active environment), Telegram bot token valid
- If any check fails → log error, exit immediately (fail fast)
- On successful boot → send Telegram message: "Bot started — env: testnet/production, balance: $X, open positions: N"
- On restart → fetch open positions from Binance API, compare with DB, reconcile mismatches, log any differences
- On shutdown (SIGTERM/SIGINT) → leave positions open on Binance (SL/TP are already placed), stop scheduler cleanly, log "shutdown complete", exit with no exceptions
- Positions are safe without the bot running because SL/TP bracket orders live on Binance

### Claude's Discretion

- Python project directory structure and module layout
- Exact Docker Compose configuration (volumes, networks, health checks)
- Logging library choice and format (loguru vs stdlib)
- SQLAlchemy model base class design
- APScheduler job store choice (PostgreSQL vs in-memory)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | System connects to Binance Futures Testnet or Production based on single env variable (`BINANCE_ENV`) | python-binance `AsyncClient.create(testnet=True/False)` driven by `BINANCE_ENV` env var; pydantic-settings validates the enum value |
| INFRA-02 | All API keys stored in `.env` file, never in code or version control | pydantic-settings `SecretStr` fields + `.gitignore` for `.env`; loguru `bind()` filter ensures secrets never reach log output |
| INFRA-03 | PostgreSQL database with all required tables created via Alembic migrations | Alembic `init -t async` with asyncpg; single `initial_migration` creates all 10 tables; seed rows added in `op.bulk_insert()` within same migration |
| INFRA-04 | APScheduler runs hourly market scan and scheduled jobs without drift or missed triggers | APScheduler 3.x `AsyncIOScheduler` + `CronTrigger` (not IntervalTrigger) for exact HH:00 scheduling; `misfire_grace_time=60` |
| INFRA-05 | Application runs as single async process (asyncio event loop with aiogram + APScheduler + asyncpg) | `asyncio.run(main())` entry point; APScheduler `AsyncIOScheduler` shares event loop; aiogram polling inside same loop |
| INFRA-06 | Docker Compose configuration for local development (app + PostgreSQL) | `docker-compose.yml` with `bot` + `db` services; healthcheck on `pg_isready`; `depends_on: db: condition: service_healthy` |
| INFRA-07 | Graceful shutdown — open positions synced, scheduler stopped cleanly | SIGTERM/SIGINT caught via `asyncio` signal handlers; `scheduler.shutdown(wait=False)`; aiogram `dp.stop_polling()`; log "shutdown complete" |
| INFRA-08 | On restart, bot loads open positions from Binance API and syncs with DB | `startup_sync()` coroutine fetches `/fapi/v2/positionRisk`, compares with DB `positions` table, reconciles mismatches |
</phase_requirements>

---

## Summary

Phase 1 establishes the complete application skeleton: project scaffold, Docker environment, database layer with all 10 tables, and the three wired-together runtime components (Binance client, PostgreSQL, APScheduler). No trading logic is written — only the verifiable plumbing that every later phase imports.

The stack is fully determined by prior project-level research (STACK.md). This phase-level research focuses on the specific wiring patterns: how `AsyncIOScheduler` integrates with aiogram's event loop, the correct Alembic async template setup, the python-binance testnet toggle via a single env var, and the fail-fast boot sequence with all three dependency checks.

The most consequential decision for Claude's Discretion is APScheduler job store: use **in-memory** for Phase 1 (simpler, no extra psycopg2 sync dependency) since no jobs are scheduled yet. The PostgreSQL job store can be added in Phase 2 when actual jobs are registered.

**Primary recommendation:** Build the three plans in strict order — scaffold+config first, then DB+migrations, then client wiring+scheduler — because each plan's output (config module, session factory, Binance client) is imported by the next.

---

## Standard Stack

### Core (Phase 1 only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12 | Runtime | Greenfield; 3.12 LTS with best asyncio perf |
| pydantic-settings | 2.13.1 | Config + env validation | Validates all vars at boot; `SecretStr` masks keys in logs |
| loguru | 0.7+ | Logging | Simpler API than stdlib; colored output; file rotation |
| SQLAlchemy | 2.0.48 | ORM / async session | `create_async_engine` + `async_sessionmaker`; 2.x syntax |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async driver; dialect `postgresql+asyncpg://` |
| Alembic | 1.18.4 | DB migrations | `alembic init -t async`; autogenerate from models |
| python-binance | 1.0.35 | Binance REST client | `AsyncClient.create(testnet=True/False)` controlled by env var |
| APScheduler | 3.11.2 | Scheduler | `AsyncIOScheduler`; shares asyncio event loop with aiogram |
| aiogram | 3.26.0 | Telegram bot | Needed for boot notification + startup Telegram message |
| Docker + Compose | latest | Container runtime | App + PostgreSQL service; healthcheck-gated startup |

### Supporting (Dev)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 8.x | Test framework | All test runs |
| pytest-asyncio | 0.24+ | Async test support | Testing async session, startup coroutines |
| python-dotenv | latest | `.env` loading | Required by pydantic-settings to load `.env` files |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| loguru | stdlib logging | loguru is simpler; no custom formatter needed for `SecretStr` masking |
| APScheduler in-memory store | APScheduler PostgreSQL store | PostgreSQL store requires psycopg2 (sync); adds complexity; no jobs run in Phase 1 anyway |
| `asyncio.run(main())` | uvloop | uvloop is ~2x faster but a C extension; asyncio is sufficient for this bot's throughput |

**Installation (Phase 1 subset):**
```bash
pip install \
  pydantic-settings==2.13.1 \
  python-dotenv \
  loguru \
  sqlalchemy==2.0.48 \
  asyncpg==0.31.0 \
  alembic==1.18.4 \
  python-binance==1.0.35 \
  apscheduler==3.11.2 \
  aiogram==3.26.0

# Dev
pip install pytest pytest-asyncio
```

---

## Architecture Patterns

### Recommended Project Structure

```
smt-bot-v4/
├── bot/
│   ├── __init__.py
│   ├── main.py              # asyncio.run(main()); startup + shutdown orchestration
│   ├── config.py            # pydantic-settings Settings class
│   ├── exchange/
│   │   ├── __init__.py
│   │   └── client.py        # BinanceClient wrapper (testnet toggle, ping check)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py       # create_async_engine + async_sessionmaker
│   │   ├── models.py        # ALL 10 SQLAlchemy ORM models
│   │   └── repositories/    # (stub files only in Phase 1)
│   │       └── __init__.py
│   └── scheduler/
│       ├── __init__.py
│       └── setup.py         # AsyncIOScheduler factory + job stubs
├── alembic/
│   ├── env.py               # async migration runner
│   ├── versions/
│   │   └── 0001_initial.py  # all 10 tables + seed rows
│   └── alembic.ini
├── tests/
│   ├── conftest.py          # async engine/session fixtures
│   └── test_startup.py      # boot check + startup message tests
├── .env                     # gitignored
├── .env.example             # committed, all vars documented
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── requirements-dev.txt
```

### Pattern 1: Pydantic-Settings Config with SecretStr Masking

**What:** Single `Settings` class inheriting `BaseSettings` with field-level `SecretStr` for all API keys and tokens. Reads `.env` via `model_config = SettingsConfigDict(env_file=".env")`.

**When to use:** Boot — instantiate once, pass as dependency.

**Example:**
```python
# Source: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Secrets — masked in all repr/log output
    binance_api_key: SecretStr
    binance_api_secret: SecretStr
    telegram_bot_token: SecretStr
    database_url: SecretStr  # contains password

    # Non-secret config
    binance_env: Literal["testnet", "production"] = "testnet"
    allowed_chat_id: int
    log_level: str = "INFO"

    # Initial defaults for seeded DB tables (section 7.1 spec)
    base_stake_pct: float = 3.0
    max_stake_pct: float = 8.0
    max_open_positions: int = 5
    daily_loss_limit_pct: float = 5.0
    leverage: int = 5
    min_rr_ratio: float = 3.0

    # Strategy criteria defaults (section 5.2 spec)
    backtest_period_months: int = 6
    min_total_return_pct: float = 200.0
    max_drawdown_pct: float = -12.0
    min_win_rate_pct: float = 55.0
    min_profit_factor: float = 1.8
    min_trades: int = 30
    min_avg_rr: float = 2.0

settings = Settings()
# settings.binance_api_key → SecretStr('**********')
# settings.binance_api_key.get_secret_value() → actual key (only where needed)
```

**Critical:** Never call `.get_secret_value()` inside a logger call. Pass the `SecretStr` object to loguru — it renders as `'**********'` automatically.

---

### Pattern 2: SQLAlchemy Async Engine + Session Factory

**What:** `create_async_engine` with asyncpg dialect; `async_sessionmaker` with `expire_on_commit=False`; context-manager sessions in all consumers.

**When to use:** Every DB operation uses `async with get_session() as session:`.

**Example:**
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    settings.database_url.get_secret_value(),  # only safe call location
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,   # validates connections before use
    echo=False,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # prevent DetachedInstanceError after commit
)

async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

**Critical:** `expire_on_commit=False` is required — without it, accessing model attributes after `session.commit()` triggers a lazy load that fails in async context.

---

### Pattern 3: SQLAlchemy Declarative Base with UUID PKs and UTC Timestamps

**What:** All 10 models inherit from a shared `Base` with naming conventions. UUID PKs use `server_default=text("gen_random_uuid()")`. Timestamps use `server_default=text("now()")`.

**When to use:** All ORM models in `bot/db/models.py`.

**Example:**
```python
import uuid
from sqlalchemy import MetaData, text
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, TIMESTAMP

NAMING_CONVENTIONS = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTIONS)

class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        onupdate=text("now()"),
        nullable=False,
    )
```

**Critical:** `gen_random_uuid()` requires PostgreSQL 13+ (pgcrypto or built-in). PostgreSQL 16 (used in Docker) has it built-in.

---

### Pattern 4: Alembic Async Template + Seed Data

**What:** Initialize with `alembic init -t async`; env.py configured for asyncpg; seed rows inserted in the same `0001_initial.py` migration using `op.bulk_insert()`.

**When to use:** One-time setup in Plan 01-02.

**Example seed in migration:**
```python
# alembic/versions/0001_initial.py
from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # ... table CREATE statements ...

    # Seed risk_settings (single row)
    risk_settings_table = sa.table(
        "risk_settings",
        sa.column("id"),
        sa.column("base_stake_pct"),
        sa.column("current_stake_pct"),
        sa.column("max_stake_pct"),
        # ... all columns from spec section 7.1 ...
    )
    op.bulk_insert(risk_settings_table, [{
        "id": "00000000-0000-0000-0000-000000000001",
        "base_stake_pct": 3.0,
        "current_stake_pct": 3.0,
        "max_stake_pct": 8.0,
        # ... spec defaults ...
    }])

    # Seed strategy_criteria (single row, spec section 5.2)
    # ...
```

---

### Pattern 5: python-binance AsyncClient Testnet Toggle

**What:** `BINANCE_ENV=testnet` or `production` drives `testnet=True/False` in `AsyncClient.create()`. Futures testnet URL is `testnet.binancefuture.com`.

**When to use:** `BinanceClient` factory in `bot/exchange/client.py`.

**Example:**
```python
# Source: python-binance docs / GitHub README
from binance import AsyncClient

async def create_binance_client(settings: Settings) -> AsyncClient:
    is_testnet = settings.binance_env == "testnet"
    client = await AsyncClient.create(
        api_key=settings.binance_api_key.get_secret_value(),
        api_secret=settings.binance_api_secret.get_secret_value(),
        testnet=is_testnet,
    )
    return client
```

**Critical:** `testnet=True` only routes Futures correctly when using the `AsyncClient`. Verify by calling `client.futures_ping()` and checking the response — a 200 confirms keys and environment. Log `env=testnet|production` but never the key values.

---

### Pattern 6: APScheduler AsyncIOScheduler Integration

**What:** `AsyncIOScheduler` initialized inside the async startup, sharing the asyncio event loop. `CronTrigger` for time-sensitive jobs (not IntervalTrigger). `misfire_grace_time` set to prevent silent skips.

**When to use:** Phase 1 creates the scheduler instance with no jobs; jobs added in Phase 2.

**Example:**
```python
# Source: https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore

def create_scheduler() -> AsyncIOScheduler:
    jobstores = {"default": MemoryJobStore()}
    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        job_defaults={
            "coalesce": True,      # merge missed runs into one
            "max_instances": 1,    # no concurrent execution of same job
            "misfire_grace_time": 60,
        },
        timezone="UTC",
    )
    return scheduler
```

**Critical:** Call `scheduler.start()` inside the async startup coroutine (after the event loop is running), NOT at module import time. Calling it at import level raises `RuntimeError: no current event loop` in Python 3.10+.

---

### Pattern 7: Startup Sequence with Fail-Fast Checks

**What:** `main()` entry point runs all three dependency checks before starting the scheduler and bot polling. Any failure triggers immediate logged exit.

**When to use:** `bot/main.py`.

**Example:**
```python
import asyncio
import signal
import sys
from loguru import logger

async def main():
    settings = Settings()
    configure_logging(settings)

    # 1. DB check — connect + verify migrations current
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    await verify_migrations_current()  # compare alembic_version vs head

    # 2. Binance check — ping + log environment
    binance_client = await create_binance_client(settings)
    await binance_client.futures_ping()
    account = await binance_client.futures_account()
    balance = float(account["totalWalletBalance"])
    logger.info(f"Binance connected | env={settings.binance_env} | balance=${balance:.2f}")

    # 3. Telegram check — validate bot token
    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    bot_info = await bot.get_me()
    logger.info(f"Telegram bot connected: @{bot_info.username}")

    # 4. Restart sync — reconcile open positions
    await startup_position_sync(binance_client, session_factory)

    # 5. Start scheduler
    scheduler = create_scheduler()
    scheduler.start()

    # 6. Send startup notification
    open_positions = await count_open_positions(session_factory)
    await bot.send_message(
        settings.allowed_chat_id,
        f"Bot started — env: {settings.binance_env}, balance: ${balance:.2f}, open positions: {open_positions}"
    )

    # 7. Start polling (blocks until shutdown signal)
    dp = create_dispatcher()
    await dp.start_polling(bot)

async def shutdown(scheduler, bot, binance_client):
    logger.info("Shutdown initiated")
    scheduler.shutdown(wait=False)
    await bot.session.close()
    await binance_client.close_connection()
    logger.info("Shutdown complete")

asyncio.run(main())
```

---

### Pattern 8: Fail-Fast on Missing Env Vars

**What:** pydantic-settings raises `ValidationError` with field names on missing required vars. Catch at entry point and exit with a clear message.

**Example:**
```python
import sys
from pydantic import ValidationError

try:
    settings = Settings()
except ValidationError as e:
    for err in e.errors():
        field = err["loc"][0]
        print(f"ERROR: Missing required environment variable: {field.upper()}", file=sys.stderr)
    sys.exit(1)
```

---

### Anti-Patterns to Avoid

- **`BackgroundScheduler` in async app:** Causes `no current event loop` errors. Use `AsyncIOScheduler` only.
- **`IntervalTrigger` for hourly scans:** Drifts when job exceeds interval. Use `CronTrigger(hour='*', minute=0)`.
- **Sharing `AsyncSession` across coroutines:** Each task needs its own session. Pass the factory, not the session instance.
- **Module-level `AsyncClient.create()`:** Async client creation must be inside a running event loop (inside `async def main()`).
- **`engine.dispose()` at shutdown before all sessions close:** Closes connections under active sessions. Shutdown in order: stop scheduler → close Telegram polling → close sessions → dispose engine.
- **Logging `settings.binance_api_key` directly:** Even f-strings will call `__repr__` which returns `SecretStr('**********')` — safe. But `.get_secret_value()` inside any log call leaks the key.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Env var validation at boot | Custom `.env` parser with manual type checks | `pydantic-settings` `BaseSettings` | Handles required/optional, types, nesting, `.env` files, SecretStr masking |
| UUID generation | `str(uuid.uuid4())` in Python before insert | `server_default=text("gen_random_uuid()")` on column | Server-side generation; consistent with DB-as-source-of-truth; no Python UUID needed |
| UTC timestamps | `datetime.utcnow()` in Python | `server_default=text("now()")` + PostgreSQL UTC config | DB clock is authoritative; Python clock can drift; avoids naive datetime bugs |
| DB schema migrations | `CREATE TABLE` SQL strings in startup | Alembic | Version control for schema; rollback support; autogenerate from models |
| Testnet/production URL routing | Hardcoded URL switch with if/else | `python-binance AsyncClient(testnet=True/False)` | Library handles URL routing correctly; avoids the testnet URL drift issue documented in PITFALLS.md |
| Signal handling for graceful shutdown | Custom SIGTERM listener | `asyncio.loop.add_signal_handler(signal.SIGTERM, ...)` | Platform-portable; integrates with asyncio event loop properly |

**Key insight:** In this phase, the most common hand-roll temptation is timestamp and UUID management in Python. Delegate both entirely to PostgreSQL — it eliminates a class of subtle bugs around timezone handling and UUID collisions.

---

## Common Pitfalls

### Pitfall 1: APScheduler PostgreSQL Job Store Requires psycopg2 (Sync)

**What goes wrong:** The PostgreSQL job store for APScheduler 3.x uses `psycopg2` (synchronous driver), not `asyncpg`. Adding it requires an additional sync dependency and a separate connection string — not the async one used for SQLAlchemy.

**Why it happens:** APScheduler 3.x job stores are sync; the async executor only affects job execution, not the store itself.

**How to avoid:** Use `MemoryJobStore` for Phase 1. There are no scheduled jobs yet. Evaluate adding the PostgreSQL job store in Phase 2 only if job persistence across restarts is needed. Given that restart reconciliation is handled by `startup_position_sync()`, in-memory is sufficient.

**Warning signs:** Adding `apscheduler[postgresql]` to requirements — this pulls in psycopg2 sync.

---

### Pitfall 2: Testnet AsyncClient Routing for Futures

**What goes wrong:** `testnet=True` on `AsyncClient.create()` correctly routes Futures endpoints. However, there are confirmed issues where private API calls can be misrouted to live endpoints on some versions.

**Why it happens:** python-binance testnet routing was patched in later versions. There are also known issues in the CCXT library (documented in PITFALLS.md — Pitfall 3) where testnet private calls hit live endpoints.

**How to avoid:** After creating the testnet client, call `futures_ping()` AND `futures_account()`. If `futures_account()` returns account data with a balance that matches testnet (~15,000 USDT virtual), the routing is correct. Store `environment` tag on every DB record from the first migration.

**Warning signs:** `futures_account()` returns a real USDT balance (not ~15,000 virtual); order placement response includes real exchange timestamps.

---

### Pitfall 3: Alembic autogenerate Misses PostgreSQL-Specific Types

**What goes wrong:** Alembic autogenerate may not detect `JSONB` vs `JSON`, or `UUID` vs `VARCHAR(36)` as changes because it compares via SQLAlchemy type representation, not raw PostgreSQL type names.

**Why it happens:** When models use `from sqlalchemy.dialects.postgresql import JSONB, UUID`, autogenerate works correctly. When models use generic `sa.JSON` or `sa.String`, PostgreSQL stores as `json` / `varchar` — different from the intended types.

**How to avoid:** Use PostgreSQL-specific dialect types explicitly in models: `from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP`. Add `compare_type=True` to Alembic `context.configure()` in `env.py`.

**Warning signs:** Migration script shows `NULL` changes for JSONB columns, or UUID columns generated as VARCHAR in migration output.

---

### Pitfall 4: aiogram Dispatcher Shutdown Not Triggered on SIGTERM

**What goes wrong:** When Docker sends SIGTERM (e.g., `docker stop`), the aiogram polling loop may not cleanly exit, leaving the Telegram session open. Subsequent restarts get "another instance is already running" errors from Telegram API.

**Why it happens:** aiogram 3.x reworked graceful shutdown but it requires signals to be handled by asyncio, not by the default Python signal handler (which raises `KeyboardInterrupt` from a thread, not from the event loop).

**How to avoid:** Register signal handlers via `asyncio.get_event_loop().add_signal_handler()` inside the async main function, calling `dp.stop_polling()` on signal receipt. Alternatively, call `await dp.start_polling(bot, handle_signals=True)` — aiogram 3.x supports this directly.

**Warning signs:** Bot doesn't respond after a `docker stop` + `docker start` cycle; Telegram API returns 409 Conflict.

---

### Pitfall 5: `DetachedInstanceError` from Shared Sessions

**What goes wrong:** Startup coroutine creates a session, returns an ORM object, session closes (context manager exits), later code accesses a lazy-loaded relationship on that object — raises `DetachedInstanceError`.

**Why it happens:** SQLAlchemy async sessions use `expire_on_commit=True` by default, expiring all attributes after commit. Async drivers cannot lazy-load.

**How to avoid:** Set `expire_on_commit=False` on `async_sessionmaker`. Use `selectinload` / `joinedload` for any relationship access. Never pass ORM objects out of a session context; pass data as plain dicts or Pydantic models instead.

**Warning signs:** `MissingGreenlet: greenlet_spawn` or `DetachedInstanceError` in logs after any DB write.

---

### Pitfall 6: `gen_random_uuid()` Availability in PostgreSQL

**What goes wrong:** `server_default=text("gen_random_uuid()")` fails in PostgreSQL < 13 where it requires `CREATE EXTENSION pgcrypto` first.

**Why it happens:** `gen_random_uuid()` became a built-in in PostgreSQL 13. Earlier versions need pgcrypto.

**How to avoid:** Use PostgreSQL 16 in Docker (as specified in STACK.md). Pin `image: postgres:16` in `docker-compose.yml`, never `postgres:latest`.

**Warning signs:** `ERROR: function gen_random_uuid() does not exist` on first migration.

---

## Code Examples

Verified patterns from official sources:

### Async Engine Setup
```python
# Source: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/ctb",
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    echo=False,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

### Alembic async env.py (key section)
```python
# Source: https://dev.to/matib/alembic-with-async-sqlalchemy-1ga
# alembic/env.py
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

def run_migrations_online():
    connectable = create_async_engine(config.get_main_option("sqlalchemy.url"))

    async def run():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    asyncio.run(run())
```

### APScheduler AsyncIOScheduler startup
```python
# Source: https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def main():
    scheduler = AsyncIOScheduler(timezone="UTC")
    # add jobs here in Phase 2
    scheduler.start()
    # ... rest of startup
    # On shutdown:
    scheduler.shutdown(wait=False)
```

### aiogram graceful shutdown with signals
```python
# Source: https://docs.aiogram.dev + aiogram/aiogram GitHub
async def main():
    dp = Dispatcher()
    bot = Bot(token=TOKEN)

    # Register shutdown
    async def on_shutdown():
        await bot.session.close()

    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot, handle_signals=True)
```

### pydantic-settings with SecretStr
```python
# Source: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    binance_api_key: SecretStr  # prints as SecretStr('**********')
    binance_env: str = "testnet"
```

---

## Complete Table Schema Reference

All 10 tables from `idea.md` section 10.1, mapped to SQLAlchemy models for the single Alembic migration:

| Table | Key Fields | Special Types |
|-------|-----------|---------------|
| `strategies` | id (UUID PK), symbol, timeframe, strategy_data, backtest_score, is_active, next_review_at, review_interval_days, source, criteria_snapshot | JSONB: strategy_data, criteria_snapshot |
| `strategy_criteria` | id (UUID PK), backtest_period_months, min_total_return_pct, max_drawdown_pct, min_win_rate_pct, min_profit_factor, min_trades, min_avg_rr, notify_on_skip, strict_mode | Single-row; seeded in migration |
| `risk_settings` | id (UUID PK), base_stake_pct, current_stake_pct, max_stake_pct, progressive_stakes, wins_to_increase, reset_on_loss, min_rr_ratio, max_open_positions, daily_loss_limit_pct, leverage, margin_type, win_streak_current | JSONB: progressive_stakes array; single-row; seeded in migration |
| `signals` | id (UUID PK), strategy_id (FK), symbol, direction, entry_price, stop_loss, take_profit, rr_ratio, signal_strength, reasoning, status, created_at | FK to strategies |
| `skipped_coins` | id (UUID PK), symbol, reason, backtest_results, failed_criteria, created_at | JSONB: backtest_results, failed_criteria |
| `orders` | id (UUID PK), signal_id (FK), binance_order_id, status, side, quantity, executed_price, filled_at, environment | environment: VARCHAR (testnet/production) |
| `positions` | id (UUID PK), order_id (FK), symbol, side, entry_price, current_price, quantity, unrealized_pnl, status, environment | FK to orders |
| `trades` | id (UUID PK), position_id (FK), symbol, side, entry_price, exit_price, realized_pnl, close_reason, opened_at, closed_at | FK to positions |
| `daily_stats` | id (UUID PK), date (UNIQUE), total_pnl, trade_count, win_count, win_rate, starting_balance, ending_balance, current_stake_pct, win_streak | DATE type for date column |
| `logs` | id (UUID PK), level, message, module, created_at | For structured audit log (not all loguru output) |

**Migration order:** Create tables in FK dependency order: strategies → signals → orders → positions → trades; strategy_criteria, risk_settings, skipped_coins, daily_stats, logs are independent.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `sessionmaker(bind=engine)` | `async_sessionmaker(engine, class_=AsyncSession)` | SQLAlchemy 2.0 (2023) | Native async sessionmaker; no `class_=AsyncSession` workaround needed |
| `alembic init alembic` | `alembic init -t async alembic` | Alembic 1.x (2022+) | Generates async-compatible env.py template directly |
| `APScheduler 4.x alpha` | `APScheduler 3.11.2` (stable) | 4.0 still alpha as of 2026 | Avoid 4.x; 3.x is production-stable |
| `python-dotenv` + manual validation | `pydantic-settings BaseSettings` | pydantic v2 era | Type validation + SecretStr masking in one step |
| Stdlib `logging.basicConfig` | `loguru` | Industry shift 2022+ | Simpler API; no custom handlers; built-in structured output |

**Deprecated/outdated:**
- `AsyncClient.create(testnet=True)` with spot testnet URL: Spot testnet URL changed to `demo-api.binance.com` (different from Futures testnet). For this project (Futures only), `testnet=True` is still correct.
- APScheduler 4.0.0a6: Explicitly marked "do NOT use in production" by maintainer.

---

## Open Questions

1. **APScheduler PostgreSQL Job Store in Phase 2**
   - What we know: In-memory store is sufficient for Phase 1 (no jobs). Phase 2 adds the hourly Market Scanner job.
   - What's unclear: Whether APScheduler PostgreSQL job store's psycopg2 sync dependency causes conflicts with asyncpg.
   - Recommendation: Test psycopg2 + asyncpg coexistence in Phase 2; if conflicts arise, use in-memory store permanently (restart reconciliation via `startup_position_sync()` handles lost scheduler state).

2. **DB migrations check at runtime (Alembic `current` vs `head`)**
   - What we know: Startup should verify the DB migration is at head before proceeding.
   - What's unclear: Programmatic `alembic current` / `alembic head` comparison in async context requires running Alembic commands via subprocess or the `MigrationContext` API.
   - Recommendation: Use `alembic.script.ScriptDirectory` + `MigrationContext.configure()` to compare current DB revision to head; fail fast if mismatch.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24+ |
| Config file | `pytest.ini` (Wave 0 gap — does not exist yet) |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | `BINANCE_ENV=testnet` → AsyncClient uses testnet URL; `production` → live URL | unit | `pytest tests/test_exchange_client.py::test_testnet_toggle -x` | ❌ Wave 0 |
| INFRA-02 | SecretStr fields never appear in log output (even debug) | unit | `pytest tests/test_config.py::test_secret_masking -x` | ❌ Wave 0 |
| INFRA-03 | All 10 tables exist after migration runs; seed rows present in risk_settings and strategy_criteria | integration | `pytest tests/test_migrations.py::test_all_tables_exist -x` | ❌ Wave 0 |
| INFRA-04 | AsyncIOScheduler starts without error; CronTrigger registered for hourly job stub | unit | `pytest tests/test_scheduler.py::test_scheduler_starts -x` | ❌ Wave 0 |
| INFRA-05 | Single asyncio event loop; scheduler and bot run in same loop | unit | `pytest tests/test_main.py::test_single_event_loop -x` | ❌ Wave 0 |
| INFRA-06 | Docker Compose `docker compose up --build` reaches healthy state | smoke | manual — `docker compose up --build -d && docker compose ps` | ❌ Wave 0 |
| INFRA-07 | SIGTERM causes scheduler.shutdown() + clean exit with no exceptions | unit | `pytest tests/test_main.py::test_graceful_shutdown -x` | ❌ Wave 0 |
| INFRA-08 | `startup_position_sync()` fetches Binance positions, creates/reconciles DB records | unit (mocked Binance) | `pytest tests/test_startup.py::test_position_sync -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/ -x -q`
- **Per wave merge:** `pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `pytest.ini` — pytest + asyncio-mode = auto configuration
- [ ] `tests/conftest.py` — async engine fixture (in-memory SQLite or test PostgreSQL), settings fixture with test values
- [ ] `tests/test_config.py` — covers INFRA-02 (secret masking)
- [ ] `tests/test_exchange_client.py` — covers INFRA-01 (testnet toggle, mock Binance ping)
- [ ] `tests/test_migrations.py` — covers INFRA-03 (all 10 tables, seed rows)
- [ ] `tests/test_scheduler.py` — covers INFRA-04 (scheduler starts, CronTrigger)
- [ ] `tests/test_main.py` — covers INFRA-05, INFRA-07 (event loop, graceful shutdown)
- [ ] `tests/test_startup.py` — covers INFRA-08 (position sync, reconciliation)
- [ ] Framework install: `pip install pytest pytest-asyncio`

---

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy async docs](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) — async engine, session factory, DetachedInstanceError prevention
- [APScheduler 3.x docs](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html) — AsyncIOScheduler, CronTrigger, job defaults
- [pydantic-settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — BaseSettings, SecretStr, SettingsConfigDict
- [Alembic 1.18.4 docs](https://alembic.sqlalchemy.org/en/latest/tutorial.html) — async template, autogenerate, bulk_insert
- [python-binance GitHub/docs](https://python-binance.readthedocs.io/en/latest/overview.html) — AsyncClient testnet parameter
- [aiogram 3.26.0 docs](https://docs.aiogram.dev/) — startup/shutdown, graceful polling stop
- `.planning/research/STACK.md` — verified library versions (researched 2026-03-19)
- `.planning/research/ARCHITECTURE.md` — component boundaries, project structure
- `.planning/research/PITFALLS.md` — APScheduler PostgreSQL job store caveat, testnet URL drift
- `idea.md` — spec sections 5.2, 6.1, 7.1, 10.1 — authoritative table schemas and default values

### Secondary (MEDIUM confidence)
- [Alembic with Async SQLAlchemy — DEV Community](https://dev.to/matib/alembic-with-async-sqlalchemy-1ga) — async env.py pattern (verified against official Alembic docs)
- [CCXT GitHub issue #26487](https://github.com/ccxt/ccxt/issues/26487) — testnet private API misrouting (confirmed bug; mitigation: verify via account balance check)

### Tertiary (LOW confidence)
- None — all critical claims verified against official sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified against PyPI in STACK.md (2026-03-19)
- Architecture: HIGH — patterns verified against official docs (SQLAlchemy, APScheduler, pydantic-settings, aiogram)
- Pitfalls: HIGH — core pitfalls from official docs and confirmed GitHub issues; MEDIUM for APScheduler job store interaction

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (stable libraries; APScheduler 4.x alpha still not production-safe)
