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
