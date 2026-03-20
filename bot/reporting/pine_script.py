"""Pine Script v5 generator — produces copy-paste ready TradingView code (PINE-01).

The generator is a pure function: given a signal dict (from DB or signal generator),
it returns a Pine Script v5 string with all values hardcoded.

zones_data format (as stored in Signal.zones_data JSONB):
{
    "order_blocks": [
        {"direction": "bullish"|"bearish", "high": float, "low": float,
         "bar_index": int, "strength": float}
    ],
    "fvgs": [
        {"direction": "bullish"|"bearish", "high": float, "low": float,
         "bar_index": int, "size_pct": float}
    ],
    "structure_levels": [
        {"level_type": "BOS"|"CHOCH", "direction": "bullish"|"bearish",
         "price": float, "bar_index": int}
    ]
}
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any


def _zones_to_json_safe(zones: dict) -> dict:
    """Convert zone dataclasses (from signal generator) to JSON-serialisable dicts.

    Handles both:
    - Dataclass instances (from generator — have __dataclass_fields__)
    - Plain dicts (already JSON-safe — loaded from DB JSONB)
    """
    result = {}
    for key, items in zones.items():
        result[key] = []
        for item in items:
            if hasattr(item, "__dataclass_fields__"):
                result[key].append(asdict(item))
            else:
                result[key].append(dict(item))
    return result


def generate_pine_script(
    symbol: str,
    timeframe: str,
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    rr_ratio: float,
    signal_strength: str | None,
    zones_data: dict | None,
) -> str:
    """Generate a Pine Script v5 string for the given signal parameters.

    Args:
        symbol: e.g. "SOLUSDT"
        timeframe: e.g. "1h"
        direction: "long" | "short"
        entry_price, stop_loss, take_profit, rr_ratio: float prices
        signal_strength: "Strong" | "Medium" | "Weak" | None
        zones_data: dict with "order_blocks", "fvgs", "structure_levels" keys
                    Values are either dataclass instances or plain dicts (both handled).

    Returns:
        Pine Script v5 string — copy-paste ready for TradingView Pine Editor.
    """
    zones = zones_data or {}

    # Normalize: convert dataclasses to dicts if needed
    safe = _zones_to_json_safe(zones) if zones else {}
    order_blocks: list[dict] = safe.get("order_blocks", [])
    fvgs: list[dict] = safe.get("fvgs", [])
    structure_levels: list[dict] = safe.get("structure_levels", [])

    direction_label = "LONG" if direction == "long" else "SHORT"
    strength_label = signal_strength or ""
    entry_arrow_style = "shape.triangleup" if direction == "long" else "shape.triangledown"
    entry_arrow_location = "location.belowbar" if direction == "long" else "location.abovebar"
    entry_arrow_color = "color.green" if direction == "long" else "color.red"

    lines: list[str] = []

    # Header
    lines.append("//@version=5")
    lines.append(f'indicator("CTB Signal — {symbol} {timeframe} {direction_label}", overlay=true)')
    lines.append("")

    # --- Order Block zones ---
    if order_blocks:
        lines.append("// Order Block zones")
        for i, ob in enumerate(order_blocks[:5], start=1):  # max 5 OBs
            ob_dir = ob.get("direction", "bullish")
            ob_high = float(ob.get("high", 0))
            ob_low = float(ob.get("low", 0))
            if ob_dir == "bullish":
                bg_color = "color.new(color.green, 80)"
                border_color = "color.green"
                label = "Demand OB"
            else:
                bg_color = "color.new(color.red, 80)"
                border_color = "color.red"
                label = "Supply OB"
            # bar_index offset relative to current bar — approximate with fixed width
            width = 10
            lines.append(
                f'var box ob{i} = box.new('
                f'bar_index-{width}, {ob_low}, bar_index, {ob_high}, '
                f'bgcolor={bg_color}, '
                f'border_color={border_color}, border_width=1, '
                f'xloc=xloc.bar_index)'
            )
            lines.append(
                f'label.new(bar_index-{width//2}, {(ob_high + ob_low) / 2:.4f}, '
                f'"{label}", color=color.new({border_color}, 90), '
                f'textcolor={border_color}, style=label.style_none, size=size.small)'
            )
        lines.append("")

    # --- FVG zones ---
    if fvgs:
        lines.append("// Fair Value Gap zones")
        for i, fvg in enumerate(fvgs[:5], start=1):  # max 5 FVGs
            fvg_dir = fvg.get("direction", "bullish")
            fvg_high = float(fvg.get("high", 0))
            fvg_low = float(fvg.get("low", 0))
            bg_color = "color.new(color.blue, 90)" if fvg_dir == "bullish" else "color.new(color.orange, 90)"
            border_color = "color.blue" if fvg_dir == "bullish" else "color.orange"
            lines.append(
                f'var box fvg{i} = box.new('
                f'bar_index-10, {fvg_low}, bar_index, {fvg_high}, '
                f'bgcolor={bg_color}, '
                f'border_color={border_color}, border_width=1, '
                f'border_style=line.style_dashed, '
                f'xloc=xloc.bar_index)'
            )
        lines.append("")

    # --- BOS / CHOCH structure levels ---
    if structure_levels:
        lines.append("// BOS / CHOCH structure levels")
        for i, sl in enumerate(structure_levels[:5], start=1):
            sl_type = sl.get("level_type", "BOS")
            sl_dir = sl.get("direction", "bullish")
            sl_price = float(sl.get("price", 0))
            line_color = "color.teal" if sl_dir == "bullish" else "color.maroon"
            lines.append(
                f'line.new(bar_index-20, {sl_price}, bar_index, {sl_price}, '
                f'color={line_color}, width=1, style=line.style_dotted)'
            )
            lines.append(
                f'label.new(bar_index-20, {sl_price}, "{sl_type}", '
                f'color=color.new({line_color}, 80), textcolor={line_color}, '
                f'style=label.style_label_right, size=size.small)'
            )
        lines.append("")

    # --- Entry / SL / TP hlines ---
    lines.append("// Entry / SL / TP levels")
    lines.append(
        f'hline({entry_price}, "Entry", color=color.blue, '
        f'linestyle=hline.style_dashed, linewidth=1)'
    )
    lines.append(
        f'hline({stop_loss}, "SL", color=color.red, '
        f'linestyle=hline.style_solid, linewidth=2)'
    )
    lines.append(
        f'hline({take_profit}, "TP", color=color.green, '
        f'linestyle=hline.style_solid, linewidth=2)'
    )
    lines.append("")

    # --- Entry arrow ---
    lines.append("// Entry arrow")
    lines.append(
        f'plotshape(bar_index == last_bar_index, '
        f'style={entry_arrow_style}, '
        f'location={entry_arrow_location}, '
        f'color={entry_arrow_color}, size=size.normal, '
        f'title="Entry {direction_label}")'
    )
    lines.append("")

    # --- Signal annotation label ---
    lines.append("// Signal info label")
    label_text = f"{direction_label} | R/R {rr_ratio:.1f}"
    if strength_label:
        label_text += f" | {strength_label}"
    lines.append(
        f'label.new(bar_index, {entry_price}, "{label_text}", '
        f'color=color.new(color.yellow, 70), textcolor=color.black, '
        f'style=label.style_label_down, size=size.normal)'
    )
    lines.append("")

    # --- MACD lower panel ---
    lines.append("// MACD (lower panel)")
    lines.append('[macd_line, signal_line, hist] = ta.macd(close, 12, 26, 9)')
    lines.append('plot(macd_line, "MACD", color=color.blue, display=display.pane)')
    lines.append('plot(signal_line, "Signal", color=color.orange, display=display.pane)')
    lines.append(
        'plot(hist, "Histogram", color=hist >= 0 ? color.new(color.green, 30) '
        ': color.new(color.red, 30), style=plot.style_histogram, display=display.pane)'
    )
    lines.append("")

    # --- RSI lower panel ---
    lines.append("// RSI (lower panel)")
    lines.append('rsi_val = ta.rsi(close, 14)')
    lines.append('plot(rsi_val, "RSI", color=color.purple, display=display.pane)')
    lines.append('hline(70, "Overbought", color=color.red, linestyle=hline.style_dashed, display=display.pane)')
    lines.append('hline(30, "Oversold", color=color.green, linestyle=hline.style_dashed, display=display.pane)')

    return "\n".join(lines)
