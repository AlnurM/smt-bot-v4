import pytest

pytest.importorskip("bot.strategy.filter", reason="Wave 0: module not yet built")
from bot.strategy.filter import filter_strategy, FilterResult


def _make_strategy(total_return=250.0, drawdown=-8.0, win_rate=0.60, pf=2.0, trades=40, avg_rr=2.5):
    return {"backtest": {
        "total_return_pct": total_return, "max_drawdown_pct": drawdown,
        "win_rate": win_rate, "profit_factor": pf, "total_trades": trades, "avg_rr": avg_rr,
    }}


def test_all_criteria_checked(sample_criteria):
    """FILT-01: In strict_mode, all 6 criteria fields are checked."""
    criteria = {**sample_criteria, "strict_mode": True}
    # Strategy fails only avg_rr
    strategy = _make_strategy(avg_rr=1.0)
    result = filter_strategy(strategy, criteria, strict_mode=True)
    assert result.passed is False
    assert "avg_rr" in result.failed_criteria
    # Strategy passes all
    strategy_good = _make_strategy()
    result_good = filter_strategy(strategy_good, criteria, strict_mode=True)
    assert result_good.passed is True
    assert result_good.failed_criteria == []


def test_default_criteria(sample_criteria):
    """FILT-02: Default criteria values match spec (return >=200, drawdown <=-12, winrate >=55, PF >=1.8, trades >=30, rr >=2.0)."""
    # Exactly at threshold values — should pass
    strategy = _make_strategy(total_return=200.0, drawdown=-12.0, win_rate=0.55, pf=1.8, trades=30, avg_rr=2.0)
    result = filter_strategy(strategy, sample_criteria, strict_mode=False)
    assert result.passed is True
    # Just under total_return threshold — relaxed mode fails
    strategy_fail = _make_strategy(total_return=199.9, drawdown=-8.0)
    result_fail = filter_strategy(strategy_fail, sample_criteria, strict_mode=False)
    assert result_fail.passed is False


def test_relaxed_mode(sample_criteria):
    """FILT-03: In relaxed mode, only total_return_pct and max_drawdown_pct are required to pass."""
    criteria = {**sample_criteria, "strict_mode": False}
    # Win rate, PF, trades, avg_rr all below threshold — but return and drawdown pass
    strategy = _make_strategy(total_return=210.0, drawdown=-11.0, win_rate=0.40, pf=1.0, trades=5, avg_rr=0.5)
    result = filter_strategy(strategy, criteria, strict_mode=False)
    assert result.passed is True
    # Return fails — whole strategy fails even in relaxed mode
    strategy_bad = _make_strategy(total_return=100.0, drawdown=-11.0)
    result_bad = filter_strategy(strategy_bad, criteria, strict_mode=False)
    assert result_bad.passed is False
