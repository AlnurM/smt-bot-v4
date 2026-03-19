import pytest
import os
from unittest.mock import AsyncMock, MagicMock
from pydantic import SecretStr


@pytest.fixture
def test_settings():
    """Settings instance with test values — does not require .env file."""
    from bot.config import Settings
    return Settings(
        binance_api_key=SecretStr("test_binance_key_abc123"),
        binance_api_secret=SecretStr("test_binance_secret_xyz789"),
        telegram_bot_token=SecretStr("123456:test_telegram_token"),
        database_url=SecretStr("postgresql+asyncpg://ctb:ctb_password@localhost:5432/ctb_test"),
        allowed_chat_id=123456789,
        binance_env="testnet",
        anthropic_api_key=SecretStr("test_anthropic_key_abc123"),
    )


@pytest.fixture
def sample_criteria():
    """Plain dict with all strategy criteria fields for use in filter/manager tests."""
    return {
        "backtest_period_months": 6,
        "min_total_return_pct": 200.0,
        "max_drawdown_pct": -12.0,
        "min_win_rate_pct": 55.0,
        "min_profit_factor": 1.8,
        "min_trades": 30,
        "min_avg_rr": 2.0,
        "strict_mode": False,
    }


@pytest.fixture
def mock_binance_client():
    """AsyncMock Binance client — returns testnet-like data."""
    client = AsyncMock()
    client.futures_ping.return_value = {}
    client.futures_account.return_value = {"totalWalletBalance": "15000.00"}
    client.futures_position_information.return_value = []
    return client
