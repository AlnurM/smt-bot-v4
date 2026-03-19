"""Tests for bot/exchange/client.py — INFRA-01: testnet/production toggle, no secret leaks."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pydantic import SecretStr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def testnet_settings(test_settings):
    """Settings with binance_env=testnet."""
    from bot.config import Settings

    return Settings(
        binance_api_key=SecretStr("test_binance_key_abc123"),
        binance_api_secret=SecretStr("test_binance_secret_xyz789"),
        telegram_bot_token=SecretStr("123456:test_telegram_token"),
        database_url=SecretStr("postgresql+asyncpg://u:p@localhost/db"),
        allowed_chat_id=123456789,
        binance_env="testnet",
    )


@pytest.fixture
def production_settings():
    """Settings with binance_env=production."""
    from bot.config import Settings

    return Settings(
        binance_api_key=SecretStr("prod_binance_key_abc123"),
        binance_api_secret=SecretStr("prod_binance_secret_xyz789"),
        telegram_bot_token=SecretStr("123456:test_telegram_token"),
        database_url=SecretStr("postgresql+asyncpg://u:p@localhost/db"),
        allowed_chat_id=123456789,
        binance_env="production",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_testnet_toggle(testnet_settings):
    """When binance_env=testnet, AsyncClient.create must be called with testnet=True."""
    with patch("bot.exchange.client.AsyncClient") as mock_cls:
        mock_cls.create = AsyncMock(return_value=MagicMock())
        from bot.exchange.client import create_binance_client

        await create_binance_client(testnet_settings)

        mock_cls.create.assert_called_once()
        _, kwargs = mock_cls.create.call_args
        assert kwargs["testnet"] is True


@pytest.mark.asyncio
async def test_production_toggle(production_settings):
    """When binance_env=production, AsyncClient.create must be called with testnet=False."""
    with patch("bot.exchange.client.AsyncClient") as mock_cls:
        mock_cls.create = AsyncMock(return_value=MagicMock())
        from bot.exchange.client import create_binance_client

        await create_binance_client(production_settings)

        mock_cls.create.assert_called_once()
        _, kwargs = mock_cls.create.call_args
        assert kwargs["testnet"] is False


@pytest.mark.asyncio
async def test_no_key_in_logs(testnet_settings, caplog):
    """API key secret value must NOT appear in any log output during client creation."""
    import logging

    with patch("bot.exchange.client.AsyncClient") as mock_cls:
        mock_cls.create = AsyncMock(return_value=MagicMock())
        from bot.exchange.client import create_binance_client

        with caplog.at_level(logging.DEBUG):
            await create_binance_client(testnet_settings)

    secret_value = testnet_settings.binance_api_key.get_secret_value()
    for record in caplog.records:
        assert secret_value not in record.message, (
            f"API key found in log: {record.message}"
        )
