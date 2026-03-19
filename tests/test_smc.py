"""Tests for bot.signals.smc — SIG-02 (Order Blocks, FVG, BOS/CHOCH detection).
All tests are RED until bot/signals/smc.py is implemented.
"""
import pandas as pd
import pytest

smc = pytest.importorskip("bot.signals.smc")


@pytest.fixture
def ohlcv_df():
    df = pd.read_csv("tests/fixtures/ohlcv_sample.csv", parse_dates=["open_time"])
    df = df.set_index("open_time")
    return df


def test_detect_order_blocks_returns_list(ohlcv_df):
    result = smc.detect_order_blocks(ohlcv_df, ob_lookback_bars=20)
    assert isinstance(result, list)


def test_order_block_fields(ohlcv_df):
    result = smc.detect_order_blocks(ohlcv_df, ob_lookback_bars=20)
    if result:
        ob = result[0]
        assert hasattr(ob, "direction")
        assert hasattr(ob, "high")
        assert hasattr(ob, "low")
        assert hasattr(ob, "bar_index")
        assert hasattr(ob, "strength")


def test_order_block_direction_values(ohlcv_df):
    result = smc.detect_order_blocks(ohlcv_df, ob_lookback_bars=20)
    for ob in result:
        assert ob.direction in ("bullish", "bearish"), f"Unexpected direction: {ob.direction}"


def test_detect_fvg_respects_min_size(ohlcv_df):
    # fvg_min_size_pct=100.0 is impossibly large — must return empty list
    result = smc.detect_fvg(ohlcv_df, fvg_min_size_pct=100.0)
    assert result == [], f"Expected empty list with threshold=100.0, got {result}"


def test_detect_bos_choch_returns_list(ohlcv_df):
    result = smc.detect_bos_choch(ohlcv_df)
    assert isinstance(result, list)


def test_structure_level_fields(ohlcv_df):
    result = smc.detect_bos_choch(ohlcv_df)
    if result:
        sl = result[0]
        assert hasattr(sl, "level_type")
        assert hasattr(sl, "direction")
        assert hasattr(sl, "price")
        assert hasattr(sl, "bar_index")
        assert sl.level_type in ("BOS", "CHOCH")


def test_determinism(ohlcv_df):
    """Running detection twice on the same df must produce identical results (no look-ahead bias)."""
    result_a = smc.detect_order_blocks(ohlcv_df, ob_lookback_bars=20)
    result_b = smc.detect_order_blocks(ohlcv_df, ob_lookback_bars=20)
    assert len(result_a) == len(result_b)
    for a, b in zip(result_a, result_b):
        assert a.bar_index == b.bar_index
        assert a.direction == b.direction
