"""Market Scanner — coin ranking, OHLCV fetch, scheduler job registration."""
from __future__ import annotations

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from binance import AsyncClient
from loguru import logger

# Minimum candles required for a valid 6-month 15m backtest (6 * 30 * 24 * 4 = 17,280; 15,000 is the floor)
MIN_HISTORY_CANDLES: int = 15_000


async def get_top_n_by_volume(
    client: AsyncClient,
    whitelist: list[str],
    top_n: int,
    min_volume_usdt: float = 0.0,
) -> list[str]:
    """Return top-N symbols from whitelist ranked by descending 24h quoteVolume.

    Excludes coins below min_volume_usdt threshold (SCAN-03).
    Only returns symbols that appear in the whitelist (SCAN-01).
    Length capped at top_n (SCAN-04).
    """
    tickers = await client.futures_ticker()
    volume_map: dict[str, float] = {
        t["symbol"]: float(t["quoteVolume"]) for t in tickers
    }

    ranked = sorted(
        [s for s in whitelist if s in volume_map],
        key=lambda s: volume_map[s],
        reverse=True,
    )
    filtered = [s for s in ranked if volume_map.get(s, 0.0) >= min_volume_usdt]
    result = filtered[:top_n]
    logger.info(
        f"Scanner ranked {len(whitelist)} whitelist coins → {len(result)} pass volume filter "
        f"(min_volume={min_volume_usdt:,.0f} USDT, top_n={top_n}): {result}"
    )
    return result


async def fetch_ohlcv_15m(
    client: AsyncClient,
    symbol: str,
    months: int = 6,
) -> pd.DataFrame:
    """Fetch 15m OHLCV data from Binance USDT-M Futures for the given symbol.

    Returns DataFrame with columns [open_time, open, high, low, close, volume].
    Returns empty DataFrame and logs warning if fewer than MIN_HISTORY_CANDLES candles
    are available (STRAT-03, Pitfall 5 in RESEARCH.md).
    """
    start_str = f"{months} months ago UTC"
    klines = await client.futures_historical_klines(
        symbol=symbol,
        interval=AsyncClient.KLINE_INTERVAL_15MINUTE,
        start_str=start_str,
    )
    df = pd.DataFrame(
        klines,
        columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ],
    )
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df = df[["open_time", "open", "high", "low", "close", "volume"]]

    if len(df) < MIN_HISTORY_CANDLES:
        logger.warning(
            f"Insufficient OHLCV history for {symbol}: got {len(df)} candles, "
            f"need >= {MIN_HISTORY_CANDLES}. Skipping symbol."
        )
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])
    else:
        logger.debug(f"Fetched {len(df)} 15m candles for {symbol}")
    return df


def register_scanner_job(
    scheduler: AsyncIOScheduler,
    job_fn,
    hour: str = "*",
    minute: str = "0",
) -> None:
    """Register the market scan job with APScheduler using CronTrigger.

    Fires at minute=minute of every hour=hour (default: every hour at :00).
    Per RESEARCH.md: use CronTrigger not IntervalTrigger to avoid drift (Pitfall 8).
    """
    scheduler.add_job(
        job_fn,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
        id="market_scanner",
        replace_existing=True,
    )
    logger.info(f"Market scanner job registered: cron hour={hour} minute={minute} UTC")
