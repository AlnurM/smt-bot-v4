"""Market Scanner — coin ranking by volume growth rate, OHLCV fetch, scheduler job registration."""
from __future__ import annotations

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from binance import AsyncClient
from loguru import logger

# Minimum candles required for a valid backtest
MIN_HISTORY_CANDLES: int = 15_000


async def get_top_n_by_volume_growth(
    client: AsyncClient,
    whitelist: list[str],
    top_n: int,
    norm_hours: int = 4,
    min_growth_rate: float = 1.0,
) -> list[str]:
    """Return top-N symbols from whitelist ranked by volume growth rate.

    Volume growth rate = current_hour_volume / avg_hourly_volume_over_norm_hours.
    A rate of 2.0 means current volume is 2x the norm.

    Args:
        client: Binance AsyncClient
        whitelist: Approved coin symbols
        top_n: Max coins to return
        norm_hours: Hours to use as baseline (default 4, configurable via Telegram)
        min_growth_rate: Minimum growth rate to include (default 1.0 = no filter)

    Returns:
        List of symbols sorted by volume growth rate (highest first)
    """
    growth_rates: dict[str, float] = {}

    for symbol in whitelist:
        try:
            # Fetch recent klines to calculate volume growth
            klines = await client.futures_klines(
                symbol=symbol,
                interval=AsyncClient.KLINE_INTERVAL_1HOUR,
                limit=norm_hours + 1,  # +1 for current hour
            )
            if len(klines) < norm_hours + 1:
                continue

            volumes = [float(k[5]) for k in klines]  # index 5 = volume

            # Current hour volume (last candle, may be incomplete)
            current_vol = volumes[-1]
            # Average of previous norm_hours
            norm_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1.0

            if norm_vol > 0:
                growth_rate = current_vol / norm_vol
            else:
                growth_rate = 0.0

            growth_rates[symbol] = growth_rate

        except Exception as e:
            logger.debug(f"Failed to get volume for {symbol}: {e}")
            continue

    # Filter and sort
    filtered = {s: r for s, r in growth_rates.items() if r >= min_growth_rate}
    ranked = sorted(filtered.keys(), key=lambda s: filtered[s], reverse=True)
    result = ranked[:top_n]

    logger.info(
        f"Scanner ranked {len(whitelist)} whitelist coins by volume growth "
        f"(norm={norm_hours}h, min_rate={min_growth_rate:.1f}x) → {len(result)} pass: "
        f"{[(s, f'{growth_rates[s]:.2f}x') for s in result]}"
    )
    return result


async def fetch_ohlcv_15m(
    client: AsyncClient,
    symbol: str,
    months: int = 6,
) -> pd.DataFrame:
    """Fetch 15m OHLCV data from Binance USDT-M Futures for the given symbol.

    Returns DataFrame with columns [open_time, open, high, low, close, volume].
    Returns empty DataFrame if fewer than MIN_HISTORY_CANDLES candles available.
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
    """Register the market scan job with APScheduler using CronTrigger."""
    scheduler.add_job(
        job_fn,
        trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
        id="market_scanner",
        replace_existing=True,
    )
    logger.info(f"Market scanner job registered: cron hour={hour} minute={minute} UTC")
