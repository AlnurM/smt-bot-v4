"""Tests for bot.risk.manager — RISK-01 through RISK-09.
All tests are RED until bot/risk/manager.py is implemented.
"""
import pytest

manager = pytest.importorskip("bot.risk.manager")


def test_position_size_formula():
    """Spec example: balance=100, stake=3%, entry=145, sl=140, leverage=5 → contracts ~3.0."""
    result = manager.calculate_position_size(
        balance=100.0,
        current_stake_pct=3.0,
        entry_price=145.0,
        stop_loss=140.0,
        leverage=5,
    )
    assert abs(result["risk_usdt"] - 3.0) < 0.01, f"risk_usdt={result['risk_usdt']}"
    assert abs(result["contracts"] - 3.0) < 0.15, f"contracts={result['contracts']}"


def test_position_size_risk_usdt():
    result = manager.calculate_position_size(100.0, 3.0, 145.0, 140.0, 5)
    assert result["risk_usdt"] == pytest.approx(3.0, abs=0.001)


def test_progressive_stakes_advance():
    """1 consecutive win from streak=0 → advance to progressive_stakes[1]."""
    stakes = [3.0, 5.0, 8.0]
    result = manager.get_next_stake(
        win_streak=1,
        progressive_stakes=stakes,
        base_stake_pct=3.0,
        wins_to_increase=1,
    )
    assert result == 5.0, f"Expected 5.0, got {result}"


def test_stake_reset_on_loss():
    """After any loss, stake resets to base_stake_pct."""
    result = manager.get_stake_after_loss(base_stake_pct=3.0)
    assert result == 3.0


def test_max_positions_enforced():
    """open_count == max_open → new signal NOT allowed."""
    result = manager.check_max_positions(open_count=5, max_open_positions=5)
    assert result is False, "Expected False (no new positions allowed)"


def test_daily_loss_circuit_breaker():
    """total_pnl=-5, starting_balance=100, limit=5% → halted."""
    result = manager.check_daily_loss(
        total_pnl=-5.0,
        starting_balance=100.0,
        daily_loss_limit_pct=5.0,
    )
    assert result is True, "Expected True (trading halted)"


def test_rr_filter():
    """rr_ratio=2.5 below min_rr=3.0 → filtered out (returns False)."""
    result = manager.check_rr_ratio(rr_ratio=2.5, min_rr_ratio=3.0)
    assert result is False


def test_min_notional_check():
    """position_usdt=3.0 below min_notional=5.0 → fails (returns False)."""
    result = manager.check_min_notional(position_usdt=3.0, min_notional=5.0)
    assert result is False


def test_liquidation_safety_pass():
    """entry=145, sl=140, leverage=5 → should be safe (liq well below sl)."""
    is_safe, liq_price = manager.validate_liquidation_safety(
        entry_price=145.0,
        stop_loss=140.0,
        leverage=5,
        liquidation_multiplier=2.0,
        maintenance_margin_rate=0.004,
    )
    assert is_safe is True, f"Expected safe, liq_price={liq_price:.2f}"


def test_liquidation_safety_fail():
    """entry=145, sl=143, leverage=20 → liquidation too close to entry."""
    is_safe, liq_price = manager.validate_liquidation_safety(
        entry_price=145.0,
        stop_loss=143.0,
        leverage=20,
        liquidation_multiplier=2.0,
        maintenance_margin_rate=0.004,
    )
    assert is_safe is False, f"Expected unsafe at 20x leverage with tight SL, liq_price={liq_price:.2f}"
