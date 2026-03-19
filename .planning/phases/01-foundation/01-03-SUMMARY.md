---
phase: 01-foundation
plan: 03
subsystem: infra
tags: [python-binance, apscheduler, aiogram, asyncio, startup-sequence, position-sync, sigterm]

requires:
  - phase: 01-foundation-01
    provides: Settings with binance_env/binance_api_key/binance_api_secret, configure_logging
  - phase: 01-foundation-02
    provides: SessionLocal async_sessionmaker, Position ORM model, engine

provides:
  - "bot/exchange/client.py: create_binance_client() — testnet/production toggle via settings.binance_env"
  - "bot/scheduler/setup.py: create_scheduler() — AsyncIOScheduler with MemoryJobStore, UTC, coalesce=True"
  - "bot/main.py: asyncio.run(main()) entrypoint — 3-step fail-fast startup, position sync, SIGTERM handler"
  - "startup_position_sync(): reconciles Binance open positions with DB positions table on every restart"

affects:
  - 02-market-scanner
  - all-phases

tech-stack:
  added: [aiosqlite (dev/test)]
  patterns:
    - "create_*() factory functions — no module-level instantiation of async clients or schedulers"
    - "startup_position_sync() called non-fatally — position errors never prevent bot startup"
    - "aiogram handle_signals=True — dp.start_polling() owns SIGTERM/SIGINT lifecycle"
    - "loguru SecretStr objects (not .get_secret_value()) passed to logger — pydantic masks in repr"

key-files:
  created:
    - bot/exchange/client.py
    - bot/scheduler/setup.py
    - bot/main.py
    - tests/test_exchange_client.py
    - tests/test_scheduler.py
    - tests/test_main.py
    - tests/test_startup.py
  modified:
    - requirements-dev.txt

key-decisions:
  - "APScheduler not started at import time — create_scheduler() returns instance only; scheduler.start() called in main() after event loop is running"
  - "startup_position_sync() is non-fatal — position sync failure logged as warning, bot continues startup"
  - "session.add() is sync in SQLAlchemy; only execute/commit/rollback are async — test mocks use MagicMock for add(), AsyncMock for execute()/commit()"
  - "loguru caplog incompatibility — loguru writes to stderr, not stdlib logging; test uses logger.add() custom sink to capture log output"
  - "aiosqlite added to requirements-dev.txt for SQLite-based async test infrastructure"

patterns-established:
  - "Pattern: All async client/scheduler creation deferred to main() — never at import/module level"
  - "Pattern: Test mock sessions use MagicMock base with AsyncMock on specific async methods (execute, commit)"
  - "Pattern: Loguru log capture in tests via logger.add(sink_fn, level=...) + logger.remove(sink_id)"

requirements-completed: [INFRA-01, INFRA-04, INFRA-05, INFRA-07, INFRA-08]

duration: 45min
completed: 2026-03-19
---

# Phase 01 Plan 03: Runtime Wiring Summary

**Binance AsyncClient with testnet/production toggle, APScheduler factory, and asyncio main() with fail-fast startup checks, position sync on restart, and aiogram SIGTERM shutdown**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-03-19T16:00:00Z
- **Completed:** 2026-03-19T16:45:00Z
- **Tasks:** 2 of 3 (Task 3 is human-verify checkpoint)
- **Files modified:** 8

## Accomplishments

- `create_binance_client(settings)` calls `AsyncClient.create(testnet=True/False)` based on `settings.binance_env`; API keys never appear in logs
- `create_scheduler()` returns `AsyncIOScheduler` with `MemoryJobStore`, `coalesce=True`, `max_instances=1`, UTC timezone; never started at import time
- `main()` fails fast on any of three dependency checks (DB, Binance, Telegram) before accepting work, then starts scheduler and Telegram polling
- `startup_position_sync()` creates DB rows for Binance positions not in DB and logs warnings for DB positions not on Binance (manual review, no auto-close)
- 11 unit tests all pass; no live DB or network required

## Task Commits

Each task was committed atomically:

1. **Task 1: BinanceClient wrapper and APScheduler factory** - `bc19226` (feat)
2. **Task 2: main.py startup sequence, position sync, graceful shutdown** - `24d97b3` (feat)

_Task 3 is a human-verify checkpoint — Docker Compose smoke test requires user action._

## Files Created/Modified

- `bot/exchange/client.py` - create_binance_client() with testnet/production toggle
- `bot/scheduler/setup.py` - create_scheduler() with MemoryJobStore, coalesce/max_instances defaults
- `bot/main.py` - Full startup sequence: DB/Binance/Telegram checks, position sync, scheduler, aiogram polling
- `tests/test_exchange_client.py` - 3 tests: testnet toggle, production toggle, no-key-in-logs
- `tests/test_scheduler.py` - 3 tests: scheduler creation, no import-time start, job defaults
- `tests/test_main.py` - 2 tests: fail-fast DB check, fail-fast Binance check
- `tests/test_startup.py` - 3 tests: position sync create/skip/reconcile-warning
- `requirements-dev.txt` - Added aiosqlite for async test infrastructure

