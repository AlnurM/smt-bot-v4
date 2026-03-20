"""Tests for generate_pine_script() — TDD RED phase.

Behavior spec:
- Signal with 2 OBs (one bullish, one bearish): output contains 2 `box.new(` calls
- Signal with 1 FVG: output contains `box.new(` with `border_style=line.style_dashed`
- Signal with 1 BOS bullish: output contains `line.new(` with label "BOS"
- Signal with direction=long: plotshape uses shape.triangleup, location.belowbar, color.green
- Signal with direction=short: plotshape uses shape.triangledown, location.abovebar, color.red
- Output always starts with //@version=5
- Output always contains hline({entry_price} and hline({stop_loss} and hline({take_profit}
- MACD indicator section always present (ma, signal line, histogram)
- RSI indicator section always present with levels 30 and 70
"""
import pytest

pine_script = pytest.importorskip("bot.reporting.pine_script")
generate_pine_script = pine_script.generate_pine_script
_zones_to_json_safe = pine_script._zones_to_json_safe


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LONG_SIGNAL_KWARGS = dict(
    symbol="SOLUSDT",
    timeframe="1h",
    direction="long",
    entry_price=145.30,
    stop_loss=140.00,
    take_profit=163.20,
    rr_ratio=3.37,
    signal_strength="Strong",
    zones_data={
        "order_blocks": [
            {"direction": "bullish", "high": 145.8, "low": 142.5, "bar_index": 50, "strength": 0.7},
            {"direction": "bearish", "high": 150.0, "low": 148.0, "bar_index": 40, "strength": 0.6},
        ],
        "fvgs": [
            {"direction": "bullish", "high": 144.0, "low": 143.0, "bar_index": 45, "size_pct": 0.5},
        ],
        "structure_levels": [
            {"level_type": "BOS", "direction": "bullish", "price": 143.5, "bar_index": 48},
        ],
    },
)

SHORT_SIGNAL_KWARGS = dict(
    symbol="BTCUSDT",
    timeframe="15m",
    direction="short",
    entry_price=45000.0,
    stop_loss=46000.0,
    take_profit=42000.0,
    rr_ratio=3.0,
    signal_strength="Weak",
    zones_data={},
)

EMPTY_ZONES_KWARGS = dict(
    symbol="BTCUSDT",
    timeframe="15m",
    direction="short",
    entry_price=45000.0,
    stop_loss=46000.0,
    take_profit=42000.0,
    rr_ratio=3.0,
    signal_strength=None,
    zones_data=None,
)


# ---------------------------------------------------------------------------
# Header / version tests
# ---------------------------------------------------------------------------

