---
phase: 01-foundation
plan: "02"
subsystem: database
tags: [sqlalchemy, alembic, asyncpg, postgresql, jsonb, uuid, migrations, orm]

requires:
  - phase: 01-01
    provides: "Settings class with database_url SecretStr, module-level settings singleton"

provides:
  - "bot/db/models.py: 10 SQLAlchemy ORM models (Base + Strategy, StrategyCriteria, RiskSettings, Signal, SkippedCoin, Order, Position, Trade, DailyStats, Log)"
  - "bot/db/session.py: async engine factory + get_session() async generator"
  - "alembic/versions/0001_initial.py: single migration creating all 10 tables + seeding risk_settings and strategy_criteria"
  - "alembic/env.py: async migration runner wired to models and settings"
  - "tests/test_migrations.py: 5 integration tests (table existence, seed data, head revision, JSONB types)"

affects:
  - 01-03
  - phase-02-scanner
  - phase-03-signal
  - phase-04-executor
  - phase-05-telegram
  - phase-06-monitor

tech-stack:
  added:
    - "greenlet (required by SQLAlchemy asyncpg dialect for sync-in-async bridge)"
  patterns:
    - "Async engine: create_async_engine with pool_size=5, max_overflow=10, pool_pre_ping=True"
    - "Session: async_sessionmaker with expire_on_commit=False to prevent DetachedInstanceError"
    - "Models: DeclarativeBase with MetaData naming conventions; UUID PKs with gen_random_uuid(); TIMESTAMP(timezone=True) with now()"
    - "JSONB: use sqlalchemy.dialects.postgresql.JSONB, not generic JSON"
    - "Migration seed: json.dumps() required for list values passed to op.bulk_insert via asyncpg"

key-files:
  created:
    - bot/db/models.py
    - bot/db/session.py
    - alembic.ini
    - alembic/env.py
    - alembic/versions/0001_initial.py
    - tests/test_migrations.py
  modified:
    - requirements.txt

key-decisions:
  - "json.dumps() required for JSONB list seed values in op.bulk_insert — asyncpg cannot encode raw Python list as JSONB bind parameter"
  - "Migration test fixture scope set to function (not module) to avoid pytest-asyncio event_loop scope mismatch"
  - "greenlet added to requirements.txt — SQLAlchemy 2.0 asyncpg dialect requires it for sync-in-async bridging"
  - "0001_initial.py uses as_uuid=False for UUID columns in migration (avoids Alembic UUID comparison issues) while ORM models use as_uuid=True"

patterns-established:
  - "All DB consumers import from bot.db.session (engine, SessionLocal, get_session) and bot.db.models"
  - "get_session() used as async context manager: async with get_session() as session:"
  - "Integration tests marked with @pytest.mark.integration; skip with pytest -m 'not integration'"

requirements-completed: [INFRA-03]

duration: 7min
completed: 2026-03-19
---

# Phase 1 Plan 02: Database Layer Summary

**10-table PostgreSQL schema via single Alembic async migration with seeded risk_settings (3%/5x) and strategy_criteria (200% return threshold), async SQLAlchemy session factory, and 26 tests passing**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-19T11:05:16Z
- **Completed:** 2026-03-19T11:12:44Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- All 10 SQLAlchemy ORM models created with UUID PKs, UTC timestamps, and JSONB columns where specified
- Single Alembic async migration creates all 10 tables in correct FK dependency order and seeds both configuration tables
- Async session factory with expire_on_commit=False (prevents DetachedInstanceError in async context)
- 5 integration tests verify table existence, seed data values, head revision, and JSONB column types

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for models and session** - `b704f08` (test)
2. **Task 1 GREEN: SQLAlchemy ORM models + async session** - `b990e66` (feat)
3. **Task 2: Alembic setup + migration + migration tests** - `7b531c0` (feat)

## Files Created/Modified

