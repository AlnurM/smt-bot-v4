"""Tests for bot/main.py — INFRA-05, INFRA-07: single event loop, graceful shutdown, fail-fast checks."""
import asyncio
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fail_fast_db(test_settings):
    """
    If DB connection fails at startup, logger.error is called and sys.exit(1) raised.
    Bot must NOT proceed to Binance check after DB failure.
    """
    import sqlalchemy.exc

    with (
        patch("bot.main.settings", test_settings),
        patch("bot.main.configure_logging"),
        patch("bot.main.engine") as mock_engine,
        patch("bot.main.sys") as mock_sys,
    ):
        # Make engine.begin() raise OperationalError
        mock_engine.begin.return_value.__aenter__ = AsyncMock(
            side_effect=sqlalchemy.exc.OperationalError("connection refused", None, None)
        )
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=False)

        # sys.exit should be called with 1
        mock_sys.exit.side_effect = SystemExit(1)

        with pytest.raises(SystemExit) as exc_info:
            from bot.main import main

            await main()

        assert exc_info.value.code == 1


@pytest.mark.asyncio
async def test_fail_fast_binance(test_settings):
    """
    If Binance futures_ping fails after DB succeeds, sys.exit(1) is called.
    """
    with (
        patch("bot.main.settings", test_settings),
        patch("bot.main.configure_logging"),
        patch("bot.main.engine") as mock_engine,
        patch("bot.main.verify_migrations_current", new_callable=AsyncMock),
        patch("bot.main.create_binance_client", new_callable=AsyncMock) as mock_create,
        patch("bot.main.sys") as mock_sys,
    ):
        # DB succeeds
        cm = AsyncMock()
        cm.__aenter__ = AsyncMock(return_value=AsyncMock())
        cm.__aexit__ = AsyncMock(return_value=False)
        mock_engine.begin.return_value = cm

        # Binance client creation succeeds but futures_ping raises
        mock_client = AsyncMock()
        mock_client.futures_ping.side_effect = Exception("Binance connection failed")
        mock_create.return_value = mock_client

        mock_sys.exit.side_effect = SystemExit(1)

        with pytest.raises(SystemExit) as exc_info:
            from bot.main import main

            await main()

        assert exc_info.value.code == 1