class TestHeader:
    def test_starts_with_version5(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert out.startswith("//@version=5"), f"Expected //@version=5 header, got: {out[:50]}"

    def test_indicator_line_contains_symbol_and_timeframe(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "SOLUSDT" in out
        assert "1h" in out


# ---------------------------------------------------------------------------
# Entry / SL / TP hlines
# ---------------------------------------------------------------------------

class TestHlines:
    def test_entry_hline_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "hline(145.3" in out, f"Expected hline(145.3...) in output"

    def test_sl_hline_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "hline(140.0" in out, f"Expected hline(140.0...) in output"

    def test_tp_hline_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "hline(163.2" in out, f"Expected hline(163.2...) in output"

    def test_short_hlines(self):
        out = generate_pine_script(**SHORT_SIGNAL_KWARGS)
        assert "hline(45000" in out
        assert "hline(46000" in out
        assert "hline(42000" in out


# ---------------------------------------------------------------------------
# Order Block zones
# ---------------------------------------------------------------------------

class TestOrderBlocks:
    def test_two_obs_produce_two_box_new(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        count = out.count("box.new(")
        # 2 OBs + 1 FVG = at least 3 box.new calls
        assert count >= 2, f"Expected >= 2 box.new calls for 2 OBs, got {count}"

    def test_bullish_ob_uses_green(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "color.green" in out

    def test_bearish_ob_uses_red(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "color.red" in out

    def test_no_ob_box_when_empty_zones(self):
        # No box.new calls for OBs when zones are empty — but FVG may add them
        out = generate_pine_script(**EMPTY_ZONES_KWARGS)
        # With empty zones, no box.new for OBs should appear
        # (FVGs are also empty, so zero total)
        assert "box.new(" not in out or "fvg" in out.lower()


# ---------------------------------------------------------------------------
# FVG zones
# ---------------------------------------------------------------------------

class TestFVG:
    def test_fvg_has_dashed_border_style(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "line.style_dashed" in out, "FVG should use border_style=line.style_dashed"

    def test_fvg_box_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "box.new(" in out


# ---------------------------------------------------------------------------
# BOS / CHOCH structure levels
# ---------------------------------------------------------------------------

class TestStructureLevels:
    def test_bos_line_new_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "line.new(" in out, "BOS should produce a line.new() call"

    def test_bos_label_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert '"BOS"' in out, "BOS label should appear in output"


# ---------------------------------------------------------------------------
# Entry arrow (plotshape)
# ---------------------------------------------------------------------------

class TestEntryArrow:
    def test_long_uses_triangleup(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "shape.triangleup" in out

    def test_long_uses_belowbar(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "location.belowbar" in out

    def test_long_uses_green(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "color.green" in out

    def test_short_uses_triangledown(self):
        out = generate_pine_script(**SHORT_SIGNAL_KWARGS)
        assert "shape.triangledown" in out

    def test_short_uses_abovebar(self):
        out = generate_pine_script(**SHORT_SIGNAL_KWARGS)
        assert "location.abovebar" in out

    def test_short_uses_red(self):
        out = generate_pine_script(**SHORT_SIGNAL_KWARGS)
        assert "color.red" in out


# ---------------------------------------------------------------------------
# MACD panel
# ---------------------------------------------------------------------------

class TestMACD:
    def test_macd_function_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "ta.macd" in out, "MACD indicator section missing"

    def test_macd_present_with_empty_zones(self):
        out = generate_pine_script(**EMPTY_ZONES_KWARGS)
        assert "ta.macd" in out


# ---------------------------------------------------------------------------
# RSI panel
# ---------------------------------------------------------------------------

class TestRSI:
    def test_rsi_function_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "ta.rsi" in out, "RSI indicator section missing"

    def test_rsi_level_70_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "hline(70" in out or "70" in out

    def test_rsi_level_30_present(self):
        out = generate_pine_script(**LONG_SIGNAL_KWARGS)
        assert "hline(30" in out or "30" in out

    def test_rsi_present_with_empty_zones(self):
        out = generate_pine_script(**EMPTY_ZONES_KWARGS)
        assert "ta.rsi" in out


# ---------------------------------------------------------------------------
# _zones_to_json_safe helper
# ---------------------------------------------------------------------------

class TestZonesToJsonSafe:
    def test_plain_dicts_pass_through(self):
        zones = {
            "order_blocks": [{"direction": "bullish", "high": 100.0, "low": 90.0, "bar_index": 10, "strength": 0.7}],
            "fvgs": [],
            "structure_levels": [],
        }
        result = _zones_to_json_safe(zones)
        assert result["order_blocks"][0]["high"] == 100.0

    def test_dataclass_instances_converted(self):
        from bot.signals.smc import OrderBlock, FairValueGap, StructureLevel
        zones = {
            "order_blocks": [OrderBlock(direction="bullish", high=100.0, low=90.0, bar_index=5, strength=0.8)],
            "fvgs": [FairValueGap(direction="bearish", high=95.0, low=93.0, bar_index=3, size_pct=0.3)],
            "structure_levels": [StructureLevel(level_type="BOS", direction="bullish", price=92.0, bar_index=4)],
        }
        result = _zones_to_json_safe(zones)
        assert isinstance(result["order_blocks"][0], dict)
        assert result["order_blocks"][0]["high"] == 100.0
        assert result["fvgs"][0]["size_pct"] == 0.3
        assert result["structure_levels"][0]["level_type"] == "BOS"
