---
phase: 01-foundation
plan: 01
subsystem: infra
tags: [pydantic-settings, loguru, docker, postgres, pytest, pytest-asyncio, python-binance, sqlalchemy, asyncpg, alembic, apscheduler, aiogram]

requires: []

provides:
  - "bot/config.py: pydantic-settings Settings class with SecretStr masking — single source of truth for all env vars"
  - "Docker Compose stack: postgres:16 + bot service with service_healthy healthcheck gate"
  - ".env.example: documented env var template committed to repo"
  - "pytest.ini: asyncio_mode=auto test infrastructure"
  - "tests/conftest.py: test_settings and mock_binance_client fixtures for all future tests"
  - "bot/ package stubs: exchange, db, db/repositories, scheduler sub-packages"
affects:
  - "01-02-PLAN.md"
  - "01-03-PLAN.md"
  - "All phases that import from bot.config"

tech-stack:
  added:
    - "pydantic-settings==2.13.1 (Settings + SecretStr)"
    - "loguru (configure_logging)"
    - "sqlalchemy==2.0.48 (imported in future plans)"
    - "asyncpg==0.31.0 (async PostgreSQL driver)"
    - "alembic==1.18.4 (migrations, used in 01-02)"
    - "python-binance==1.0.35 (Binance async client)"
    - "apscheduler==3.11.2 (AsyncIOScheduler, used in 01-03)"
    - "aiogram==3.26.0 (Telegram bot, used in 01-03)"
    - "pytest==8.3.5 + pytest-asyncio==0.24.0"
  patterns:
    - "pydantic-settings BaseSettings with SecretStr for all secrets — never exposed in repr/str/logs"
    - "Fail-fast module-level Settings instantiation — sys.exit(1) on missing required var"
    - "TDD Red-Green: test first, implement to pass"

key-files:
  created:
    - "bot/config.py"
    - "docker-compose.yml"
    - ".env.example"
    - "pytest.ini"
    - "tests/conftest.py"
    - "tests/test_config.py"
    - "requirements.txt"
    - "requirements-dev.txt"
    - "pyproject.toml"
    - "Dockerfile"
    - "bot/__init__.py"
    - "bot/exchange/__init__.py"
    - "bot/db/__init__.py"
    - "bot/db/repositories/__init__.py"
    - "bot/scheduler/__init__.py"
    - "tests/__init__.py"
  modified:
    - ".gitignore"

key-decisions:
  - "SecretStr on all secret fields (API keys, tokens, database_url) — pydantic automatically masks in repr/str, no custom logging filter needed"
  - "Module-level settings = Settings() with ValidationError catch and sys.exit(1) — fail fast if any required var missing"
  - "postgres:16 pinned (not latest) — ensures gen_random_uuid() built-in without pgcrypto extension"
  - "asyncio_default_fixture_loop_scope=function added to pytest.ini — suppresses pytest-asyncio deprecation warning on Python 3.14"
  - "test_missing_required_var uses monkeypatch.delenv to unset BINANCE_API_KEY — required because env var is set during test run"

patterns-established:
  - "Settings injection: all modules receive Settings via parameter, never import settings directly"
  - "test_settings fixture: creates Settings with hardcoded test values, no .env file required"
  - "TDD with monkeypatch: use monkeypatch.delenv when testing missing env var behavior"

requirements-completed: [INFRA-02, INFRA-05, INFRA-06]

duration: 3min
completed: 2026-03-19
---

# Phase 1 Plan 01: Project Scaffold, Config Module, and Docker Stack Summary

**pydantic-settings Settings class with SecretStr masking for all secrets, fail-fast validation, pytest infrastructure with asyncio_mode=auto, and Docker Compose stack with postgres:16 + service_healthy healthcheck**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-19T10:58:52Z
- **Completed:** 2026-03-19T11:02:28Z
- **Tasks:** 1
- **Files modified:** 16 created, 1 modified

## Accomplishments

- bot/config.py Settings class exports `settings`, `Settings`, `configure_logging` — contract for all future plans
- All 5 test_config.py tests pass (TDD Red-Green): secret masking, missing var, binance_env validation, defaults, logging
- Docker Compose stack with postgres:16, healthcheck via pg_isready, bot depends on service_healthy
- pytest.ini with asyncio_mode=auto and asyncio_default_fixture_loop_scope=function
- Complete directory structure: bot/exchange, bot/db, bot/db/repositories, bot/scheduler stubs

## Task Commits

