"""Tests for bot/order/executor.py — order execution, dry-run, double-tap, error handling.

Covers: ORD-01, ORD-02, ORD-03, ORD-04, ORD-05 and dry-run mode.
"""
import uuid
import types
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

pytest.importorskip("bot.order.executor")

from bot.order.executor import execute_order, _exchange_info_cache  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_session_factory(signal=None, risk=None, stats=None, open_count=0):
    """Build an async context-manager session_factory mock.

    The returned session supports execute() for Signal, RiskSettings, DailyStats, Position
    queries, flush(), refresh(), and add().
    """
    import types as _types

    def _make_scalar_result(obj):
        r = MagicMock()
        r.scalar_one_or_none.return_value = obj
        r.scalar_one.return_value = obj
        r.scalar.return_value = obj
        return r

    async def _execute(stmt, **kwargs):
        # Inspect the statement to decide what to return.
        # We use a simple dispatch on the first column type in whereclause.
        stmt_str = str(stmt)
        if "signals" in stmt_str:
            return _make_scalar_result(signal)
        if "risk_settings" in stmt_str:
            return _make_scalar_result(risk)
        if "daily_stats" in stmt_str:
            return _make_scalar_result(stats)
        if "positions" in stmt_str:
            # count query
            r = MagicMock()
            r.scalar.return_value = open_count
            r.scalar_one_or_none.return_value = None
            return r
        return _make_scalar_result(None)

    session = AsyncMock()
    session.execute.side_effect = _execute
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    session.get = AsyncMock(return_value=None)

    # Context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock()
    factory.return_value = session
    return factory, session


def make_settings():
    s = MagicMock()
    s.allowed_chat_id = 123456789
    s.binance_env = "testnet"
    return s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_dry_run_mode(mock_binance_client, mock_signal, mock_risk_settings):
    """Dry-run: no Binance order API called; Order created with status='dry_run'."""
    factory, session = make_session_factory(signal=mock_signal)
    settings = make_settings()
    bot = AsyncMock()

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": True, "paused": False}):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    mock_binance_client.futures_create_order.assert_not_called()
    bot.send_message.assert_called_once()
    msg = bot.send_message.call_args[0][1]
    assert "[DRY RUN]" in msg


async def test_double_tap_protection(mock_binance_client, mock_signal, mock_risk_settings):
    """Double-tap: if signal is not 'confirmed', execute_order returns without placing order."""
    # Return None from the SELECT FOR UPDATE (signal not in 'confirmed' state)
    factory, session = make_session_factory(signal=None)
    settings = make_settings()
    bot = AsyncMock()

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    mock_binance_client.futures_create_order.assert_not_called()
    bot.send_message.assert_not_called()


async def test_market_order_placed(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-01: A confirmed signal triggers a MARKET entry order on Binance Futures."""
    factory, session = make_session_factory(
        signal=mock_signal,
        risk=mock_risk_settings,
    )
    settings = make_settings()
    bot = AsyncMock()

    # Make the position refresh work without error
    session.refresh = AsyncMock()

    # Position.id needs to be a uuid for later queries — simulate with attribute
    order_obj = MagicMock()
    order_obj.id = uuid.uuid4()
    position_obj = MagicMock()
    position_obj.id = uuid.uuid4()

    # After flush, refresh is called — set id attributes via side_effect
    async def _refresh(obj):
        if hasattr(obj, 'sl_order_id'):
            obj.id = position_obj.id
        else:
            obj.id = order_obj.id

    session.refresh.side_effect = _refresh

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}), \
         patch("bot.order.executor._exchange_info_cache", {}):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    calls = mock_binance_client.futures_create_order.call_args_list
    assert len(calls) >= 1
    market_calls = [c for c in calls if c.kwargs.get("type") == "MARKET" or
                    (len(c.args) > 3 and c.args[3] == "MARKET")]
    # Check that at least one call includes type=MARKET
    all_kwargs = [c.kwargs for c in calls]
    market_call = next((k for k in all_kwargs if k.get("type") == "MARKET"), None)
    assert market_call is not None, f"No MARKET order call found in: {all_kwargs}"
    assert market_call["symbol"] == "BTCUSDT"
    assert market_call["side"] == "BUY"  # long signal


async def test_bracket_orders_placed(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-02: After MARKET entry fills, STOP_MARKET and TAKE_PROFIT_MARKET are placed."""
    factory, session = make_session_factory(
        signal=mock_signal,
        risk=mock_risk_settings,
    )
    settings = make_settings()
    bot = AsyncMock()
    session.refresh = AsyncMock()

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}), \
         patch("bot.order.executor._exchange_info_cache", {}):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    all_kwargs = [c.kwargs for c in mock_binance_client.futures_create_order.call_args_list]
    types_used = [k.get("type") for k in all_kwargs]

    assert "MARKET" in types_used, f"MARKET not in {types_used}"
    assert "STOP_MARKET" in types_used, f"STOP_MARKET not in {types_used}"
    assert "TAKE_PROFIT_MARKET" in types_used, f"TAKE_PROFIT_MARKET not in {types_used}"

    # Bracket orders must use closePosition=True and workingType=MARK_PRICE
    stop_call = next(k for k in all_kwargs if k.get("type") == "STOP_MARKET")
    tp_call = next(k for k in all_kwargs if k.get("type") == "TAKE_PROFIT_MARKET")
    assert stop_call["closePosition"] is True
    assert stop_call["workingType"] == "MARK_PRICE"
    assert tp_call["closePosition"] is True
    assert tp_call["workingType"] == "MARK_PRICE"


