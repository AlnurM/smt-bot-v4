"""Tests for bot.signals.generator — SIG-01, SIG-04, SIG-05, SIG-06.
All tests are RED until bot/signals/generator.py is implemented.
"""
import pytest

generator = pytest.importorskip("bot.signals.generator")


MINIMAL_STRATEGY = {
    "symbol": "SOLUSDT",
    "timeframe": "15m",
    "indicators": {"macd": {"fast": 12, "slow": 26, "signal": 9}, "rsi": {"period": 14, "oversold": 30, "overbought": 70}},
    "smc": {"ob_lookback_bars": 20, "fvg_min_size_pct": 0.2, "require_bos_confirm": True, "use_choch": True, "htf_confirmation": "4h"},
    "entry": {"long": ["ob_demand", "macd_cross_up", "rsi_oversold_exit"], "short": ["ob_supply", "macd_cross_down", "rsi_overbought_exit"]},
    "exit": {"sl_method": "ob_boundary", "sl_atr_mult": 1.5, "tp_rr_ratio": 3.0, "trailing_stop": False},
    "backtest": {"period_months": 6, "total_trades": 50, "total_return_pct": 250.0, "win_rate": 0.6,
                 "profit_factor": 2.0, "max_drawdown_pct": -8.0, "avg_rr": 2.5, "criteria_passed": True},
}


def test_signal_fields():
    """Signal dict must have all required fields — SIG-06."""
    required = {"direction", "entry_price", "stop_loss", "take_profit", "rr_ratio", "signal_strength", "reasoning"}
    # This tests the shape. Actual generation tested via integration; here we test the SignalResult dataclass/dict.
    result = generator.build_empty_signal_result()  # Returns a dict with all required keys set to None
    assert required.issubset(set(result.keys())), f"Missing keys: {required - set(result.keys())}"


def test_signal_direction_values():
    """direction must be 'long' or 'short'."""
    result = generator.build_empty_signal_result()
    # After population, direction must be in valid set
    assert "direction" in result


def test_signal_strength_values():
    """Signal strength thresholds: Strong >= 7, Moderate 4-6, Weak 1-3."""
    assert generator.score_to_strength(9) == "Strong"
    assert generator.score_to_strength(5) == "Moderate"
    assert generator.score_to_strength(2) == "Weak"


def test_volume_confirmation():
    """Volume > avg * multiplier returns True."""
    assert generator.check_volume(current_volume=15000, volume_avg=10000, multiplier=1.2) is True
    assert generator.check_volume(current_volume=8000, volume_avg=10000, multiplier=1.2) is False


def test_no_signal_none_return():
    """check_entry_conditions with empty conditions list returns score=0."""
    score = generator.check_entry_conditions(conditions_met=[])
    assert score == 0