Each task was committed atomically:

1. **TDD RED — failing tests** - `3c5b79b` (test)
2. **Task 1: Project scaffold, packaging, Docker stack, and config module** - `54e14b9` (feat)

**Plan metadata:** (docs commit follows)

_Note: TDD task had separate RED commit (failing tests) then GREEN commit (implementation + fix)_

## Files Created/Modified

- `bot/config.py` - pydantic-settings Settings with SecretStr, configure_logging, fail-fast module-level instantiation
- `docker-compose.yml` - postgres:16 + bot services, healthcheck, service_healthy depends_on
- `.env.example` - all env vars documented with comments, BINANCE_API_KEY placeholder present
- `pytest.ini` - asyncio_mode=auto, asyncio_default_fixture_loop_scope=function, markers
- `tests/conftest.py` - test_settings fixture (no .env required), mock_binance_client fixture
- `tests/test_config.py` - 5 tests covering INFRA-02 requirements
- `requirements.txt` - pinned: pydantic-settings 2.13.1, sqlalchemy 2.0.48, asyncpg 0.31.0, etc.
- `requirements-dev.txt` - pytest 8.3.5 + pytest-asyncio 0.24.0
- `pyproject.toml` - Python 3.12 package declaration
- `Dockerfile` - python:3.12-slim with requirements install
- `bot/` stubs - exchange, db, db/repositories, scheduler __init__.py files
- `.gitignore` - updated to include __pycache__, .venv, *.pyc, etc.

## Decisions Made

- Used `monkeypatch.delenv` in `test_missing_required_var` because the test runner sets `BINANCE_API_KEY` in the environment, which pydantic-settings reads even when the field is not passed as a constructor argument.
- Added `asyncio_default_fixture_loop_scope = function` to pytest.ini to silence pytest-asyncio deprecation warning on Python 3.14 host environment (still compatible with Python 3.12 target).
- `.venv/` added to `.gitignore` (deviation from plan spec, but necessary since venv was created in project root).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_missing_required_var to use monkeypatch.delenv**
- **Found during:** Task 1 (TDD GREEN verification)
- **Issue:** test_missing_required_var did not unset BINANCE_API_KEY before instantiating Settings without it; pydantic-settings read the env var from the process environment, causing the test not to raise ValidationError
- **Fix:** Added `monkeypatch` parameter and `monkeypatch.delenv("BINANCE_API_KEY", raising=False)` before Settings instantiation
- **Files modified:** tests/test_config.py
- **Verification:** All 5 tests pass with `pytest tests/test_config.py -x -q`
- **Committed in:** 54e14b9 (Task 1 feat commit)

**2. [Rule 2 - Missing Critical] Added asyncio_default_fixture_loop_scope to pytest.ini**
- **Found during:** Task 1 (first test run)
- **Issue:** pytest-asyncio emitted PytestDeprecationWarning about asyncio_default_fixture_loop_scope being unset; while not blocking, suppressing it prevents noise in all future test runs
- **Fix:** Added `asyncio_default_fixture_loop_scope = function` to [pytest] section in pytest.ini
- **Files modified:** pytest.ini
- **Verification:** Warning absent from test output after fix
- **Committed in:** 54e14b9 (Task 1 feat commit)

---

**Total deviations:** 2 auto-fixed (1 bug fix, 1 missing critical)
**Impact on plan:** Both fixes necessary for test correctness and clean test output. No scope creep.

## Issues Encountered

- Python 3.14 on host machine (project targets 3.12). Tests pass correctly on 3.14; asyncio deprecation warnings from pytest-asyncio are from 3.14's updated asyncio API, not from project code.

## User Setup Required

None - no external service configuration required for this plan. Docker Compose verification is optional (manual step from the verification section).

## Next Phase Readiness

- `from bot.config import settings, Settings, configure_logging` is ready for 01-02 (DB models + Alembic) and 01-03 (exchange client + scheduler)
- All required env vars documented in `.env.example`; user must create `.env` from it before running
- Docker Compose stack ready to test with `docker compose up db -d`

## Self-Check: PASSED

- bot/config.py: FOUND
- docker-compose.yml: FOUND
- .env.example: FOUND
- pytest.ini: FOUND
- tests/conftest.py: FOUND
- tests/test_config.py: FOUND
- Commit 3c5b79b (TDD RED): FOUND
- Commit 54e14b9 (TDD GREEN feat): FOUND

---
*Phase: 01-foundation*
*Completed: 2026-03-19*
