import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

pytest.importorskip("bot.strategy.manager", reason="Wave 0: module not yet built")
from bot.strategy.manager import (
    get_coins_needing_strategy,
    save_strategy,
    log_skipped_coin,
    get_expired_active_strategies,
    deactivate_strategy,
)

# ---- STRAT-05 ----
@pytest.mark.asyncio
async def test_skip_if_active():
    """STRAT-05: get_coins_needing_strategy returns empty lists when all symbols have active, non-expired strategies."""
    mock_session = AsyncMock()
    # Simulate query results: all symbols are active
    mock_result_active = MagicMock()
    mock_result_active.scalars.return_value.all.return_value = ["BTCUSDT", "ETHUSDT"]
    mock_result_expired = MagicMock()
    mock_result_expired.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(side_effect=[mock_result_active, mock_result_expired])
    no_strategy, expired = await get_coins_needing_strategy(["BTCUSDT", "ETHUSDT"], mock_session)
    assert no_strategy == []
    assert expired == []


# ---- FILT-04 ----
@pytest.mark.asyncio
async def test_failed_strategy_logged():
    """FILT-04: log_skipped_coin inserts a SkippedCoin row with failed_criteria populated."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    from bot.strategy.filter import FilterResult
    result = FilterResult(passed=False, failed_criteria=["total_return_pct", "max_drawdown_pct"], details={})
    strategy_data = {"backtest": {"total_return_pct": 80.0, "max_drawdown_pct": -20.0}}
    await log_skipped_coin(mock_session, "XRPUSDT", strategy_data, result)
    mock_session.add.assert_called_once()
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.symbol == "XRPUSDT"
    assert "total_return_pct" in added_obj.failed_criteria
    mock_session.commit.assert_called_once()


# ---- FILT-05 ----
@pytest.mark.asyncio
async def test_criteria_snapshot_saved():
    """FILT-05: save_strategy stores criteria_snapshot as a non-null dict on the Strategy row."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    strategy_data = {
        "symbol": "BTCUSDT", "timeframe": "15m",
        "backtest": {"profit_factor": 2.1, "win_rate": 0.58, "total_return_pct": 215.0,
                     "max_drawdown_pct": -9.5, "total_trades": 45, "avg_rr": 2.3, "criteria_passed": True},
    }
    criteria_snapshot = {"min_total_return_pct": 200.0, "strict_mode": False}
    await save_strategy(mock_session, "BTCUSDT", strategy_data, criteria_snapshot, review_interval_days=30)
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.criteria_snapshot == criteria_snapshot
    assert added_obj.criteria_snapshot is not None


# ---- LIFE-01 ----
@pytest.mark.asyncio
async def test_strategy_fields_saved():
    """LIFE-01: save_strategy inserts a Strategy row with symbol, timeframe, strategy_data, backtest_score, is_active=True."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    strategy_data = {
        "symbol": "SOLUSDT", "timeframe": "15m",
        "backtest": {"profit_factor": 2.0, "win_rate": 0.60, "total_return_pct": 220.0,
                     "max_drawdown_pct": -10.0, "total_trades": 50, "avg_rr": 2.5, "criteria_passed": True},
    }
    await save_strategy(mock_session, "SOLUSDT", strategy_data, {}, review_interval_days=30)
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.symbol == "SOLUSDT"
    assert added_obj.timeframe == "15m"
    assert added_obj.is_active is True
    assert added_obj.strategy_data == strategy_data
    assert added_obj.backtest_score == pytest.approx(2.0 * 0.60)


# ---- LIFE-02 ----
@pytest.mark.asyncio
async def test_expiry_detection():
    """LIFE-02: get_expired_active_strategies returns strategies where next_review_at <= now()."""
    mock_session = AsyncMock()
    expired_strategy = MagicMock()
    expired_strategy.symbol = "BTCUSDT"
    expired_strategy.is_active = True
    expired_strategy.next_review_at = datetime.now(timezone.utc) - timedelta(days=1)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [expired_strategy]
    mock_session.execute = AsyncMock(return_value=mock_result)
    result = await get_expired_active_strategies(mock_session)
    assert len(result) == 1
    assert result[0].symbol == "BTCUSDT"


# ---- LIFE-03 ----
@pytest.mark.asyncio
async def test_old_strategy_deactivated():
    """LIFE-03: save_strategy issues an UPDATE to set is_active=False on existing active strategies before inserting new one."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    strategy_data = {
        "symbol": "BTCUSDT", "timeframe": "15m",
        "backtest": {"profit_factor": 2.1, "win_rate": 0.58, "total_return_pct": 215.0,
                     "max_drawdown_pct": -9.5, "total_trades": 45, "avg_rr": 2.3, "criteria_passed": True},
    }
    await save_strategy(mock_session, "BTCUSDT", strategy_data, {}, review_interval_days=30)
    # execute must have been called at least once (for the UPDATE deactivation query)
    assert mock_session.execute.called
    # New row must be added (not replacing old one — no delete)
    assert mock_session.add.called


