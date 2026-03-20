"""Tests for daily summary notification (TG-19)."""
import pytest
pytest.importorskip("bot.reporting.daily_summary")

import types
import uuid
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock, MagicMock, patch, AsyncMock


# ---------------------------------------------------------------------------
# pnl_sign_fmt
# ---------------------------------------------------------------------------

def test_pnl_sign_fmt_positive():
    from bot.reporting.daily_summary import pnl_sign_fmt
    assert pnl_sign_fmt(12.5) == "+$12.50"


def test_pnl_sign_fmt_negative():
    from bot.reporting.daily_summary import pnl_sign_fmt
    assert pnl_sign_fmt(-3.1) == "-$3.10"


def test_pnl_sign_fmt_zero():
    from bot.reporting.daily_summary import pnl_sign_fmt
    assert pnl_sign_fmt(0.0) == "+$0.00"


# ---------------------------------------------------------------------------
# send_daily_summary — zero trade day
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_daily_summary_zero_trades(test_settings, mock_binance_client):
    """Zero-trade day sends 'Нет сделок за сегодня' message."""
    from bot.reporting.daily_summary import send_daily_summary

    # Mock session that returns no stats and no trades
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # stats result: no row
    stats_result = MagicMock()
    stats_result.scalars.return_value.first.return_value = None

    # trades result: empty
    trades_result = MagicMock()
    trades_result.scalars.return_value.all.return_value = []

    # active count result
    active_result = MagicMock()
    active_result.scalar.return_value = 2

    # due count result
    due_result = MagicMock()
    due_result.scalar.return_value = 1

    # risk result: no row
    risk_result = MagicMock()
    risk_result.scalars.return_value.first.return_value = None

    mock_session.execute = AsyncMock(
        side_effect=[stats_result, trades_result, active_result, due_result, risk_result]
    )

    session_factory = MagicMock(return_value=mock_session)

    bot = AsyncMock()

    await send_daily_summary(session_factory, mock_binance_client, test_settings, bot)

    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    message_text = call_args[0][1]

    assert "Нет сделок за сегодня" in message_text
    assert "Баланс:" in message_text
    assert "Ставка:" in message_text


# ---------------------------------------------------------------------------
# send_daily_summary — trade day
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_daily_summary_with_trades(test_settings, mock_binance_client):
    """Trade day sends full summary with PnL, win rate, best/worst trade."""
    from bot.reporting.daily_summary import send_daily_summary

    # Build mock stats
    mock_stats = types.SimpleNamespace(
        total_pnl=150.75,
        trade_count=5,
        win_count=4,
        win_rate=80.0,
    )

    # Build mock trades
    trade1 = types.SimpleNamespace(symbol="BTCUSDT", realized_pnl=100.0)
    trade2 = types.SimpleNamespace(symbol="ETHUSDT", realized_pnl=-20.0)
    trade3 = types.SimpleNamespace(symbol="SOLUSDT", realized_pnl=70.75)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    stats_result = MagicMock()
    stats_result.scalars.return_value.first.return_value = mock_stats

    trades_result = MagicMock()
    trades_result.scalars.return_value.all.return_value = [trade1, trade2, trade3]

    active_result = MagicMock()
    active_result.scalar.return_value = 3

    due_result = MagicMock()
    due_result.scalar.return_value = 1

    mock_risk = types.SimpleNamespace(current_stake_pct=5.0)
    risk_result = MagicMock()
    risk_result.scalars.return_value.first.return_value = mock_risk

    mock_session.execute = AsyncMock(
        side_effect=[stats_result, trades_result, active_result, due_result, risk_result]
    )

    session_factory = MagicMock(return_value=mock_session)
    bot = AsyncMock()

    await send_daily_summary(session_factory, mock_binance_client, test_settings, bot)

    bot.send_message.assert_called_once()
    message_text = bot.send_message.call_args[0][1]

    assert "PnL" in message_text
    assert "Сделок" in message_text
    assert "Win Rate" in message_text
    assert "BTCUSDT" in message_text  # best trade
    assert "ETHUSDT" in message_text  # worst trade
    assert "3 активных" in message_text


# ---------------------------------------------------------------------------
# send_daily_summary — exception does not propagate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_daily_summary_exception_does_not_propagate(test_settings):
    """Exception in summary handler sends fallback alert, never raises."""
    from bot.reporting.daily_summary import send_daily_summary

    # session_factory raises
    session_factory = MagicMock(side_effect=RuntimeError("DB down"))
    binance_client = AsyncMock()
    bot = AsyncMock()

    # Must NOT raise
    await send_daily_summary(session_factory, binance_client, test_settings, bot)

    # Should attempt fallback error alert
    bot.send_message.assert_called_once()
    message_text = bot.send_message.call_args[0][1]
    assert "Ошибка" in message_text
