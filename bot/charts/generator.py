"""Chart Generator — mplfinance PNG with SMC overlays for Telegram signal messages.

API:
    generate_chart(df, signal, zones) -> bytes   (async — offloads to thread)

CRITICAL implementation notes:
1. matplotlib.use('Agg') MUST be called before mplfinance import (Docker headless).
2. plt.close(fig) MUST be called after fig.savefig() to prevent memory leak.
3. asyncio.to_thread() offloads CPU-bound _render_chart() to the thread pool.
4. axes indexing with volume=False, two addplot panels:
   axes[0]=main, axes[2]=MACD(panel=1), axes[4]=RSI(panel=2)
5. x-coordinates for Rectangle patches are INTEGER bar indices (0-based in sliced df).
"""
from __future__ import annotations

import asyncio
import time
from io import BytesIO
from typing import Any

import matplotlib
matplotlib.use('Agg')   # Must be first matplotlib call — headless Docker compatible

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
from loguru import logger
from matplotlib.patches import Rectangle

from bot.signals.indicators import compute_macd, compute_rsi


# ---------------------------------------------------------------------------
# Zone attribute accessor — handles both dataclasses and plain dicts
# ---------------------------------------------------------------------------

def _get(obj: Any, key: str, default=None):
    """Access obj.key (dataclass) or obj[key] (dict) uniformly."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ---------------------------------------------------------------------------
# Dynamic candle range computation
# ---------------------------------------------------------------------------

def _compute_candle_range(df: pd.DataFrame, zones: dict) -> tuple[pd.DataFrame, int]:
    """Determine which candles to include so all OB/FVG zones are visible.

    Minimum 60 candles. If oldest zone bar_index extends further back, include
    enough candles to show it. Maximum = all available closed candles (df.iloc[:-1]).
    """
    closed = df.iloc[:-1]
    n = len(closed)
    min_candles = 60

    # Find the oldest bar index among all zones
    oldest_bar = n  # default: show all
    for zone_list in (
        zones.get("order_blocks", []),
        zones.get("fvgs", []),
        zones.get("structure_levels", []),
    ):
        for z in zone_list:
            idx = _get(z, "bar_index", n)
            if idx < oldest_bar:
                oldest_bar = idx

    # Include from oldest zone bar (with 10-bar margin) to most recent
    start = max(0, min(oldest_bar - 10, n - min_candles))
    sliced = closed.iloc[start:]
    return sliced, start  # return start offset for bar_index translation


# ---------------------------------------------------------------------------
# Sync rendering function (CPU-bound — run via asyncio.to_thread)
# ---------------------------------------------------------------------------

def _render_chart(df: pd.DataFrame, signal: dict, zones: dict) -> bytes:
    """Synchronous chart rendering. Must NOT be called directly in async context.

    Always run via: await asyncio.to_thread(_render_chart, df, signal, zones)
    """
    t_start = time.time()

    chart_df, bar_offset = _compute_candle_range(df, zones)

    if chart_df.empty or len(chart_df) < 5:
        logger.warning("Chart DataFrame too short — returning empty PNG placeholder")
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.text(0.5, 0.5, "Insufficient data", transform=ax.transAxes, ha='center')
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=200)
        buf.seek(0)
        plt.close(fig)
        return buf.read()

    # Ensure chart_df has DatetimeIndex (mplfinance requirement)
    if not isinstance(chart_df.index, pd.DatetimeIndex):
        if "open_time" in chart_df.columns:
            chart_df = chart_df.set_index("open_time")

    # Ensure OHLCV columns are float
    chart_df = chart_df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in chart_df.columns:
            chart_df[col] = chart_df[col].astype(float)

    n_bars = len(chart_df)
    symbol = signal.get("symbol", "")
    timeframe = signal.get("timeframe", "15m")
    direction = signal.get("direction", "long")
    rr_ratio = signal.get("rr_ratio", 0.0)

    # Compute MACD and RSI
    macd_params_fast, macd_params_slow, macd_params_sig = 12, 26, 9
    macd_df = compute_macd(chart_df, macd_params_fast, macd_params_slow, macd_params_sig)
    rsi_series = compute_rsi(chart_df, period=14)

    macd_col = f"MACD_{macd_params_fast}_{macd_params_slow}_{macd_params_sig}"
    hist_col = f"MACDH_{macd_params_fast}_{macd_params_slow}_{macd_params_sig}"
    sig_col = f"MACDS_{macd_params_fast}_{macd_params_slow}_{macd_params_sig}"

    addplots = []

    if not macd_df.empty and macd_col in macd_df.columns:
        macd_line_vals = macd_df[macd_col].fillna(0)
        macd_sig_vals = macd_df[sig_col].fillna(0)
        macd_hist_vals = macd_df[hist_col].fillna(0)
        hist_colors = ['green' if v >= 0 else 'red' for v in macd_hist_vals]

        addplots += [
            mpf.make_addplot(macd_line_vals, panel=1, color='blue', width=1.0),
            mpf.make_addplot(macd_sig_vals, panel=1, color='orange', width=0.8),
            mpf.make_addplot(macd_hist_vals, panel=1, type='bar', color=hist_colors, alpha=0.7),
        ]

    if rsi_series is not None and not rsi_series.empty:
        rsi_vals = rsi_series.fillna(50)
        addplots.append(
            mpf.make_addplot(rsi_vals, panel=2, color='purple', width=1.0, ylim=(0, 100))
        )

    # mplfinance plot
    chart_title = f"{symbol} {timeframe} | {direction.upper()} | R/R {rr_ratio:.2f}"
    panel_ratios = (3, 1, 1) if addplots else (1,)
    fig, axes = mpf.plot(
        chart_df,
        type='candle',
        style='charles',
        addplot=addplots if addplots else [],
        panel_ratios=panel_ratios,
        returnfig=True,
        figsize=(12, 8),
        volume=False,
        title=chart_title,
    )

    ax_main = axes[0]

    # Identify MACD and RSI axes (only if addplots were added)
    ax_macd = axes[2] if len(axes) > 2 else None
    ax_rsi = axes[4] if len(axes) > 4 else None

    # OB rectangles
    for ob in zones.get("order_blocks", []):
        ob_dir = _get(ob, "direction")
        ob_high = _get(ob, "high")
        ob_low = _get(ob, "low")
        ob_bar = _get(ob, "bar_index")
        if None in (ob_dir, ob_high, ob_low, ob_bar):
            continue
        # Translate global bar_index to chart-relative index
        chart_bar = int(ob_bar) - bar_offset
        if chart_bar < 0:
            chart_bar = 0
        width = n_bars - chart_bar
        color = 'green' if ob_dir == 'bullish' else 'red'
        rect = Rectangle(
            (chart_bar - 0.5, float(ob_low)), width, float(ob_high) - float(ob_low),
            facecolor=color, alpha=0.15, edgecolor=color, linewidth=1,
        )
        ax_main.add_patch(rect)

    # FVG rectangles (transparent with dashed border)
    for fvg in zones.get("fvgs", []):
        fvg_dir = _get(fvg, "direction")
        fvg_high = _get(fvg, "high")
        fvg_low = _get(fvg, "low")
        fvg_bar = _get(fvg, "bar_index")
        if None in (fvg_dir, fvg_high, fvg_low, fvg_bar):
            continue
        chart_bar = max(0, int(fvg_bar) - bar_offset)
        width = n_bars - chart_bar
        color = 'green' if fvg_dir == 'bullish' else 'red'
        rect = Rectangle(
            (chart_bar - 0.5, float(fvg_low)), width, float(fvg_high) - float(fvg_low),
            facecolor=color, alpha=0.05, edgecolor=color, linewidth=1, linestyle='--',
        )
        ax_main.add_patch(rect)

    # BOS/CHOCH horizontal lines
    for sl in zones.get("structure_levels", []):
        sl_type = _get(sl, "level_type", "BOS")
        sl_price = _get(sl, "price")
        if sl_price is None:
            continue
        linestyle = '-' if sl_type == 'BOS' else '--'
        ax_main.axhline(
            float(sl_price), linestyle=linestyle, color='gray', linewidth=0.8, alpha=0.7
        )
        ax_main.text(
            0.01, float(sl_price), sl_type,
            transform=ax_main.get_yaxis_transform(),
            fontsize=7, color='gray', va='bottom',
        )

    # Entry / SL / TP lines
    entry_price = signal.get("entry_price")
    stop_loss = signal.get("stop_loss")
    take_profit = signal.get("take_profit")

    if entry_price is not None:
        ax_main.axhline(float(entry_price), linestyle='--', color='royalblue', linewidth=1.2, label='Entry')
    if stop_loss is not None:
        ax_main.axhline(float(stop_loss), linestyle='-', color='red', linewidth=1.5, label='SL')
    if take_profit is not None:
        ax_main.axhline(float(take_profit), linestyle='-', color='green', linewidth=1.5, label='TP')

    # RSI 30/70 reference lines
    if ax_rsi is not None:
        ax_rsi.axhline(30, linestyle='--', color='green', linewidth=0.8, alpha=0.5)
        ax_rsi.axhline(70, linestyle='--', color='red', linewidth=0.8, alpha=0.5)

    # Render to BytesIO — no disk I/O
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)   # CRITICAL: prevent memory leak in long-running process

    elapsed = time.time() - t_start
    logger.debug(f"Chart rendered for {symbol} in {elapsed:.2f}s ({n_bars} bars)")

    return buf.read()


# ---------------------------------------------------------------------------
# Async entry point — offloads to thread pool
# ---------------------------------------------------------------------------

async def generate_chart(df: pd.DataFrame, signal: dict, zones: dict) -> bytes:
    """Generate a PNG chart as bytes. Async wrapper over CPU-bound _render_chart().

    Offloads rendering to asyncio.to_thread() to avoid blocking the event loop.
    mplfinance rendering typically takes 2-5 seconds on standard hardware.

    Returns bytes starting with b'\\x89PNG'.
    Raises RuntimeError if rendering fails.
    """
    try:
        return await asyncio.to_thread(_render_chart, df, signal, zones)
    except Exception as e:
        logger.error(f"Chart generation failed for {signal.get('symbol', '?')}: {e}")
        raise RuntimeError(f"Chart generation failed: {e}") from e