# ---- LIFE-04 ----
@pytest.mark.asyncio
async def test_review_interval_stored():
    """LIFE-04: save_strategy stores review_interval_days on the Strategy row."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    strategy_data = {
        "symbol": "ETHUSDT", "timeframe": "15m",
        "backtest": {"profit_factor": 1.9, "win_rate": 0.57, "total_return_pct": 205.0,
                     "max_drawdown_pct": -11.0, "total_trades": 35, "avg_rr": 2.1, "criteria_passed": True},
    }
    await save_strategy(mock_session, "ETHUSDT", strategy_data, {}, review_interval_days=14)
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.review_interval_days == 14


# ---- LIFE-05 ----
@pytest.mark.asyncio
async def test_criteria_snapshot_stored():
    """LIFE-05: save_strategy stores a complete criteria_snapshot dict including strict_mode."""
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    strategy_data = {
        "symbol": "BNBUSDT", "timeframe": "15m",
        "backtest": {"profit_factor": 2.2, "win_rate": 0.62, "total_return_pct": 230.0,
                     "max_drawdown_pct": -8.0, "total_trades": 55, "avg_rr": 2.6, "criteria_passed": True},
    }
    snapshot = {
        "min_total_return_pct": 200.0, "max_drawdown_pct": -12.0,
        "min_win_rate_pct": 55.0, "min_profit_factor": 1.8,
        "min_trades": 30, "min_avg_rr": 2.0, "strict_mode": False,
    }
    await save_strategy(mock_session, "BNBUSDT", strategy_data, snapshot, review_interval_days=30)
    added_obj = mock_session.add.call_args[0][0]
    assert added_obj.criteria_snapshot["strict_mode"] is False
    assert added_obj.criteria_snapshot["min_total_return_pct"] == 200.0


# ---- SIG-01 / Gap 1 fix ----
@pytest.mark.asyncio
async def test_signal_row_created_in_db():
    """Gap 1 fix: run_strategy_scan inserts a Signal ORM row and flushes for UUID
    before calling send_signal_message. signal['id'] is set to the real row UUID."""
    from unittest.mock import AsyncMock, MagicMock, patch, call
    import uuid as _uuid
    from bot.strategy.manager import run_strategy_scan

    fake_signal_id = _uuid.uuid4()

    # Build a mock Signal row returned by flush
    mock_signal_row = MagicMock()
    mock_signal_row.id = fake_signal_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_factory = MagicMock(return_value=mock_session)

    mock_binance = AsyncMock()
    mock_binance.futures_account.return_value = {"totalWalletBalance": "1000.0"}

    mock_settings = MagicMock()
    mock_settings.coin_whitelist = ["BTCUSDT"]
    mock_settings.top_n_coins = 1
    mock_settings.min_volume_usdt = 0
    mock_settings.backtest_period_months = 6
    mock_settings.min_total_return_pct = 200.0
    mock_settings.max_drawdown_pct = -12.0
    mock_settings.min_win_rate_pct = 55.0
    mock_settings.min_profit_factor = 1.8
    mock_settings.min_trades = 30
    mock_settings.min_avg_rr = 2.0
    mock_settings.strict_mode = False
    mock_settings.allowed_chat_id = 123
    mock_settings.consecutive_empty_cycles_alert = 5
    mock_settings.signal_expiry_minutes = 15

    mock_bot = AsyncMock()
    mock_scheduler = MagicMock()

    fake_strategy_data = {
        "timeframe": "15m",
        "backtest": {"profit_factor": 2.0, "win_rate": 0.60},
    }
    fake_signal = {
        "symbol": "BTCUSDT",
        "direction": "long",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": 52000.0,
        "rr_ratio": 2.0,
        "timeframe": "15m",
        "signal_strength": "high",
        "reasoning": "test",
        "zones": {},
    }

    mock_risk = MagicMock()
    mock_risk.leverage = 5
    mock_risk.current_stake_pct = 3.0
    mock_risk.min_rr_ratio = 1.5

    # session.execute returns: risk query, then coins_needing_strategy queries
    mock_risk_result = MagicMock()
    mock_risk_result.scalars.return_value.first.return_value = mock_risk
    mock_active_result = MagicMock()
    mock_active_result.scalars.return_value.all.return_value = []
    mock_expired_result = MagicMock()
    mock_expired_result.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [
        mock_active_result, mock_expired_result,  # get_coins_needing_strategy
        mock_risk_result,                          # risk settings query
    ]

    with (
        patch("bot.scanner.market_scanner.get_top_n_by_volume", new=AsyncMock(return_value=["BTCUSDT"])),
        patch("bot.scanner.market_scanner.fetch_ohlcv_15m", new=AsyncMock(return_value=MagicMock(empty=False))),
        patch("bot.strategy.claude_engine.generate_strategy", new=AsyncMock(return_value=fake_strategy_data)),
        patch("bot.strategy.filter.filter_strategy", return_value=MagicMock(passed=True)),
        patch("bot.strategy.manager.save_strategy", new=AsyncMock()),
        patch("bot.signals.generator.generate_signal", new=AsyncMock(return_value=fake_signal)),
        patch("bot.charts.generator.generate_chart", new=AsyncMock(return_value=b"PNG")),
        patch("bot.risk.manager.calculate_position_size", return_value={
            "risk_usdt": 30.0, "sl_distance": 0.02, "position_usdt": 1500.0, "contracts": 0.1
        }),
        patch("bot.db.models.Signal", return_value=mock_signal_row) as mock_signal_cls,
        patch("bot.telegram.dispatch.send_signal_message", new=AsyncMock(return_value=42)),
        patch("bot.telegram.dispatch.schedule_signal_expiry"),
    ):
        await run_strategy_scan(
            mock_session_factory, mock_binance, mock_settings,
            bot=mock_bot, scheduler=mock_scheduler
        )

    # Signal row was added to session
    mock_session.add.assert_called()
    # flush was called to get UUID
    mock_session.flush.assert_called()
    # signal["id"] was set to the row's UUID string
    assert fake_signal.get("id") == str(fake_signal_id)


# ---- RISK-03 ----
@pytest.mark.asyncio
async def test_rr_filter_blocks_low_ratio():
    """RISK-03: signals with rr_ratio below min_rr_ratio are not dispatched and no Signal row is created."""
    from unittest.mock import AsyncMock, MagicMock, patch
    from bot.strategy.manager import run_strategy_scan

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory = MagicMock(return_value=mock_session)

    mock_settings = MagicMock()
    mock_settings.coin_whitelist = ["BTCUSDT"]
    mock_settings.top_n_coins = 1
    mock_settings.min_volume_usdt = 0
    mock_settings.backtest_period_months = 6
    mock_settings.min_total_return_pct = 200.0
    mock_settings.max_drawdown_pct = -12.0
    mock_settings.min_win_rate_pct = 55.0
    mock_settings.min_profit_factor = 1.8
    mock_settings.min_trades = 30
    mock_settings.min_avg_rr = 2.0
    mock_settings.strict_mode = False
    mock_settings.allowed_chat_id = 123
    mock_settings.consecutive_empty_cycles_alert = 5

    low_rr_signal = {
        "symbol": "BTCUSDT", "direction": "long",
        "entry_price": 50000.0, "stop_loss": 49000.0, "take_profit": 50500.0,
        "rr_ratio": 1.0,  # below min_rr_ratio=1.5
        "timeframe": "15m",
    }

    mock_risk = MagicMock()
    mock_risk.leverage = 5
    mock_risk.current_stake_pct = 3.0
    mock_risk.min_rr_ratio = 1.5

    mock_risk_result = MagicMock()
    mock_risk_result.scalars.return_value.first.return_value = mock_risk
    mock_active_result = MagicMock()
    mock_active_result.scalars.return_value.all.return_value = []
    mock_expired_result = MagicMock()
    mock_expired_result.scalars.return_value.all.return_value = []
    mock_session.execute.side_effect = [
        mock_active_result, mock_expired_result, mock_risk_result,
    ]

    mock_binance = AsyncMock()
    mock_binance.futures_account.return_value = {"totalWalletBalance": "1000.0"}

    with (
        patch("bot.scanner.market_scanner.get_top_n_by_volume", new=AsyncMock(return_value=["BTCUSDT"])),
        patch("bot.scanner.market_scanner.fetch_ohlcv_15m", new=AsyncMock(return_value=MagicMock(empty=False))),
        patch("bot.strategy.claude_engine.generate_strategy", new=AsyncMock(return_value={"timeframe": "15m", "backtest": {"profit_factor": 2.0, "win_rate": 0.6}})),
        patch("bot.strategy.filter.filter_strategy", return_value=MagicMock(passed=True)),
        patch("bot.strategy.manager.save_strategy", new=AsyncMock()),
        patch("bot.signals.generator.generate_signal", new=AsyncMock(return_value=low_rr_signal)),
        patch("bot.charts.generator.generate_chart", new=AsyncMock(return_value=b"PNG")),
        patch("bot.risk.manager.calculate_position_size", return_value={
            "risk_usdt": 30.0, "sl_distance": 0.02, "position_usdt": 1500.0, "contracts": 0.1
        }),
        patch("bot.telegram.dispatch.send_signal_message") as mock_dispatch,
    ):
        await run_strategy_scan(
            mock_session_factory, mock_binance, mock_settings,
            bot=AsyncMock(), scheduler=MagicMock()
        )

    # send_signal_message must NOT have been called
    mock_dispatch.assert_not_called()
    # No Signal ORM row added
    mock_session.add.assert_not_called()
