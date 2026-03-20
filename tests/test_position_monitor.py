"""Tests for Phase 5 position monitor (Plans 05-02).

Tests cover MON-01 through MON-05:
  - MON-01: Unrealized PnL update via futures_position_information
  - MON-02: Close notification sent via Telegram on SL/TP fill
  - MON-03: Trade record created with correct fields on close
  - MON-04: Win streak updated on TP (increment) and SL (reset to 0)
  - MON-05: DailyStats upserted atomically on any position close
"""
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

pytest.importorskip("bot.monitor.position")

from bot.monitor.position import monitor_positions, _handle_position_close, _update_unrealized_pnl


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_position(
    sl_order_id="1002",
    tp_order_id="1003",
    is_dry_run=False,
    status="open",
    side="long",
    entry_price=145.0,
    quantity=1.0,
    symbol="BTCUSDT",
):
    """Create a SimpleNamespace position for use in tests."""
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        quantity=quantity,
        unrealized_pnl=None,
        status=status,
        sl_order_id=sl_order_id,
        tp_order_id=tp_order_id,
        is_dry_run=is_dry_run,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_price=None,
        environment="testnet",
    )


def make_risk_settings(win_streak_current=0):
    return types.SimpleNamespace(
        win_streak_current=win_streak_current,
        base_stake_pct=3.0,
        current_stake_pct=3.0,
        progressive_stakes=[3.0, 5.0, 8.0],
        wins_to_increase=1,
        reset_on_loss=True,
        daily_loss_limit_pct=5.0,
        updated_at=datetime.now(timezone.utc),
    )


def make_daily_stats():
    return types.SimpleNamespace(
        date=datetime.now(timezone.utc).date(),
        total_pnl=0.0,
        trade_count=0,
        win_count=0,
        win_rate=None,
        starting_balance=None,
    )


