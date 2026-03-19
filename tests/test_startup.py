"""Tests for startup_position_sync() — INFRA-08: position reconciliation on restart."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from contextlib import asynccontextmanager


# ---------------------------------------------------------------------------
# Helper: build a fake Position-like object
# ---------------------------------------------------------------------------


def make_position(symbol, side, status="open", environment="testnet"):
    """Return a MagicMock mimicking a Position ORM row."""
    p = MagicMock()
    p.symbol = symbol
    p.side = side
    p.status = status
    p.environment = environment
    p.id = uuid.uuid4()
    return p


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def binance_one_position():
    """Binance returns one open BTCUSDT long position."""
    client = AsyncMock()
    client.futures_position_information.return_value = [
        {
            "symbol": "BTCUSDT",
            "positionAmt": "0.1",
            "entryPrice": "50000.0",
            "markPrice": "51000.0",
            "unRealizedProfit": "100.0",
        }
    ]
    return client


@pytest.fixture
def binance_no_positions():
    """Binance returns no open positions."""
    client = AsyncMock()
    client.futures_position_information.return_value = []
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_position_sync_creates_missing(binance_one_position):
    """
    When Binance returns 1 open position not in DB,
    startup_position_sync should call session.add() to create a Position row.
    """
    from bot.main import startup_position_sync

    added_positions = []

    # Build a mock session — add() is sync in SQLAlchemy, execute/commit are async
    mock_session = MagicMock()
    mock_session.add = MagicMock(side_effect=lambda pos: added_positions.append(pos))
    mock_session.commit = AsyncMock()

    # SELECT returns no existing position (empty result)
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Second session context: db_open check
    mock_result_2 = MagicMock()
    mock_result_2.scalars.return_value.all.return_value = []
    mock_session_2 = MagicMock()
    mock_session_2.execute = AsyncMock(return_value=mock_result_2)
    mock_session_2.commit = AsyncMock()

    call_count = {"n": 0}

    @asynccontextmanager
    async def mock_session_factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield mock_session
        else:
            yield mock_session_2

    await startup_position_sync(binance_one_position, mock_session_factory)

    assert len(added_positions) == 1, (
        f"Expected 1 Position to be added, got {len(added_positions)}"
    )
    pos = added_positions[0]
    assert pos.symbol == "BTCUSDT"
    assert pos.side == "long"
    assert pos.entry_price == 50000.0
    assert pos.quantity == 0.1


@pytest.mark.asyncio
async def test_position_sync_skips_existing(binance_one_position):
    """
    When Binance returns 1 open position already in DB,
    startup_position_sync should NOT call session.add().
    """
    from bot.main import startup_position_sync

    existing_pos = make_position("BTCUSDT", "long")

    mock_session = MagicMock()
    # SELECT returns an existing position
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_pos
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_2 = MagicMock()
    mock_result_2 = MagicMock()
    mock_result_2.scalars.return_value.all.return_value = [existing_pos]
    mock_session_2.execute = AsyncMock(return_value=mock_result_2)
    mock_session_2.commit = AsyncMock()

    call_count = {"n": 0}

    @asynccontextmanager
    async def mock_session_factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield mock_session
        else:
            yield mock_session_2

    await startup_position_sync(binance_one_position, mock_session_factory)

    mock_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_position_sync_reconciles_closed(binance_no_positions):
    """
    When DB has open position that Binance does NOT return,
    startup_position_sync should log a warning containing 'Manual review'.

    Uses a loguru sink to capture log output directly.
    """
    from loguru import logger

    from bot.main import startup_position_sync

    orphan_pos = make_position("BTCUSDT", "long")

    mock_session = MagicMock()
    # First context (no open_binance to iterate over): commit immediately
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    mock_session_2 = MagicMock()
    mock_result_2 = MagicMock()
    mock_result_2.scalars.return_value.all.return_value = [orphan_pos]
    mock_session_2.execute = AsyncMock(return_value=mock_result_2)
    mock_session_2.commit = AsyncMock()

    call_count = {"n": 0}

    @asynccontextmanager
    async def mock_session_factory():
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield mock_session
        else:
            yield mock_session_2

    # Capture loguru log messages via a custom sink
    log_messages = []
    sink_id = logger.add(lambda msg: log_messages.append(msg), level="WARNING")

    try:
        await startup_position_sync(binance_no_positions, mock_session_factory)
    finally:
        logger.remove(sink_id)

    all_output = " ".join(str(m) for m in log_messages)
    assert "Manual review" in all_output, (
        f"Expected 'Manual review' in log output. Got: {all_output!r}"
    )
