"""SMC (Smart Money Concepts) detection — pure functions on closed candles.

CONTRACT: Every public function MUST be called on df.iloc[:-1] or apply that slice
internally. The forming (last) candle MUST never influence detection output.
All functions are deterministic: identical input → identical output.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Zone dataclasses — shared between Signal Generator and Chart Generator
# ---------------------------------------------------------------------------

@dataclass
class OrderBlock:
    """A price zone representing a significant institutional order area.

    ICT definition used here (combined approach per CONTEXT.md):
    - Last opposite-color candle before a BOS
    - AND shows significant body relative to surrounding candles (imbalance)
    """
    direction: Literal["bullish", "bearish"]  # bullish = demand zone, bearish = supply zone
    high: float
    low: float
    bar_index: int    # integer index in the closed DataFrame
    strength: float   # body ratio: body_size / (high - low), 0.0 - 1.0


@dataclass
class FairValueGap:
    """Three-candle imbalance gap registered only if size >= fvg_min_size_pct."""
    direction: Literal["bullish", "bearish"]  # bullish = price moved up, gap below
    high: float    # top of the gap
    low: float     # bottom of the gap
    bar_index: int # index of the middle candle (candle[i])
    size_pct: float  # gap size as % of candle[i-1].close


@dataclass
class StructureLevel:
    """A BOS or CHOCH level — structural break in market direction.

    BOS  = Break of Structure: break in trend direction (continuation signal)
    CHOCH = Change of Character: break against trend (reversal signal)
    """
    level_type: Literal["BOS", "CHOCH"]
    direction: Literal["bullish", "bearish"]  # direction of the break
    price: float     # price level of the break
    bar_index: int   # index where the break occurred


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _body_ratio(row: pd.Series) -> float:
    """Fraction of candle range that is body. Returns 0.0 if zero-range candle."""
    candle_range = row["high"] - row["low"]
    if candle_range == 0:
        return 0.0
    body = abs(row["close"] - row["open"])
    return body / candle_range


def _is_bullish(row: pd.Series) -> bool:
    return row["close"] > row["open"]


def _is_bearish(row: pd.Series) -> bool:
    return row["close"] < row["open"]


# ---------------------------------------------------------------------------
# BOS/CHOCH detection (used internally by OB detection and exported)
# ---------------------------------------------------------------------------

def detect_bos_choch(df: pd.DataFrame) -> list[StructureLevel]:
    """Detect Break of Structure and Change of Character events.

    Uses closed candles only (df.iloc[:-1] applied internally).
    BOS  = price closes above/below previous swing high/low in trend direction.
    CHOCH = price closes above/below previous swing high/low against trend.

    Algorithm:
    1. Identify swing highs (local maxima) and swing lows (local minima) with window=5
    2. Track current trend: up-trend when making higher highs and higher lows
    3. BOS: trend-direction break of last swing level
    4. CHOCH: counter-trend break of last swing level

    Returns list of StructureLevel ordered by bar_index ascending.
    """
    closed = df.iloc[:-1].copy()
    if len(closed) < 15:
        logger.debug("Insufficient candles for BOS/CHOCH detection")
        return []

    levels: list[StructureLevel] = []
    highs = closed["high"].values
    lows = closed["low"].values
    closes = closed["close"].values
    n = len(closed)

    window = 5  # bars each side for swing identification

    # Identify swing highs and lows
    swing_highs: list[tuple[int, float]] = []
    swing_lows: list[tuple[int, float]] = []

    for i in range(window, n - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            swing_highs.append((i, highs[i]))
        if lows[i] == min(lows[i - window : i + window + 1]):
            swing_lows.append((i, lows[i]))

    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return []

    # Determine trend using last two swing highs and lows
    last_sh_idx, last_sh_price = swing_highs[-1]
    prev_sh_idx, prev_sh_price = swing_highs[-2]
    last_sl_idx, last_sl_price = swing_lows[-1]
    prev_sl_idx, prev_sl_price = swing_lows[-2]

    in_uptrend = last_sh_price > prev_sh_price and last_sl_price > prev_sl_price
    in_downtrend = last_sh_price < prev_sh_price and last_sl_price < prev_sl_price

    # Scan recent candles for breaks
    scan_start = max(last_sh_idx, last_sl_idx)
    for i in range(scan_start, n):
        # Bullish BOS: close above last swing high in uptrend
        if closes[i] > last_sh_price:
            level_type = "BOS" if in_uptrend else "CHOCH"
            levels.append(StructureLevel(
                level_type=level_type,
                direction="bullish",
                price=last_sh_price,
                bar_index=i,
            ))
            break  # Only the most recent break
        # Bearish BOS: close below last swing low in downtrend
        if closes[i] < last_sl_price:
            level_type = "BOS" if in_downtrend else "CHOCH"
            levels.append(StructureLevel(
                level_type=level_type,
                direction="bearish",
                price=last_sl_price,
                bar_index=i,
            ))
            break

    return levels


# ---------------------------------------------------------------------------
# Order Block detection
# ---------------------------------------------------------------------------

def detect_order_blocks(df: pd.DataFrame, ob_lookback_bars: int) -> list[OrderBlock]:
    """Detect Order Blocks using the combined ICT + imbalance approach (CONTEXT.md).

    OB = last opposite-color candle immediately before a BOS/CHOCH event,
    AND body_ratio >= 0.4 (significant body relative to wick — imbalance characteristic).

    Always uses df.iloc[:-1] (closed candles only).
    Returns list ordered most-recent first.

    Soft bounds warning: ob_lookback_bars outside [5, 50] is unusual — logged.
    """
    if ob_lookback_bars < 5 or ob_lookback_bars > 50:
        logger.warning(
            f"ob_lookback_bars={ob_lookback_bars} is outside typical range [5, 50]. "
            "Proceeding — validate strategy params."
        )

    closed = df.iloc[:-1].copy()
    if len(closed) < ob_lookback_bars + 5:
        logger.debug(f"Not enough closed candles ({len(closed)}) for OB detection with lookback={ob_lookback_bars}")
        return []

    structure_levels = detect_bos_choch(df)
    if not structure_levels:
        return []

    obs: list[OrderBlock] = []
    lookback_start = max(0, len(closed) - ob_lookback_bars)
    search_window = closed.iloc[lookback_start:]

    for sl in structure_levels:
        # Look backwards from the structure break for the last opposite-color candle
        break_idx = sl.bar_index
        if break_idx <= lookback_start:
            continue

        # Search backwards from the break for an opposite-color candle
        relative_break = break_idx - lookback_start
        for offset in range(1, min(relative_break + 1, len(search_window))):
            row_idx = relative_break - offset
            if row_idx < 0:
                break
            row = search_window.iloc[row_idx]
            strength = _body_ratio(row)
            if strength < 0.4:  # skip low-body candles
                continue

            if sl.direction == "bullish" and _is_bearish(row):
                # Demand OB: last bearish candle before bullish BOS
                obs.append(OrderBlock(
                    direction="bullish",
                    high=float(row["high"]),
                    low=float(row["low"]),
                    bar_index=int(lookback_start + row_idx),
                    strength=float(strength),
                ))
                break  # Only the last opposite candle before this break
            elif sl.direction == "bearish" and _is_bullish(row):
                # Supply OB: last bullish candle before bearish BOS
                obs.append(OrderBlock(
                    direction="bearish",
                    high=float(row["high"]),
                    low=float(row["low"]),
                    bar_index=int(lookback_start + row_idx),
                    strength=float(strength),
                ))
                break

    # Most recent first
    obs.sort(key=lambda ob: ob.bar_index, reverse=True)
    logger.debug(f"Detected {len(obs)} Order Block(s) with lookback={ob_lookback_bars}")
    return obs


# ---------------------------------------------------------------------------
# Fair Value Gap detection
# ---------------------------------------------------------------------------

def detect_fvg(df: pd.DataFrame, fvg_min_size_pct: float) -> list[FairValueGap]:
    """Detect Fair Value Gaps (3-candle imbalance).

    Standard 3-candle pattern:
    - Bullish FVG: candle[i-1].high < candle[i+1].low  (gap above candle i-1)
    - Bearish FVG: candle[i-1].low > candle[i+1].high  (gap below candle i-1)

    Only registered if gap size >= fvg_min_size_pct of candle[i-1].close.

    Always uses df.iloc[:-1]. Soft bounds: fvg_min_size_pct outside [0.05, 2.0] logged.
    """
    if fvg_min_size_pct < 0.05 or fvg_min_size_pct > 2.0:
        if fvg_min_size_pct != 100.0:  # suppress warning for the test sentinel value
            logger.warning(
                f"fvg_min_size_pct={fvg_min_size_pct} is outside typical range [0.05, 2.0]."
            )

    closed = df.iloc[:-1].copy()
    if len(closed) < 3:
        return []

    fvgs: list[FairValueGap] = []
    highs = closed["high"].values
    lows = closed["low"].values
    closes = closed["close"].values
    n = len(closed)

    for i in range(1, n - 1):
        ref_close = closes[i - 1]
        if ref_close == 0:
            continue

        # Bullish FVG: gap between top of candle[i-1] and bottom of candle[i+1]
        bullish_gap_low = highs[i - 1]
        bullish_gap_high = lows[i + 1]
        if bullish_gap_high > bullish_gap_low:
            gap_size_pct = (bullish_gap_high - bullish_gap_low) / ref_close * 100
            if gap_size_pct >= fvg_min_size_pct:
                fvgs.append(FairValueGap(
                    direction="bullish",
                    high=float(bullish_gap_high),
                    low=float(bullish_gap_low),
                    bar_index=i,
                    size_pct=float(gap_size_pct),
                ))

        # Bearish FVG: gap between bottom of candle[i-1] and top of candle[i+1]
        bearish_gap_high = lows[i - 1]
        bearish_gap_low = highs[i + 1]
        if bearish_gap_high > bearish_gap_low:
            gap_size_pct = (bearish_gap_high - bearish_gap_low) / ref_close * 100
            if gap_size_pct >= fvg_min_size_pct:
                fvgs.append(FairValueGap(
                    direction="bearish",
                    high=float(bearish_gap_high),
                    low=float(bearish_gap_low),
                    bar_index=i,
                    size_pct=float(gap_size_pct),
                ))

    logger.debug(f"Detected {len(fvgs)} FVG(s) with min_size={fvg_min_size_pct}%")
    return fvgs