def make_session_factory(position=None, risk=None, daily_stats=None):
    """Return an async context-manager session factory mock.

    Supports session.get(), session.execute(), session.add(), session.commit().
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    # session.get(Position, id) -> position object
    if position is not None:
        session.get = AsyncMock(return_value=position)
    else:
        session.get = AsyncMock(return_value=None)

    # Build execute results based on what's in the session
    results_map = {}
    if risk is not None:
        risk_result = MagicMock()
        risk_result.scalar_one_or_none.return_value = risk
        risk_result.scalar_one.return_value = risk
        results_map["risk"] = risk_result

    if daily_stats is not None:
        stats_result = MagicMock()
        stats_result.scalar_one_or_none.return_value = daily_stats
        results_map["stats"] = stats_result

    async def mock_execute(stmt):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalar_one.return_value = None
        result.scalars.return_value.all.return_value = []

        # Check what type of statement this is (duck-typing by string repr)
        stmt_str = str(stmt)
        if "risk_settings" in stmt_str and risk is not None:
            result.scalar_one_or_none.return_value = risk
            result.scalar_one.return_value = risk
        elif "daily_stats" in stmt_str and daily_stats is not None:
            result.scalar_one_or_none.return_value = daily_stats
            result.scalar_one.return_value = daily_stats
        elif "positions" in stmt_str and position is not None:
            result.scalars.return_value.all.return_value = [position]

        return result

    session.execute = mock_execute

    # Context-manager support
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    # Expose session directly for assertions
    factory._session = session
    return factory


def make_settings():
    return types.SimpleNamespace(
        allowed_chat_id=123456789,
        binance_env="testnet",
    )


# ---------------------------------------------------------------------------
# MON-01: Unrealized PnL update
# ---------------------------------------------------------------------------

async def test_pnl_update(mock_binance_client):
    """MON-01: When neither SL nor TP is FILLED, unrealized_pnl is updated from
    futures_position_information() and the DB record is committed with the new value.
    """
    position = make_position()
    bot = AsyncMock()
    settings = make_settings()

    # Both bracket orders are still open (not filled)
    mock_binance_client.futures_get_order.return_value = {
        "orderId": 1002,
        "status": "NEW",
        "avgPrice": "0.00",
        "type": "STOP_MARKET",
    }
    # Unrealized PnL data from Binance
    mock_binance_client.futures_position_information.return_value = [
        {
            "symbol": "BTCUSDT",
            "unRealizedProfit": "25.50",
            "positionAmt": "1.0",
            "markPrice": "170.50",
        }
    ]

    # Session factory where get() returns the position so we can update it
    session_factory = make_session_factory(position=position)

    await monitor_positions(session_factory, mock_binance_client, settings, bot)

    # futures_position_information should have been called (for unrealized PnL update)
    mock_binance_client.futures_position_information.assert_called()

    # The session commit should have been called (to persist the updated PnL)
    session = session_factory._session
    session.commit.assert_called()


# ---------------------------------------------------------------------------
# MON-02: Close notification
# ---------------------------------------------------------------------------

async def test_close_notification(mock_binance_client):
    """MON-02: When sl_order status == 'FILLED', bot.send_message is called once
    with a message containing 'Stop Loss' and the exit price.
    """
    position = make_position()
    bot = AsyncMock()
    settings = make_settings()
    risk = make_risk_settings()
    daily_stats = make_daily_stats()

    # SL order is FILLED, TP order is still NEW
    sl_filled = {
        "orderId": 1002,
        "status": "FILLED",
        "avgPrice": "140.00",
        "type": "STOP_MARKET",
    }
    tp_new = {
        "orderId": 1003,
        "status": "NEW",
        "avgPrice": "0.00",
        "type": "TAKE_PROFIT_MARKET",
    }
    # First call: SL order (FILLED), second call: TP order (NEW)
    mock_binance_client.futures_get_order.side_effect = [sl_filled, tp_new]

    # Account trades for realized PnL
    mock_binance_client.futures_account_trades.return_value = [
        {"orderId": 1002, "realizedPnl": "-5.00", "symbol": "BTCUSDT"},
    ]
    mock_binance_client.futures_cancel_order.return_value = {"status": "CANCELED"}

    # Session factory with risk and daily stats available
    session_factory = make_session_factory(position=position, risk=risk, daily_stats=daily_stats)

    await monitor_positions(session_factory, mock_binance_client, settings, bot)

    # Telegram should have been called with a close notification
    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    message_text = call_args[0][1] if call_args[0] else call_args[1].get("text", "")
    assert "Stop Loss" in message_text, f"Expected 'Stop Loss' in message, got: {message_text!r}"
    assert "140.0000" in message_text or "140.00" in message_text, f"Expected exit price in message: {message_text!r}"


# ---------------------------------------------------------------------------
# MON-03: Trade record created
# ---------------------------------------------------------------------------

async def test_trade_record_created(mock_binance_client):
    """MON-03: When tp_order status == 'FILLED', a Trade row is created with
    close_reason='tp', correct exit_price, and realized_pnl from futures_account_trades().
    """
    position = make_position()
    bot = AsyncMock()
    settings = make_settings()
    risk = make_risk_settings()
    daily_stats = make_daily_stats()

    # TP order is FILLED, SL order is still NEW
    sl_new = {
        "orderId": 1002,
        "status": "NEW",
        "avgPrice": "0.00",
        "type": "STOP_MARKET",
    }
    tp_filled = {
        "orderId": 1003,
        "status": "FILLED",
        "avgPrice": "160.00",
        "type": "TAKE_PROFIT_MARKET",
    }
    # First call: SL (NEW), second call: TP (FILLED)
    mock_binance_client.futures_get_order.side_effect = [sl_new, tp_filled]

    # Realized PnL from account trades for the TP order
    mock_binance_client.futures_account_trades.return_value = [
        {"orderId": 1003, "realizedPnl": "15.00", "symbol": "BTCUSDT"},
        {"orderId": 9999, "realizedPnl": "99.00", "symbol": "BTCUSDT"},  # other order, ignored
    ]
    mock_binance_client.futures_cancel_order.return_value = {"status": "CANCELED"}

    added_objects = []
    session_factory = make_session_factory(position=position, risk=risk, daily_stats=daily_stats)

    # Patch session.add to capture what was added
    original_add = session_factory._session.add
    def capture_add(obj):
        added_objects.append(obj)
    session_factory._session.add = capture_add

    await monitor_positions(session_factory, mock_binance_client, settings, bot)

    # A Trade object should have been added
    from bot.db.models import Trade
    trade_objects = [o for o in added_objects if isinstance(o, Trade)]
    assert len(trade_objects) == 1, f"Expected 1 Trade added, got {len(trade_objects)}. Added: {added_objects}"
    trade = trade_objects[0]
    assert trade.close_reason == "tp", f"Expected close_reason='tp', got {trade.close_reason!r}"
    assert trade.exit_price == 160.0, f"Expected exit_price=160.0, got {trade.exit_price}"
    assert trade.realized_pnl == 15.0, f"Expected realized_pnl=15.0, got {trade.realized_pnl}"


# ---------------------------------------------------------------------------
# MON-04: Win streak update
# ---------------------------------------------------------------------------

async def test_win_streak_update(mock_binance_client):
    """MON-04: On TP hit, win_streak_current increments by 1 and stake is updated.
    On SL hit, win_streak_current resets to 0 and stake resets to base.
    """
    # --- TP case: win streak increments ---
    position_tp = make_position()
    bot = AsyncMock()
    settings = make_settings()
    risk_tp = make_risk_settings(win_streak_current=0)
    daily_stats = make_daily_stats()

    sl_new = {"orderId": 1002, "status": "NEW", "avgPrice": "0.00", "type": "STOP_MARKET"}
    tp_filled = {"orderId": 1003, "status": "FILLED", "avgPrice": "160.00", "type": "TAKE_PROFIT_MARKET"}

    mock_binance_client.futures_get_order.side_effect = [sl_new, tp_filled]
    mock_binance_client.futures_account_trades.return_value = [
        {"orderId": 1003, "realizedPnl": "15.00", "symbol": "BTCUSDT"},
    ]
    mock_binance_client.futures_cancel_order.return_value = {"status": "CANCELED"}

    session_factory = make_session_factory(position=position_tp, risk=risk_tp, daily_stats=daily_stats)

    await monitor_positions(session_factory, mock_binance_client, settings, bot)

    # After TP: win_streak_current should be incremented
    assert risk_tp.win_streak_current == 1, (
        f"Expected win_streak_current=1 after TP, got {risk_tp.win_streak_current}"
    )
    # current_stake_pct should have been updated (get_next_stake with streak=1 on [3,5,8], wins_to_increase=1 -> 5.0)
    assert risk_tp.current_stake_pct == 5.0, (
        f"Expected current_stake_pct=5.0 after win streak=1, got {risk_tp.current_stake_pct}"
    )

    # --- SL case: win streak resets ---
    position_sl = make_position()
    risk_sl = make_risk_settings(win_streak_current=3)
    daily_stats_sl = make_daily_stats()
    bot_sl = AsyncMock()

    sl_filled = {"orderId": 1002, "status": "FILLED", "avgPrice": "140.00", "type": "STOP_MARKET"}
    tp_new = {"orderId": 1003, "status": "NEW", "avgPrice": "0.00", "type": "TAKE_PROFIT_MARKET"}

    mock_binance_client.futures_get_order.side_effect = [sl_filled, tp_new]
    mock_binance_client.futures_account_trades.return_value = [
        {"orderId": 1002, "realizedPnl": "-5.00", "symbol": "BTCUSDT"},
    ]

    session_factory_sl = make_session_factory(position=position_sl, risk=risk_sl, daily_stats=daily_stats_sl)

    await monitor_positions(session_factory_sl, mock_binance_client, settings, bot_sl)

    # After SL: win_streak_current should reset to 0
    assert risk_sl.win_streak_current == 0, (
        f"Expected win_streak_current=0 after SL, got {risk_sl.win_streak_current}"
    )
    # current_stake_pct should be base_stake_pct
    assert risk_sl.current_stake_pct == 3.0, (
        f"Expected current_stake_pct=3.0 (base) after SL, got {risk_sl.current_stake_pct}"
    )


# ---------------------------------------------------------------------------
# MON-05: DailyStats upsert
# ---------------------------------------------------------------------------

async def test_daily_stats_update(mock_binance_client):
    """MON-05: On any close, DailyStats for today is upserted with pg_insert ON CONFLICT DO UPDATE.

    Verify that session.execute is called with a statement that targets the daily_stats table.
    """
    position = make_position()
    bot = AsyncMock()
    settings = make_settings()
    risk = make_risk_settings()
    daily_stats = make_daily_stats()

    # TP fill triggers a close
    sl_new = {"orderId": 1002, "status": "NEW", "avgPrice": "0.00", "type": "STOP_MARKET"}
    tp_filled = {"orderId": 1003, "status": "FILLED", "avgPrice": "160.00", "type": "TAKE_PROFIT_MARKET"}

    mock_binance_client.futures_get_order.side_effect = [sl_new, tp_filled]
    mock_binance_client.futures_account_trades.return_value = [
        {"orderId": 1003, "realizedPnl": "15.00", "symbol": "BTCUSDT"},
    ]
    mock_binance_client.futures_cancel_order.return_value = {"status": "CANCELED"}

    # Track all execute calls
    executed_statements = []
    session_factory = make_session_factory(position=position, risk=risk, daily_stats=daily_stats)
    original_execute = session_factory._session.execute

    async def capturing_execute(stmt):
        executed_statements.append(stmt)
        return await original_execute(stmt)

    session_factory._session.execute = capturing_execute

    await monitor_positions(session_factory, mock_binance_client, settings, bot)

    # At least one execute call should have happened
    assert len(executed_statements) > 0, "No execute calls were made to the session"

    # At least one should target the daily_stats table (ON CONFLICT DO UPDATE)
    stmt_strings = [str(s) for s in executed_statements]
    has_daily_stats = any("daily_stats" in s for s in stmt_strings)
    assert has_daily_stats, (
        f"Expected a statement targeting 'daily_stats', "
        f"got statements targeting: {stmt_strings}"
    )


# ---- RISK-04 / Gap 2 fix ----
@pytest.mark.asyncio
async def test_starting_balance_set_on_daily_stats():
    """Gap 2: _handle_position_close fetches balance from binance_client.futures_account."""
    from unittest.mock import AsyncMock, MagicMock

    position = make_position(symbol="BTCUSDT", side="long", entry_price=50000.0)
    settings = make_settings()
    bot = AsyncMock()
    risk = make_risk_settings()
    daily_stats = make_daily_stats()
    daily_stats.total_pnl = -5.0
    daily_stats.trade_count = 1
    daily_stats.starting_balance = 1000.0

    mock_binance = AsyncMock()
    mock_binance.futures_account.return_value = {"totalWalletBalance": "1000.00"}
    mock_binance.futures_account_trades.return_value = [
        {"orderId": 9001, "realizedPnl": "-5.00"}
    ]
    mock_binance.futures_cancel_order = AsyncMock()

    session_factory = make_session_factory(
        position=position, risk=risk, daily_stats=daily_stats
    )

    await _handle_position_close(
        mock_binance,
        session_factory,
        bot,
        settings,
        position,
        close_reason="sl",
        filled_order_id="9001",
        surviving_order_id="9002",
        exit_price=49000.0,
    )

    # Binance balance was fetched
    mock_binance.futures_account.assert_called()


# ---- TG-20 / Gap 2 fix ----
@pytest.mark.asyncio
async def test_80pct_warning_called_after_close():
    """TG-20: check_and_warn_daily_loss is called after DailyStats upsert in _handle_position_close."""
    from unittest.mock import AsyncMock, patch

    position = make_position(symbol="ETHUSDT", side="long", entry_price=3000.0)
    settings = make_settings()
    bot = AsyncMock()
    risk = make_risk_settings()
    daily_stats = make_daily_stats()
    # Simulate a losing day at 80% of limit
    daily_stats.total_pnl = -4.0
    daily_stats.trade_count = 1
    daily_stats.starting_balance = 1000.0

    mock_binance = AsyncMock()
    mock_binance.futures_account.return_value = {"totalWalletBalance": "1000.00"}
    mock_binance.futures_account_trades.return_value = [
        {"orderId": 8001, "realizedPnl": "-4.00"}
    ]
    mock_binance.futures_cancel_order = AsyncMock()

    session_factory = make_session_factory(
        position=position, risk=risk, daily_stats=daily_stats
    )

    with patch(
        "bot.telegram.notifications.check_and_warn_daily_loss",
        new=AsyncMock(),
    ) as mock_warn:
        await _handle_position_close(
            mock_binance,
            session_factory,
            bot,
            settings,
            position,
            close_reason="sl",
            filled_order_id="8001",
            surviving_order_id="8002",
            exit_price=2900.0,
        )

    mock_warn.assert_called_once()
