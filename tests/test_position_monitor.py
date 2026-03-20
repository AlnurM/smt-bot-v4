"""RED-state stubs for Phase 5 position monitor tests (Plans 05-02).

Each test function will fail with ImportError (via importorskip) until
bot.monitor.position is implemented in Plan 05-02.
"""
import pytest

pytest.importorskip("bot.monitor.position")


async def test_pnl_update(mock_binance_client):
    """MON-01: Unrealized PnL is updated on each monitor poll cycle.

    Verifies that futures_symbol_ticker is called for each open position
    and that position.unrealized_pnl is recalculated and persisted.
    """
    assert False, "Not implemented — RED stub"


async def test_close_notification(mock_binance_client):
    """MON-02: A Telegram close notification is sent when a position is closed.

    Verifies that when futures_get_order returns a FILLED status for an SL or
    TP order, a close notification is dispatched via Telegram with realized PnL.
    """
    assert False, "Not implemented — RED stub"


async def test_trade_record_created(mock_binance_client):
    """MON-03: A Trade record is created in the DB when a position closes.

    Verifies that a Trade row is inserted with position_id, realized_pnl,
    close_reason (sl or tp), and correct closed_at timestamp.
    """
    assert False, "Not implemented — RED stub"


async def test_win_streak_update(mock_binance_client):
    """MON-04: Win streak counter in RiskSettings is updated after a winning trade.

    Verifies that a profitable trade increments win_streak_current and that
    a losing trade resets it to 0 (if reset_on_loss=True).
    """
    assert False, "Not implemented — RED stub"


async def test_daily_stats_update(mock_binance_client):
    """MON-05: DailyStats row for today is upserted after each position close.

    Verifies that total_pnl, trade_count, win_count, and win_rate are
    correctly accumulated in the DailyStats record for the current date.
    """
    assert False, "Not implemented — RED stub"
