"""Tests for bot.charts.generator — CHART-01, CHART-02, CHART-05, CHART-09.
All tests are RED until bot/charts/generator.py is implemented.
"""
import asyncio
import os
import pandas as pd
import pytest

chart_gen = pytest.importorskip("bot.charts.generator")


@pytest.fixture
def ohlcv_df():
    df = pd.read_csv("tests/fixtures/ohlcv_sample.csv", parse_dates=["open_time"])
    df = df.set_index("open_time")
    return df


@pytest.fixture
def minimal_signal():
    return {
        "symbol": "SOLUSDT",
        "timeframe": "15m",
        "direction": "long",
        "entry_price": 145.0,
        "stop_loss": 140.0,
        "take_profit": 160.0,
        "rr_ratio": 3.0,
        "signal_strength": "Strong",
    }


@pytest.fixture
def minimal_zones():
    return {
        "order_blocks": [],
        "fvgs": [],
        "structure_levels": [],
    }


def test_chart_returns_png(ohlcv_df, minimal_signal, minimal_zones):
    """generate_chart returns bytes starting with PNG magic header — CHART-01, CHART-09."""
    result = asyncio.run(chart_gen.generate_chart(ohlcv_df, minimal_signal, minimal_zones))
    assert isinstance(result, bytes), "Expected bytes"
    assert result[:4] == b'\x89PNG', f"Expected PNG magic bytes, got {result[:4]!r}"


def test_chart_with_ob_zones(ohlcv_df, minimal_signal):
    """Chart renders without error when order_blocks contains valid zones — CHART-02."""
    zones = {
        "order_blocks": [{"direction": "bullish", "high": 146.0, "low": 144.0, "bar_index": 10, "strength": 0.8}],
        "fvgs": [],
        "structure_levels": [],
    }
    result = asyncio.run(chart_gen.generate_chart(ohlcv_df, minimal_signal, zones))
    assert result[:4] == b'\x89PNG'


def test_chart_entry_sl_tp(ohlcv_df, minimal_signal, minimal_zones):
    """Chart renders when signal has entry_price, stop_loss, take_profit — CHART-05."""
    result = asyncio.run(chart_gen.generate_chart(ohlcv_df, minimal_signal, minimal_zones))
    assert len(result) > 1000, "PNG output suspiciously small"


def test_chart_bytesio_no_disk(ohlcv_df, minimal_signal, minimal_zones, tmp_path):
    """No chart file created on disk after generate_chart — CHART-09."""
    before = set(os.listdir("."))
    asyncio.run(chart_gen.generate_chart(ohlcv_df, minimal_signal, minimal_zones))
    after = set(os.listdir("."))
    new_files = after - before
    png_files = [f for f in new_files if f.endswith(".png")]
    assert not png_files, f"Unexpected PNG files created: {png_files}"
