"""Signal Generator — orchestrates SMC + indicator analysis to produce trade signals.

Entry point: generate_signal(client, symbol, strategy_data, ohlcv_df) -> dict | None

Pure helpers (score_to_strength, check_volume, check_entry_conditions,
build_empty_signal_result) are exported for unit testing.
"""
from __future__ import annotations

from typing import Any

import pandas as pd
from loguru import logger

from bot.signals.indicators import (
    compute_macd,
    compute_rsi,
    detect_macd_crossover,
    detect_rsi_signal,
)
from bot.signals.smc import (
    detect_bos_choch,
    detect_fvg,
    detect_order_blocks,
)


# ---------------------------------------------------------------------------
# Scoring weights — per CONTEXT.md (Claude's Discretion)
# ---------------------------------------------------------------------------

CONDITION_WEIGHTS: dict[str, int] = {
    "htf_bos_confirm": 3,    # HTF 4h BOS/CHOCH alignment
    "ob_demand": 2,           # price in bullish OB zone
    "ob_supply": 2,           # price in bearish OB zone
    "macd_cross_up": 2,
    "macd_cross_down": 2,
    "rsi_oversold_exit": 1,
    "rsi_overbought_exit": 1,
    "bos_bullish": 1,
    "bos_bearish": 1,
    "volume_confirm": 1,
}

STRENGTH_STRONG: int = 7
STRENGTH_MODERATE: int = 4


def score_to_strength(score: int) -> str:
    """Map total condition score to strength label.

    Strong   >= 7  (HTF confirmed, OB + MACD + extra)
    Moderate >= 4  (core conditions met)
    Weak     <  4  (minimal conditions)
    """
    if score >= STRENGTH_STRONG:
        return "Strong"
    if score >= STRENGTH_MODERATE:
        return "Moderate"
    return "Weak"


def check_volume(current_volume: float, volume_avg: float, multiplier: float) -> bool:
    """Return True if current_volume >= volume_avg * multiplier."""
    if volume_avg == 0:
        return False
    return current_volume >= volume_avg * multiplier


def check_entry_conditions(conditions_met: list[str]) -> int:
    """Sum weights of all conditions in conditions_met list.

    Returns 0 if conditions_met is empty.
    Unknown condition keys have weight 0 (no KeyError).
    """
    return sum(CONDITION_WEIGHTS.get(cond, 0) for cond in conditions_met)


def build_empty_signal_result() -> dict[str, Any]:
    """Return a template signal dict with all required keys set to None.

    Used by tests to verify key presence. Populated by generate_signal().
    """
    return {
        "symbol": None,
        "timeframe": None,
        "direction": None,
        "entry_price": None,
        "stop_loss": None,
        "take_profit": None,
        "rr_ratio": None,
        "signal_strength": None,
        "reasoning": None,
        "zones": {},  # {order_blocks, fvgs, structure_levels} for Chart Generator
    }


# ---------------------------------------------------------------------------
# Internal: determine entry price, SL, TP from detected zones
# ---------------------------------------------------------------------------

def _calculate_entry_sl_tp(
    direction: str,
    current_price: float,
    order_blocks: list,
    structure_levels: list,
    tp_rr_ratio: float,
    sl_method: str,
) -> tuple[float, float, float]:
    """Derive entry, SL, and TP prices from detected zones.

    SL methods:
    - 'ob_boundary': SL at the opposite edge of the triggering OB (low for bullish, high for bearish)
    - 'atr': Not implemented in Phase 3; falls back to 1% of current_price

    Returns (entry_price, stop_loss, take_profit).
    Entry = current_price (market entry).
    """
    entry = current_price

    if sl_method == "ob_boundary" and order_blocks:
        # Use the nearest OB that price is currently inside
        nearest_ob = order_blocks[0]  # sorted most-recent first
        if direction == "long":
            # SL below the demand OB low, 0.1% buffer
            stop_loss = nearest_ob.low * 0.999
        else:
            # SL above the supply OB high, 0.1% buffer
            stop_loss = nearest_ob.high * 1.001
    else:
        # Fallback: 1% of entry price
        if direction == "long":
            stop_loss = entry * 0.99
        else:
            stop_loss = entry * 1.01

    sl_distance = abs(entry - stop_loss)
    if direction == "long":
        take_profit = entry + (sl_distance * tp_rr_ratio)
    else:
        take_profit = entry - (sl_distance * tp_rr_ratio)

    return entry, stop_loss, take_profit


