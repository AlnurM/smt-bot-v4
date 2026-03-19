"""Tests for bot.signals.indicators — SIG-03 (MACD crossover, RSI signals).
All tests are RED until bot/signals/indicators.py is implemented.
"""
import pandas as pd
import pytest

indicators = pytest.importorskip("bot.signals.indicators")


@pytest.fixture
def ohlcv_df():
    df = pd.read_csv("tests/fixtures/ohlcv_sample.csv", parse_dates=["open_time"])
    df = df.set_index("open_time")
    return df


def test_compute_macd_columns(ohlcv_df):
    result = indicators.compute_macd(ohlcv_df, fast=12, slow=26, signal=9)
    assert "MACD_12_26_9" in result.columns, f"Missing MACD_12_26_9. Got: {list(result.columns)}"
    assert "MACDH_12_26_9" in result.columns
    assert "MACDS_12_26_9" in result.columns


def test_compute_rsi_series(ohlcv_df):
    result = indicators.compute_rsi(ohlcv_df, period=14)
    assert hasattr(result, "name"), "Expected a named pandas Series"
    assert result.name == "RSI_14", f"Expected name 'RSI_14', got '{result.name}'"


def test_macd_crossover_returns_bool(ohlcv_df):
    macd_df = indicators.compute_macd(ohlcv_df, fast=12, slow=26, signal=9)
    result = indicators.detect_macd_crossover(macd_df, fast=12, slow=26, signal=9)
    assert isinstance(result, bool)


def test_rsi_signal_returns_bool(ohlcv_df):
    rsi = indicators.compute_rsi(ohlcv_df, period=14)
    result = indicators.detect_rsi_signal(rsi, oversold=30, overbought=70, direction="long")
    assert isinstance(result, bool)
