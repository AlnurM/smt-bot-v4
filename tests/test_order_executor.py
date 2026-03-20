"""RED-state stubs for Phase 5 order executor tests (Plans 05-01 through 05-05).

Each test function will fail with ImportError (via importorskip) until
bot.order.executor is implemented in Plan 05-01.
"""
import pytest

pytest.importorskip("bot.order.executor")


async def test_market_order_placed(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-01: A confirmed signal triggers a MARKET order on Binance Futures.

    Verifies that futures_create_order is called with correct symbol, side,
    type=MARKET, and calculated quantity based on stake_pct and leverage.
    """
    assert False, "Not implemented — RED stub"


async def test_bracket_orders_placed(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-02: After the entry MARKET order fills, SL and TP bracket orders are placed.

    Verifies that futures_create_order is called twice more (STOP_MARKET and
    TAKE_PROFIT_MARKET), and that Position.sl_order_id and tp_order_id are persisted.
    """
    assert False, "Not implemented — RED stub"


async def test_confirmation_notification(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-03: A Telegram fill notification is sent after order execution.

    Verifies that the Telegram dispatcher receives the fill price, symbol,
    side, and order ID in the notification payload.
    """
    assert False, "Not implemented — RED stub"


async def test_error_handling(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-04: Binance API errors during order placement are caught and logged.

    Verifies that a BinanceAPIException does not propagate out of execute_order
    and that the signal status is set to 'failed'.
    """
    assert False, "Not implemented — RED stub"


async def test_double_tap_protection(mock_binance_client, mock_signal, mock_risk_settings):
    """ORD-05: Double-tap protection prevents duplicate orders for the same signal.

    Verifies that if an Order already exists for signal.id (due to
    uq_orders_signal_id constraint), execute_order returns early without
    calling futures_create_order again.
    """
    assert False, "Not implemented — RED stub"


async def test_dry_run_mode(mock_binance_client, mock_signal, mock_risk_settings):
    """Dry-run: In dry-run mode, no real Binance API calls are made.

    Verifies that futures_create_order is NOT called when is_dry_run=True,
    and that Position.is_dry_run is set to True in the persisted record.
    """
    assert False, "Not implemented — RED stub"