## Decisions Made

- `APScheduler.start()` must be called inside the running event loop — `create_scheduler()` returns the instance only; placing `start()` in `main()` after all checks pass avoids the "no running event loop" error
- `startup_position_sync()` is non-fatal — a position sync failure during restart should never prevent the bot from starting since SL/TP brackets are already live on Binance
- Test mocking: `session.add()` is synchronous in SQLAlchemy 2.0 — mocks must use `MagicMock` for `add()` and `AsyncMock` for `execute()`/`commit()` or the side_effect never fires
- Loguru bypasses pytest's `caplog` — log capture in tests requires a custom loguru sink (`logger.add(fn, level)`) rather than `caplog`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed scheduler timezone test assertion for Python 3.14**
- **Found during:** Task 1 (test_scheduler_creates)
- **Issue:** APScheduler 3.11.2 on Python 3.14 stores timezone as `datetime.timezone.utc` (stdlib), not `pytz.utc` — the test `assert scheduler.timezone == pytz.utc` fails with `AssertionError: assert datetime.timezone.utc == <UTC>`
- **Fix:** Updated assertion to accept both `pytz.utc` and `datetime.timezone.utc` via a try/import pattern
- **Files modified:** tests/test_scheduler.py
- **Verification:** `pytest tests/test_scheduler.py` passes
- **Committed in:** bc19226 (Task 1 commit)

**2. [Rule 3 - Blocking] Installed aiosqlite for async SQLite test support**
- **Found during:** Task 2 (in-memory session fixture for test_startup.py)
- **Issue:** `ModuleNotFoundError: No module named 'aiosqlite'` — SQLite+aiosqlite needed for in-memory DB in tests
- **Fix:** `.venv/bin/pip install aiosqlite`; added to `requirements-dev.txt`
- **Files modified:** requirements-dev.txt
- **Verification:** aiosqlite import succeeds
- **Committed in:** 24d97b3 (Task 2 commit)

**3. [Rule 1 - Bug] Fixed test_startup.py mock session for SQLAlchemy sync/async API**
- **Found during:** Task 2 (test_position_sync_creates_missing)
- **Issue:** Using `AsyncMock()` for the entire session object caused `session.add()` to return an unawaited coroutine since `add()` is actually synchronous — `side_effect` never fired, `added_positions` stayed empty
- **Fix:** Changed mock sessions to `MagicMock()` base with `session.add = MagicMock(side_effect=...)` and `session.execute = AsyncMock(return_value=...)` explicitly
- **Files modified:** tests/test_startup.py
- **Verification:** All 3 startup tests pass
- **Committed in:** 24d97b3 (Task 2 commit)

**4. [Rule 1 - Bug] Fixed log capture for loguru in test_position_sync_reconciles_closed**
- **Found during:** Task 2 (test_position_sync_reconciles_closed)
- **Issue:** `caplog` captures stdlib `logging` only; loguru writes directly to stderr bypassing pytest's caplog handler — log assertion always failed with empty string even though warning appeared in terminal
- **Fix:** Used `logger.add(lambda msg: log_messages.append(msg), level="WARNING")` + `logger.remove(sink_id)` to capture loguru output directly
- **Files modified:** tests/test_startup.py
- **Verification:** Test passes; "Manual review" found in captured messages
- **Committed in:** 24d97b3 (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (2 bugs in test assertions, 1 blocking missing dependency, 1 bug in mock API usage)
**Impact on plan:** All auto-fixes were test-layer correctness issues. Production code (main.py, client.py, setup.py) implemented exactly as planned with no scope changes.

## Issues Encountered

- SQLite incompatibility with JSONB PostgreSQL type: initial `in_memory_session_factory` fixture tried `Base.metadata.create_all` which includes JSONB columns. Pivoted to fully mocked session objects (no real DB needed for unit tests of position sync logic).

## User Setup Required

None — this plan wires existing credentials from `.env` (set up in plan 01-01). For Task 3 Docker smoke test, user needs real Binance Testnet API keys and Telegram bot token in `.env`.

## Next Phase Readiness

- All INFRA requirements (01, 04, 05, 07, 08) implemented and unit-tested
- Docker Compose smoke test (Task 3) requires user action: set up `.env` with real credentials and run `docker compose up --build`
- Once Task 3 checkpoint is approved, Phase 1 is complete and Phase 2 (Market Scanner) can begin
- Phase 2 will call `create_scheduler()` and register cron jobs — the scheduler factory is ready

---
*Phase: 01-foundation*
*Completed: 2026-03-19*
