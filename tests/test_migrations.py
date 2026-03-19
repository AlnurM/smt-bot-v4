"""Integration tests for Alembic migrations (Task 2).

These tests require a running PostgreSQL instance with migrations already applied.
Run with: pytest tests/test_migrations.py -x -v
Skip in unit-only runs: pytest -m "not integration"
"""
import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# ---------------------------------------------------------------------------
# Module-level setup: ensure DB is at head before tests run
# ---------------------------------------------------------------------------

TEST_DB_URL = "postgresql+asyncpg://ctb:ctb_password@localhost:5432/ctb"


def _get_alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
    os.environ.setdefault("BINANCE_API_KEY", "test")
    os.environ.setdefault("BINANCE_API_SECRET", "test")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
    os.environ.setdefault("ALLOWED_CHAT_ID", "123")
    return cfg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def ensure_migrations_at_head():
    """Ensure DB is at head revision before each integration test."""
    cfg = _get_alembic_cfg()
    command.upgrade(cfg, "head")
    yield
    # Leave DB at head after tests (don't downgrade — next test run will be clean)


@pytest.fixture
def db_url():
    return TEST_DB_URL


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.integration
async def test_all_tables_exist(db_url):
    """After upgrade head, all 10 tables exist in information_schema.tables."""
    expected = {
        "strategies",
        "strategy_criteria",
        "risk_settings",
        "signals",
        "skipped_coins",
        "orders",
        "positions",
        "trades",
        "daily_stats",
        "logs",
    }
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
            )
            actual = {row[0] for row in result.fetchall()}
    finally:
        await engine.dispose()

    missing = expected - actual
    assert not missing, f"Tables missing after migration: {missing}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_risk_settings_seeded(db_url):
    """risk_settings has exactly 1 seeded row with base_stake_pct=3.0 and leverage=5."""
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            count = await conn.execute(text("SELECT COUNT(*) FROM risk_settings"))
            assert count.scalar() == 1

            row = await conn.execute(
                text("SELECT base_stake_pct, leverage FROM risk_settings LIMIT 1")
            )
            data = row.fetchone()
        assert data is not None
        assert data[0] == 3.0, f"Expected base_stake_pct=3.0, got {data[0]}"
        assert data[1] == 5, f"Expected leverage=5, got {data[1]}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_strategy_criteria_seeded(db_url):
    """strategy_criteria has exactly 1 seeded row with min_total_return_pct=200.0."""
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            count = await conn.execute(text("SELECT COUNT(*) FROM strategy_criteria"))
            assert count.scalar() == 1

            row = await conn.execute(
                text(
                    "SELECT min_total_return_pct, max_drawdown_pct "
                    "FROM strategy_criteria LIMIT 1"
                )
            )
            data = row.fetchone()
        assert data is not None
        assert data[0] == 200.0, f"Expected min_total_return_pct=200.0, got {data[0]}"
        assert data[1] == -12.0, f"Expected max_drawdown_pct=-12.0, got {data[1]}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_migration_at_head(db_url):
    """The database migration version matches the Alembic head revision."""
    cfg = _get_alembic_cfg()
    sd = ScriptDirectory.from_config(cfg)
    head_rev = sd.get_current_head()

    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            current_rev = await conn.run_sync(
                lambda sync_conn: MigrationContext.configure(
                    sync_conn
                ).get_current_revision()
            )
    finally:
        await engine.dispose()

    assert current_rev == head_rev, (
        f"DB is at revision {current_rev!r}, expected head {head_rev!r}"
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_jsonb_columns_are_jsonb_type(db_url):
    """JSONB columns are stored as jsonb type in PostgreSQL, not json."""
    expected_jsonb = [
        ("strategies", "strategy_data"),
        ("strategies", "criteria_snapshot"),
        ("risk_settings", "progressive_stakes"),
        ("skipped_coins", "backtest_results"),
        ("skipped_coins", "failed_criteria"),
    ]
    engine = create_async_engine(db_url, echo=False)
    try:
        async with engine.connect() as conn:
            for table_name, column_name in expected_jsonb:
                result = await conn.execute(
                    text(
                        "SELECT data_type, udt_name FROM information_schema.columns "
                        "WHERE table_name = :table AND column_name = :col"
                    ),
                    {"table": table_name, "col": column_name},
                )
                row = result.fetchone()
                assert row is not None, (
                    f"Column {table_name}.{column_name} not found"
                )
                assert row[1] == "jsonb", (
                    f"{table_name}.{column_name}: expected udt_name='jsonb', "
                    f"got {row[1]!r}"
                )
    finally:
        await engine.dispose()
