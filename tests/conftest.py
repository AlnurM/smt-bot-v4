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
    # Futures order methods for Phase 5
    client.futures_change_margin_type.return_value = {}
    client.futures_change_leverage.return_value = {"leverage": 5, "symbol": "BTCUSDT"}
    client.futures_create_order.return_value = {
        "orderId": 1001,
        "status": "FILLED",
        "avgPrice": "145.00",
        "executedQty": "3.0",
        "origQty": "3.0",
        "side": "BUY",
        "type": "MARKET",
    }
    client.futures_get_order.return_value = {
        "orderId": 1002,
        "status": "NEW",
        "avgPrice": "0.00",
        "type": "STOP_MARKET",
    }
    client.futures_cancel_order.return_value = {"status": "CANCELED", "orderId": 1002}
    client.futures_account_trades.return_value = [
        {"orderId": 1001, "realizedPnl": "10.00", "symbol": "BTCUSDT"}
    ]
    client.futures_symbol_ticker.return_value = {"price": "145.00", "symbol": "BTCUSDT"}
    client.futures_exchange_info.return_value = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                ],
            }
        ]
    }
    return client


@pytest.fixture
def mock_signal():
    """SimpleNamespace signal with all fields needed by the order executor."""
    import types
    import uuid
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        symbol="BTCUSDT",
        direction="long",
        entry_price=145.0,
        stop_loss=140.0,
        take_profit=160.0,
        rr_ratio=3.0,
        status="confirmed",
    )


@pytest.fixture
def mock_risk_settings():
    """SimpleNamespace risk settings with all fields needed by the order executor."""
    import types
    return types.SimpleNamespace(
        leverage=5,
        base_stake_pct=3.0,
        current_stake_pct=3.0,
        max_open_positions=5,
        daily_loss_limit_pct=5.0,
        win_streak_current=0,
        progressive_stakes=[3.0, 5.0, 8.0],
        wins_to_increase=1,
    )
