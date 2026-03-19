import pytest
from unittest.mock import AsyncMock, patch

# These imports will fail until 02-01-PLAN creates the module — RED state is correct
pytest.importorskip("bot.scanner.market_scanner", reason="Wave 0: module not yet built")
from bot.scanner.market_scanner import get_top_n_by_volume, fetch_ohlcv_15m, register_scanner_job


@pytest.mark.asyncio
async def test_top_n_by_volume():
    """SCAN-01: Scanner returns symbols from whitelist ranked by descending quoteVolume."""
    mock_client = AsyncMock()
    mock_client.futures_ticker.return_value = [
        {"symbol": "BTCUSDT", "quoteVolume": "3000000000"},
        {"symbol": "ETHUSDT", "quoteVolume": "1500000000"},
        {"symbol": "SOLUSDT", "quoteVolume": "500000000"},
        {"symbol": "DOGEUSDT", "quoteVolume": "100000000"},
    ]
    result = await get_top_n_by_volume(mock_client, whitelist=["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT"], top_n=3, min_volume_usdt=0)
    assert result == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


@pytest.mark.asyncio
async def test_scheduler_job_registered():
    """SCAN-02: register_scanner_job adds a job to the scheduler."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    register_scanner_job(scheduler, job_fn=AsyncMock(), hour="*", minute="0")
    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    assert jobs[0].trigger is not None


@pytest.mark.asyncio
async def test_volume_filter():
    """SCAN-03: Coins below min_volume_usdt are excluded from results."""
    mock_client = AsyncMock()
    mock_client.futures_ticker.return_value = [
        {"symbol": "BTCUSDT", "quoteVolume": "3000000000"},
        {"symbol": "ETHUSDT", "quoteVolume": "10000"},  # below threshold
    ]
    result = await get_top_n_by_volume(mock_client, whitelist=["BTCUSDT", "ETHUSDT"], top_n=10, min_volume_usdt=50_000_000)
    assert result == ["BTCUSDT"]


@pytest.mark.asyncio
async def test_top_n_configurable():
    """SCAN-04: top_n parameter limits the number of returned symbols."""
    mock_client = AsyncMock()
    mock_client.futures_ticker.return_value = [
        {"symbol": f"COIN{i}USDT", "quoteVolume": str(1_000_000_000 - i * 1000)} for i in range(20)
    ]
    whitelist = [f"COIN{i}USDT" for i in range(20)]
    result = await get_top_n_by_volume(mock_client, whitelist=whitelist, top_n=5, min_volume_usdt=0)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_ohlcv_fetch_format():
    """STRAT-03: fetch_ohlcv_15m returns DataFrame with columns [open_time, open, high, low, close, volume]."""
    import pandas as pd
    mock_client = AsyncMock()
    # Return 10 fake klines in python-binance format (12-element lists)
    fake_klines = [[1700000000000 + i*900000, "100", "105", "95", "102", "1000",
                    1700000900000 + i*900000, "102000", "500", "500", "51000", "0"] for i in range(10)]
    mock_client.futures_historical_klines.return_value = fake_klines
    df = await fetch_ohlcv_15m(mock_client, symbol="BTCUSDT", months=6)
    assert list(df.columns) == ["open_time", "open", "high", "low", "close", "volume"]
    assert df.dtypes["open"] == float
    assert df.dtypes["close"] == float
    assert len(df) == 10