async def test_confirmation_notification(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-03: bot.send_message is called with fill price after successful execution."""
    factory, session = make_session_factory(
        signal=mock_signal,
        risk=mock_risk_settings,
    )
    settings = make_settings()
    bot = AsyncMock()
    session.refresh = AsyncMock()

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}), \
         patch("bot.order.executor._exchange_info_cache", {}):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    bot.send_message.assert_called_once()
    # conftest returns avgPrice="145.00"
    msg = bot.send_message.call_args[0][1]
    assert "145.00" in msg, f"Fill price not found in message: {msg}"


async def test_error_handling(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-04: BinanceAPIException triggers send_error_alert; signal marked 'failed'."""
    from binance.exceptions import BinanceAPIException

    # Simulate -2018 (insufficient balance) on the MARKET order
    exc = BinanceAPIException(
        response=MagicMock(status_code=400),
        status_code=400,
        text='{"code": -2018, "msg": "Insufficient balance"}',
    )
    mock_binance_client.futures_create_order.side_effect = exc

    factory, session = make_session_factory(
        signal=mock_signal,
        risk=mock_risk_settings,
    )
    settings = make_settings()
    bot = AsyncMock()

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}), \
         patch("bot.order.executor._exchange_info_cache", {}), \
         patch("bot.order.executor.send_error_alert", new_callable=AsyncMock) as mock_alert:
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

        mock_alert.assert_called_once()
        call_kwargs = mock_alert.call_args
        # The message should contain the Russian error description for -2018
        msg_arg = call_kwargs[0][3] if len(call_kwargs[0]) >= 4 else call_kwargs[1].get("message", "")
        assert "баланс" in msg_arg.lower() or "balance" in msg_arg.lower() or \
               "Недостаточно" in msg_arg or "-2018" in msg_arg, \
               f"Expected error message not found: {msg_arg}"


async def test_double_tap_protection_is_none(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-05: When signal query returns None, no order is placed (already processing)."""
    factory, session = make_session_factory(signal=None)
    settings = make_settings()
    bot = AsyncMock()

    with patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    mock_binance_client.futures_create_order.assert_not_called()


# ---- RISK-08 / Gap 3b fix ----
@pytest.mark.asyncio
async def test_liquidation_safety_blocks_order(mock_binance_client, mock_signal, mock_risk_settings):
    """RISK-08: execute_order rejects the order when validate_liquidation_safety returns False."""
    from unittest.mock import AsyncMock, patch

    # Use high leverage — will cause liquidation safety failure with wide SL
    mock_risk_settings.leverage = 125
    mock_signal.stop_loss = 40000.0   # very wide SL — unsafe at 125x leverage
    mock_signal.entry_price = 50000.0

    factory, session = make_session_factory(
        signal=mock_signal,
        risk=mock_risk_settings,
    )
    settings = make_settings()
    bot = AsyncMock()

    with (
        patch("bot.telegram.handlers.commands._bot_state", {"dry_run": False, "paused": False}),
        patch("bot.order.executor._exchange_info_cache", {}),
        patch(
            "bot.order.executor.validate_liquidation_safety",
            return_value=(False, 48000.0),
        ),
        patch(
            "bot.order.executor.send_error_alert",
            new_callable=AsyncMock,
        ) as mock_alert,
    ):
        await execute_order(
            signal_id=mock_signal.id,
            session_factory=factory,
            binance_client=mock_binance_client,
            settings=settings,
            bot=bot,
        )

    # No MARKET order placed
    mock_binance_client.futures_create_order.assert_not_called()
    # Error alert sent
    mock_alert.assert_called()