- `bot/db/models.py` - Base + 10 ORM models: Strategy, StrategyCriteria, RiskSettings, Signal, SkippedCoin, Order, Position, Trade, DailyStats, Log
- `bot/db/session.py` - create_async_engine + async_sessionmaker(expire_on_commit=False) + get_session() async generator
- `alembic.ini` - Alembic config with placeholder URL (real URL injected by env.py)
- `alembic/env.py` - Async migration runner, wired to Base.metadata and settings.database_url
- `alembic/versions/0001_initial.py` - Creates all 10 tables + seeds risk_settings and strategy_criteria
- `tests/test_migrations.py` - 5 integration tests (table existence, seed data, head check, JSONB types)
- `requirements.txt` - Added greenlet dependency
- `tests/test_models.py` - 21 unit tests for model imports, table names, UUID PKs, JSONB types, metadata

## Decisions Made

- **json.dumps() for JSONB seed values:** asyncpg requires JSON-encoded strings for JSONB bind parameters in op.bulk_insert, not raw Python lists. Applied to progressive_stakes column in risk_settings seed row.
- **greenlet dependency:** SQLAlchemy 2.0's asyncpg dialect requires greenlet for the sync-in-async bridge used during migration execution. Added to requirements.txt.
- **as_uuid=False in migration vs as_uuid=True in ORM:** Migration uses as_uuid=False (stores UUID as string) to avoid Alembic UUID comparison issues; ORM models use as_uuid=True for Python-level UUID objects.
- **Function-scoped test fixtures:** pytest-asyncio 0.24 disallows module-scoped async fixtures with function-scoped event_loop; downgraded to function scope with idempotent `alembic upgrade head` in autouse fixture.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] json.dumps() for JSONB list in op.bulk_insert**
- **Found during:** Task 2 (Alembic migration execution)
- **Issue:** asyncpg raised `'list' object has no attribute 'encode'` when op.bulk_insert passed `[3.0, 5.0, 8.0]` as a Python list for the JSONB progressive_stakes column
- **Fix:** Wrapped list with `json.dumps([3.0, 5.0, 8.0])` so asyncpg receives a JSON string it can encode
- **Files modified:** alembic/versions/0001_initial.py
- **Verification:** `alembic upgrade head` ran to completion; migration tests pass
- **Committed in:** 7b531c0 (Task 2 commit)

**2. [Rule 1 - Bug] pytest-asyncio scope mismatch in test fixture**
- **Found during:** Task 2 (running migration tests)
- **Issue:** Module-scoped async fixture `migrated_engine` triggered `ScopeMismatch` because pytest-asyncio 0.24 cannot share a function-scoped event_loop with a module-scoped fixture
- **Fix:** Redesigned tests to use function-scoped fixtures; each test creates its own engine instance; `autouse` fixture calls `alembic upgrade head` before each test (idempotent)
- **Files modified:** tests/test_migrations.py
- **Verification:** All 5 integration tests pass
- **Committed in:** 7b531c0 (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2x Rule 1 bugs)
**Impact on plan:** Both bugs encountered at first execution, fixed immediately. No scope creep.

## Issues Encountered

- `greenlet` not in requirements.txt but required by SQLAlchemy asyncpg dialect at runtime — added to requirements.txt and venv

## User Setup Required

None - DB runs via Docker Compose (`docker compose up db -d`). Migration runs with `DATABASE_URL=... alembic upgrade head`.

## Next Phase Readiness

- `from bot.db.session import get_session, engine` imports without error
- `from bot.db.models import Base, Strategy, ...` imports without error
- All 10 tables exist in PostgreSQL after `alembic upgrade head`
- Plan 01-03 (startup_position_sync) can import session factory and ORM models immediately

## Self-Check: PASSED

All files created and commits verified:
- bot/db/models.py: FOUND
- bot/db/session.py: FOUND
- alembic/versions/0001_initial.py: FOUND
- alembic/env.py: FOUND
- tests/test_migrations.py: FOUND
- Commit b704f08 (TDD RED): FOUND
- Commit b990e66 (feat models+session): FOUND
- Commit 7b531c0 (feat alembic+tests): FOUND

---
*Phase: 01-foundation*
*Completed: 2026-03-19*
