"""MACD and RSI indicator computation using pandas-ta-classic.

CONTRACT: compute_* functions accept the full DataFrame (including forming candle).
detect_* functions use df.iloc[:-1] for crossover detection — forming candle excluded.

Do NOT hand-roll MACD or RSI math. Use df.ta.macd() and df.ta.rsi() exclusively.
pandas-ta-classic handles EMA warm-up periods and Wilder smoothing correctly.
"""
from __future__ import annotations

import pandas as pd
from loguru import logger


def compute_macd(df: pd.DataFrame, fast: int, slow: int, signal: int) -> pd.DataFrame:
    """Compute MACD using pandas-ta-classic df.ta.macd().

    Returns standalone DataFrame (does not mutate input df) with columns:
      MACD_{fast}_{slow}_{signal}   — MACD line
      MACDH_{fast}_{slow}_{signal}  — histogram (MACD - signal)
      MACDS_{fast}_{slow}_{signal}  — signal line

    Requires at least slow+signal rows of data for meaningful values.
    Rows before warm-up period contain NaN — this is expected.
    """
    import pandas_ta_classic as ta  # noqa: PLC0415 — lazy import to fail fast if missing

    macd_df = df.ta.macd(fast=fast, slow=slow, signal=signal)
    if macd_df is None or macd_df.empty:
        logger.warning(f"pandas-ta MACD returned None/empty for fast={fast} slow={slow} signal={signal}")
        return pd.DataFrame()
    # pandas-ta-classic returns lowercase histogram/signal suffixes (MACDh_*, MACDs_*).
    # Normalise to uppercase to match the canonical column names in the plan contract.
    macd_df.columns = [col.upper() for col in macd_df.columns]
    logger.debug(f"Computed MACD({fast},{slow},{signal}): {len(macd_df)} rows, {list(macd_df.columns)}")
    return macd_df


def compute_rsi(df: pd.DataFrame, period: int) -> pd.Series:
    """Compute RSI using pandas-ta-classic df.ta.rsi().

    Returns Series named RSI_{period}.
    First `period` rows contain NaN — this is expected (Wilder smoothing warm-up).
    """
    import pandas_ta_classic as ta  # noqa: PLC0415

    rsi = df.ta.rsi(length=period)
    if rsi is None or rsi.empty:
        logger.warning(f"pandas-ta RSI returned None/empty for period={period}")
        return pd.Series(name=f"RSI_{period}", dtype=float)
    logger.debug(f"Computed RSI({period}): {len(rsi)} rows, name={rsi.name}")
    return rsi


def detect_macd_crossover(
    macd_df: pd.DataFrame,
    fast: int,
    slow: int,
    signal: int,
    direction: str = "long",
) -> bool:
    """Detect if MACD line crossed the signal line on the last CLOSED candle.

    Uses macd_df.iloc[:-1] — the forming candle is excluded from crossover detection.

    direction='long'  -> True if MACD crossed ABOVE signal line (bullish cross)
    direction='short' -> True if MACD crossed BELOW signal line (bearish cross)

    Returns False if insufficient data (< 3 closed rows after warm-up).
    """
    macd_col = f"MACD_{fast}_{slow}_{signal}"
    sig_col = f"MACDS_{fast}_{slow}_{signal}"

    if macd_col not in macd_df.columns or sig_col not in macd_df.columns:
        logger.warning(f"MACD columns not found: expected {macd_col}, {sig_col}")
        return False

    closed = macd_df.iloc[:-1].dropna(subset=[macd_col, sig_col])
    if len(closed) < 2:
        return False

    prev_macd = closed[macd_col].iloc[-2]
    prev_sig = closed[sig_col].iloc[-2]
    curr_macd = closed[macd_col].iloc[-1]
    curr_sig = closed[sig_col].iloc[-1]

    if direction == "long":
        # Bullish crossover: MACD was below signal, now above
        return bool((prev_macd <= prev_sig) and (curr_macd > curr_sig))
    else:
        # Bearish crossover: MACD was above signal, now below
        return bool((prev_macd >= prev_sig) and (curr_macd < curr_sig))


def detect_rsi_signal(
    rsi_series: pd.Series,
    oversold: float,
    overbought: float,
    direction: str,
) -> bool:
    """Detect RSI entry confirmation on the last CLOSED candle.

    Uses rsi_series.iloc[:-1] — the forming candle is excluded.

    direction='long' : True if RSI was below oversold and has risen above it
                       (exit from oversold — bullish momentum confirmation)
    direction='short': True if RSI was above overbought and has dropped below it
                       (exit from overbought — bearish momentum confirmation)

    Returns False if fewer than 2 non-NaN closed RSI values.
    """
    closed = rsi_series.iloc[:-1].dropna()
    if len(closed) < 2:
        return False

    prev_rsi = closed.iloc[-2]
    curr_rsi = closed.iloc[-1]

    if direction == "long":
        return bool((prev_rsi <= oversold) and (curr_rsi > oversold))
    else:
        return bool((prev_rsi >= overbought) and (curr_rsi < overbought))