def _check_price_in_ob(current_price: float, order_blocks: list, direction: str) -> bool:
    """Return True if current_price is within any OB of the given direction."""
    for ob in order_blocks:
        if ob.direction == direction and ob.low <= current_price <= ob.high:
            return True
    return False


def _fetch_4h_df(klines: list) -> pd.DataFrame:
    """Convert raw klines list to OHLCV DataFrame with datetime index."""
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
    df = df.set_index("open_time")
    return df


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_signal(
    client: Any,
    symbol: str,
    strategy_data: dict,
    ohlcv_df: pd.DataFrame,
) -> dict | None:
    """Generate a trade signal for symbol using the active strategy.

    Returns a signal dict (all Signal ORM fields + zones for chart) or None if:
    - No entry conditions are satisfied
    - Insufficient OHLCV data
    - No qualifying OB zone found

    The 'zones' key in the returned dict is consumed by Chart Generator.
    Risk validation happens AFTER this function (in Risk Manager).

    Steps:
    1. Run SMC detection on 15m data (closed candles only)
    2. Compute MACD and RSI indicators
    3. Fetch 4h OHLCV and run BOS/CHOCH for HTF confirmation
    4. For each direction (long, short), check which entry conditions are met
    5. Score conditions and pick the highest-scoring direction if >= 1 point
    6. Calculate entry/SL/TP from zones
    7. Return populated signal dict
    """
    from binance import AsyncClient, HistoricalKlinesType  # noqa: PLC0415 — lazy import

    smc_params = strategy_data.get("smc", {})
    ind_params = strategy_data.get("indicators", {})
    exit_params = strategy_data.get("exit", {})
    entry_params = strategy_data.get("entry", {})

    ob_lookback = smc_params.get("ob_lookback_bars", 20)
    fvg_min_size = smc_params.get("fvg_min_size_pct", 0.2)
    tp_rr_ratio = exit_params.get("tp_rr_ratio", 3.0)
    sl_method = exit_params.get("sl_method", "ob_boundary")

    macd_params = ind_params.get("macd", {"fast": 12, "slow": 26, "signal": 9})
    rsi_params = ind_params.get("rsi", {"period": 14, "oversold": 30, "overbought": 70})

    if ohlcv_df.empty or len(ohlcv_df) < 50:
        logger.warning(
            f"{symbol}: Insufficient OHLCV data for signal generation ({len(ohlcv_df)} rows)"
        )
        return None

    # Ensure datetime index
    df = ohlcv_df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if "open_time" in df.columns:
            df = df.set_index("open_time")

    # Step 1: SMC detection on 15m
    order_blocks = detect_order_blocks(df, ob_lookback_bars=ob_lookback)
    fvgs = detect_fvg(df, fvg_min_size_pct=fvg_min_size)
    structure_levels = detect_bos_choch(df)

    # Step 2: Indicators on 15m
    macd_df = compute_macd(
        df, fast=macd_params["fast"], slow=macd_params["slow"], signal=macd_params["signal"]
    )
    rsi_series = compute_rsi(df, period=rsi_params["period"])

    # Step 3: 4h HTF BOS/CHOCH confirmation
    htf_levels: list = []
    try:
        htf_klines = await client.futures_historical_klines(
            symbol=symbol,
            interval=AsyncClient.KLINE_INTERVAL_4HOUR,
            start_str="3 months ago UTC",
            klines_type=HistoricalKlinesType.FUTURES,
        )
        if htf_klines:
            htf_df = _fetch_4h_df(htf_klines)
            htf_levels = detect_bos_choch(htf_df)
    except Exception as e:
        logger.warning(
            f"{symbol}: 4h HTF fetch failed, proceeding without HTF confirmation: {e}"
        )

    htf_bullish = any(sl.direction == "bullish" for sl in htf_levels)
    htf_bearish = any(sl.direction == "bearish" for sl in htf_levels)

    # Step 4: Current price (last closed candle)
    current_price = float(df["close"].iloc[-2])  # iloc[-2] = last closed candle

    # Volume confirmation
    vol_window = 20
    volume_avg = float(df["volume"].iloc[:-1].rolling(vol_window).mean().iloc[-1])
    current_volume = float(df["volume"].iloc[-2])
    volume_multiplier = strategy_data.get("volume_multiplier", 1.2)
    volume_ok = check_volume(current_volume, volume_avg, multiplier=volume_multiplier)

    # Step 5: Score both directions
    def score_direction(direction: str) -> tuple[int, list[str]]:
        conditions_required = entry_params.get("long" if direction == "long" else "short", [])
        met: list[str] = []

        # HTF confirmation
        if direction == "long" and htf_bullish:
            met.append("htf_bos_confirm")
        elif direction == "short" and htf_bearish:
            met.append("htf_bos_confirm")

        # OB zone check
        if "ob_demand" in conditions_required and _check_price_in_ob(
            current_price, order_blocks, "bullish"
        ):
            met.append("ob_demand")
        if "ob_supply" in conditions_required and _check_price_in_ob(
            current_price, order_blocks, "bearish"
        ):
            met.append("ob_supply")

        # MACD
        if "macd_cross_up" in conditions_required and not macd_df.empty:
            if detect_macd_crossover(
                macd_df,
                macd_params["fast"],
                macd_params["slow"],
                macd_params["signal"],
                "long",
            ):
                met.append("macd_cross_up")
        if "macd_cross_down" in conditions_required and not macd_df.empty:
            if detect_macd_crossover(
                macd_df,
                macd_params["fast"],
                macd_params["slow"],
                macd_params["signal"],
                "short",
            ):
                met.append("macd_cross_down")

        # RSI
        if "rsi_oversold_exit" in conditions_required and not rsi_series.empty:
            if detect_rsi_signal(
                rsi_series, rsi_params["oversold"], rsi_params["overbought"], "long"
            ):
                met.append("rsi_oversold_exit")
        if "rsi_overbought_exit" in conditions_required and not rsi_series.empty:
            if detect_rsi_signal(
                rsi_series, rsi_params["oversold"], rsi_params["overbought"], "short"
            ):
                met.append("rsi_overbought_exit")

        # BOS on 15m
        if "bos_bullish" in conditions_required and any(
            sl.direction == "bullish" for sl in structure_levels
        ):
            met.append("bos_bullish")
        if "bos_bearish" in conditions_required and any(
            sl.direction == "bearish" for sl in structure_levels
        ):
            met.append("bos_bearish")

        # Volume
        if "volume_confirm" in conditions_required and volume_ok:
            met.append("volume_confirm")

        return check_entry_conditions(met), met

    long_score, long_conditions = score_direction("long")
    short_score, short_conditions = score_direction("short")

    # Select best direction or return None
    if long_score == 0 and short_score == 0:
        logger.debug(
            f"{symbol}: No entry conditions met (long_score=0, short_score=0)"
        )
        return None

    if long_score >= short_score:
        direction = "long"
        score = long_score
        conditions_met = long_conditions
    else:
        direction = "short"
        score = short_score
        conditions_met = short_conditions

    # Step 6: Entry/SL/TP
    entry, sl, tp = _calculate_entry_sl_tp(
        direction=direction,
        current_price=current_price,
        order_blocks=order_blocks,
        structure_levels=structure_levels,
        tp_rr_ratio=tp_rr_ratio,
        sl_method=sl_method,
    )

    sl_dist = abs(entry - sl)
    if sl_dist == 0:
        logger.warning(f"{symbol}: SL distance is zero, skipping signal")
        return None
    rr = abs(tp - entry) / sl_dist

    strength = score_to_strength(score)
    reasoning = f"Conditions met: {', '.join(conditions_met)} (score={score})"

    logger.info(
        f"{symbol}: Signal generated — direction={direction}, strength={strength}, "
        f"score={score}, R/R={rr:.2f}"
    )

    # Step 7: Return signal dict
    return {
        "symbol": symbol,
        "timeframe": strategy_data.get("timeframe", "15m"),
        "direction": direction,
        "entry_price": round(entry, 6),
        "stop_loss": round(sl, 6),
        "take_profit": round(tp, 6),
        "rr_ratio": round(rr, 2),
        "signal_strength": strength,
        "reasoning": reasoning,
        "zones": {
            "order_blocks": order_blocks,
            "fvgs": fvgs,
            "structure_levels": structure_levels,
        },
    }
