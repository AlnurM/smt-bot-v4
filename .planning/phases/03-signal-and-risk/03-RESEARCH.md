# Phase 3: Signal and Risk - Research

**Researched:** 2026-03-19
**Domain:** SMC signal detection, MACD/RSI indicators, position sizing, mplfinance chart generation
**Confidence:** HIGH (stack verified; SMC parameter ranges MEDIUM — not standardized)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**SMC Detection Parameters**
- SMC params (ob_lookback_bars, fvg_min_size_pct, require_bos_confirm, use_choch, htf_confirmation) come from strategy JSON per coin
- Always exclude the current (incomplete) candle: `df.iloc[:-1]` — signals only on fully closed data, deterministic results
- Higher timeframe confirmation: fetch 4h OHLCV data separately, run BOS/CHOCH detection on it, require alignment with 15m signal direction
- Order Block identification: combined approach — OB = last opposite candle before a BOS, AND must show significant body relative to surrounding candles (imbalance characteristic)
- Fair Value Gap: standard 3-candle gap, but only registered if gap size >= `fvg_min_size_pct` from strategy JSON
- BOS vs CHOCH: standard ICT definitions — BOS = break in trend direction (continuation), CHOCH = break against trend (reversal)

**Signal Strength Logic**
- Weighted scoring system: each entry condition has a weight (e.g., HTF BOS confirmation = 3, OB zone = 2, MACD cross = 2, RSI confirmation = 1, volume = 1)
- Signal strength derived from total score: Strong (>=7), Moderate (4-6), Weak (1-3) — thresholds TBD during implementation
- ALL signals sent to Telegram regardless of strength — labeled with strength for trader to decide
- Entry conditions: which conditions are required vs optional is defined by strategy JSON (not hardcoded 4-of-4)
- Signal object includes: direction, entry price, SL, TP, R/R ratio, signal strength label, reasoning text listing which conditions were met

**Chart Visual Style**
- Follow spec exactly for colors: green OB (demand), red OB (supply), transparent FVG with dashed borders, blue dashed entry line, red solid SL, green solid TP
- Dynamic candle range: auto-adjust to include all relevant OB/FVG zones in view (not fixed 100-150)
- 200 DPI for sharper display on high-res phones
- MACD panel below chart: histogram + signal lines, crossover point marked
- RSI panel below MACD: 30/70 levels, signal zone highlighted
- Chart title: symbol, timeframe, direction, R/R ratio
- Render to BytesIO, no disk I/O

**Risk Edge Cases**
- MIN_NOTIONAL: when position size is too small, still send signal to Telegram but mark as "too small to execute" — informational only, no Confirm button
- Liquidation safety: configurable multiplier stored in risk_settings (default 2x SL distance) — reject if liquidation price is closer than threshold
- Daily loss limit (5%): stop generating new signals, keep existing positions open with their SL/TP, send prominent Telegram alert
- Progressive stakes: advance through tiers (3->5->8%) on consecutive wins, reset to base on any loss (from spec, already in RiskSettings)
- Max open positions: enforce before allowing new signals (default 5, from risk_settings)
- R/R minimum: signals below min_rr_ratio are filtered out before reaching Telegram

### Claude's Discretion
- Exact weighted scoring values for signal strength
- Signal strength threshold breakpoints (Strong/Moderate/Weak)
- mplfinance chart configuration details (figure size, spacing, panel ratios)
- Thread pool executor configuration for chart rendering
- How to handle edge cases in SMC detection (e.g., overlapping OBs, nested FVGs)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SIG-01 | Signal Generator applies active strategy to current OHLCV data and detects entry conditions | Strategy JSON structure already defined in StrategySchema; fetch_ohlcv_15m() reusable |
| SIG-02 | SMC analysis: identifies Order Blocks, Fair Value Gaps, Break of Structure, Change of Character | Custom implementation guided by ICT definitions; smartmoneyconcepts library available as reference |
| SIG-03 | Indicator analysis: MACD crossovers, RSI oversold/overbought exits | pandas-ta-classic 0.4.47; MACD columns: MACD_f_s_sig, MACDH_f_s_sig, MACDS_f_s_sig; RSI column: RSI_period |
| SIG-04 | Higher timeframe confirmation (4h BOS/CHOCH) required before signal emission | Fetch 4h via futures_historical_klines with KLINE_INTERVAL_1HOUR*4 or KLINE_INTERVAL_4HOUR; run BOS/CHOCH separately |
| SIG-05 | Volume confirmation: volume must exceed average by configurable multiplier | Volume average computed from df['volume'].rolling(N).mean(); multiplier from strategy JSON |
| SIG-06 | Signal includes: direction, entry, SL, TP, R/R ratio, signal strength, reasoning | Signal ORM model already has all these fields; OB/FVG zone coordinates also needed for Chart |
| RISK-01 | Position size: % of balance / SL distance * leverage | Formula from spec section 7.3 — verified against idea.md |
| RISK-02 | Progressive stakes: configurable tiers based on consecutive win count | RiskSettings.progressive_stakes JSONB, win_streak_current already in DB |
| RISK-03 | Win streak resets to base stake on any loss | RiskSettings.reset_on_loss flag; update current_stake_pct and win_streak_current in DB |
| RISK-04 | Maximum open positions limit enforced before new order | Count open Position rows with status='open'; compare to risk_settings.max_open_positions |
| RISK-05 | Daily loss limit — trading paused, notification sent | Query DailyStats for today; compare total_pnl vs starting_balance * daily_loss_limit_pct |
| RISK-06 | Minimum R/R ratio filter — signals below threshold ignored | Compare signal rr_ratio to risk_settings.min_rr_ratio before saving/sending |
| RISK-07 | Isolated margin enforced on every position | Set in risk_settings.margin_type; validated at order placement (Phase 5) but risk manager must flag |
| RISK-08 | MIN_NOTIONAL check before order submission | Send as informational-only signal with no Confirm button; fetch min_notional from exchangeInfo |
| RISK-09 | Liquidation price calculated and validated before every order | Formula: Entry * (1 - 1/(leverage * (1+mmr))); liquidation_distance >= multiplier * sl_distance |
| RISK-10 | All risk parameters adjustable via Telegram /risk command | Reads from RiskSettings; Telegram handler is Phase 4 — but risk module must expose update interface |
| CHART-01 | PNG chart with candlestick data (dynamic candle range) | mplfinance 0.12.10b0; returnfig=True to get axes for overlays; dynamic range = span OB/FVG zones |
| CHART-02 | Order Block zones (green=demand, red=supply rectangles) | matplotlib Rectangle patch added to axes[0] after returnfig |
| CHART-03 | Fair Value Gap zones (transparent rectangles with dashed borders) | Rectangle with alpha, linestyle='--' |
| CHART-04 | BOS/CHOCH levels (horizontal lines with labels) | axes[0].axhline + axes[0].text for label |
| CHART-05 | Entry, SL, TP horizontal lines with correct colors | axes[0].axhline with color and linestyle parameters |
| CHART-06 | MACD panel (histogram + lines, crossover marked) | make_addplot with panel=1; separate calls for MACD line, signal line, histogram (type='bar') |
| CHART-07 | RSI panel (30/70 levels, signal zone highlighted) | make_addplot with panel=2; axhline at 30/70 after returnfig |
| CHART-08 | Chart title: symbol, timeframe, direction, R/R ratio | axes[0].set_title() after returnfig |
| CHART-09 | Chart rendered to BytesIO at 200 DPI (spec says 200; requirements say 150 — use 200 per CONTEXT.md) | fig.savefig(buf, format='png', dpi=200, bbox_inches='tight') |
</phase_requirements>

---

## Summary

Phase 3 builds the three core analysis modules that together produce a tradeable signal: Signal Generator (SMC + indicator detection), Risk Manager (position sizing and circuit breakers), and Chart Generator (mplfinance PNG with all SMC overlays).

All infrastructure from Phases 1-2 is in place: the database models (Signal, RiskSettings, DailyStats, Position) are already migrated, the OHLCV fetch function (`fetch_ohlcv_15m`) exists, and the strategy JSON structure is defined by `StrategySchema`. Phase 3 consumes these — it does not modify them. The main engineering challenge is the custom SMC detection logic (Order Blocks, FVG, BOS/CHOCH), which has no single authoritative implementation and requires parameter ranges that are not standardized in the literature.

The chart generation approach is well-understood: mplfinance `returnfig=True` gives access to matplotlib axes for adding Rectangle patches and axhline overlays. The CPU-bound rendering must be offloaded via `asyncio.to_thread()` to avoid blocking the aiogram event loop. The risk formulas are fully specified in idea.md section 7.3 and need careful implementation of the liquidation price check to protect the small-account use case.

**Primary recommendation:** Implement SMC detection as a pure function module (`bot/signals/smc.py`) that returns structured zone objects consumed by both Signal Generator and Chart Generator. This prevents coordinate mismatch between what triggered the signal and what appears on the chart.

---

## Standard Stack

### Core (already in requirements.txt or needs adding)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas-ta-classic | 0.4.47 | MACD, RSI calculation via df.ta accessor | Community fork of pandas-ta; original at risk of archival. Latest release March 17, 2026. Not yet in requirements.txt — must be added |
| mplfinance | 0.12.10b0 | Candlestick chart + multi-panel PNG | Only production-ready Python candlestick library with OHLCV panel management. Stable since 2023. Not yet in requirements.txt — must be added |
| matplotlib | (mplfinance dependency) | Rectangle patches, axhline, set_title | Direct matplotlib calls needed for OB/FVG overlays on top of mplfinance figure |
| numpy | 2.4.3 (already in venv) | Numeric ops in SMC detection | Already installed as pandas dependency |
| pandas | 3.0.1 (already in requirements.txt) | DataFrame operations for OHLCV | Already installed |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| smartmoneyconcepts | 0.0.26 | Reference implementation for OB/FVG/BOS/CHOCH algorithms | Use as implementation reference and fallback, NOT as a direct dependency — its ICT parameter model differs from the project's combined approach. Study the source for algorithm patterns. |
| asyncio.to_thread | stdlib (Python 3.9+) | Offload mplfinance CPU work to thread pool | Use in chart generator to avoid blocking aiogram event loop |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom SMC detection | `smartmoneyconcepts` package directly | smc package uses different OB definition (swing-based only); project uses combined OB+imbalance approach that requires custom code |
| mplfinance | matplotlib directly | mplfinance handles OHLCV candlestick rendering with correct bar widths; raw matplotlib requires much more boilerplate |
| asyncio.to_thread | ThreadPoolExecutor | to_thread is cleaner one-shot API; executor needed only for repeated parallel work |

**Installation (additions to requirements.txt):**
```bash
pip install pandas-ta-classic==0.4.47 mplfinance==0.12.10b0
```

**DPI note:** CONTEXT.md specifies 200 DPI. REQUIREMENTS.md CHART-09 says 150 DPI. CONTEXT.md locked decision takes precedence — use 200 DPI.

**MPLBACKEND note (critical for Docker):** mplfinance raises `_tkinter.TclError` in headless containers. Must set `MPLBACKEND=Agg` in Dockerfile ENV and call `matplotlib.use('Agg')` before importing mplfinance.

---

## Architecture Patterns

### Recommended Module Structure

```
bot/
├── signals/
│   ├── __init__.py
│   ├── generator.py      # orchestrates SMC + indicators + entry evaluation
│   ├── smc.py            # pure functions: detect_order_blocks(), detect_fvg(), detect_bos_choch()
│   └── indicators.py     # pure functions: compute_macd(), compute_rsi()
├── risk/
│   ├── __init__.py
│   └── manager.py        # calculate_position_size(), check_daily_limit(), check_max_positions()
└── charts/
    ├── __init__.py
    └── generator.py      # async generate_chart() wrapping sync _render_chart()
```

### Pattern 1: SMC Zone Object — Shared Between Signal and Chart

The SMC detector returns structured zone objects that are passed through the pipeline. Both Signal Generator (for scoring) and Chart Generator (for rendering) consume the same objects. This prevents coordinate mismatch.

```python
# Source: project design — derived from ICT definitions
from dataclasses import dataclass
from typing import Literal

@dataclass
class OrderBlock:
    direction: Literal["bullish", "bearish"]
    high: float
    low: float
    bar_index: int          # integer index in the sliced DataFrame
    strength: float         # body ratio relative to surrounding candles

@dataclass
class FairValueGap:
    direction: Literal["bullish", "bearish"]
    high: float
    low: float
    bar_index: int          # candle index where FVG starts (candle[i-1])
    size_pct: float         # gap size as percentage of candle[i-1].close

@dataclass
class StructureLevel:
    level_type: Literal["BOS", "CHOCH"]
    direction: Literal["bullish", "bearish"]
    price: float
    bar_index: int
```

### Pattern 2: SMC Detection — Pure Functions on Closed Candles Only

```python
# Source: ICT concepts + CONTEXT.md locked decision
def detect_order_blocks(df: pd.DataFrame, ob_lookback_bars: int) -> list[OrderBlock]:
    """
    Always called on df.iloc[:-1] (closed candles only).
    OB = last opposite candle before a BOS, with significant body relative
    to surrounding candles (imbalance characteristic).
    Returns list ordered most-recent first.
    """
    closed = df.iloc[:-1]
    # ...
```

### Pattern 3: MACD/RSI Computation with pandas-ta-classic

```python
# Source: pandas-ta-classic 0.4.47 API
import pandas_ta as ta

def compute_macd(df: pd.DataFrame, fast: int, slow: int, signal: int) -> pd.DataFrame:
    """Returns DataFrame with MACD_{fast}_{slow}_{signal}, MACDH_..., MACDS_... columns."""
    macd_df = df.ta.macd(fast=fast, slow=slow, signal=signal)
    # Column names: MACD_12_26_9, MACDH_12_26_9, MACDS_12_26_9 for default params
    return macd_df

def compute_rsi(df: pd.DataFrame, period: int) -> pd.Series:
    """Returns RSI_{period} series."""
    return df.ta.rsi(length=period)
```

### Pattern 4: mplfinance Multi-Panel Chart with Overlays

```python
# Source: mplfinance 0.12.10b0 API + project spec
import mplfinance as mpf
import matplotlib
matplotlib.use('Agg')  # Must be called before any other matplotlib import
from matplotlib.patches import Rectangle
from io import BytesIO

def _render_chart(df: pd.DataFrame, signal, zones) -> bytes:
    """Sync rendering function — run via asyncio.to_thread()."""

    # Build addplots for MACD (panel=1) and RSI (panel=2)
    macd_line = mpf.make_addplot(macd_values['MACD_line'], panel=1, color='blue', width=1.0)
    macd_signal = mpf.make_addplot(macd_values['MACD_signal'], panel=1, color='orange', width=0.8)
    macd_hist = mpf.make_addplot(macd_values['MACD_hist'], panel=1, type='bar',
                                  color=['green' if v >= 0 else 'red' for v in macd_values['MACD_hist']])
    rsi_line = mpf.make_addplot(rsi_values, panel=2, color='purple', width=1.0,
                                 ylim=(0, 100))

    fig, axes = mpf.plot(
        df,
        type='candle',
        style='charles',
        addplot=[macd_line, macd_signal, macd_hist, rsi_line],
        panel_ratios=(3, 1, 1),   # main:MACD:RSI height ratio
        returnfig=True,
        figsize=(12, 8),
        title=f"{signal.symbol} {signal.timeframe} | {signal.direction.upper()} | R/R {signal.rr_ratio:.2f}",
    )
    ax_main = axes[0]
    ax_macd = axes[2]   # axes indexing: 0=main, 1=volume(if enabled), 2=panel1, 4=panel2
    ax_rsi = axes[4]

    # OB rectangles — x-axis is integer index (NOT datetime)
    for ob in zones.order_blocks:
        color = 'green' if ob.direction == 'bullish' else 'red'
        width = len(df) - ob.bar_index   # extend to right edge
        rect = Rectangle((ob.bar_index, ob.low), width, ob.high - ob.low,
                          facecolor=color, alpha=0.15, edgecolor=color, linewidth=1)
        ax_main.add_patch(rect)

    # FVG rectangles (transparent with dashed border)
    for fvg in zones.fvgs:
        color = 'green' if fvg.direction == 'bullish' else 'red'
        width = len(df) - fvg.bar_index
        rect = Rectangle((fvg.bar_index, fvg.low), width, fvg.high - fvg.low,
                          facecolor=color, alpha=0.05,
                          edgecolor=color, linewidth=1, linestyle='--')
        ax_main.add_patch(rect)

    # BOS/CHOCH horizontal lines
    for sl in zones.structure_levels:
        ax_main.axhline(sl.price, linestyle='-' if sl.level_type == 'BOS' else '--',
                        color='gray', linewidth=0.8, alpha=0.7)
        ax_main.text(0.01, sl.price, sl.level_type, transform=ax_main.get_yaxis_transform(),
                     fontsize=7, color='gray')

    # Entry/SL/TP lines
    ax_main.axhline(signal.entry_price, linestyle='--', color='royalblue', linewidth=1.2)
    ax_main.axhline(signal.stop_loss, linestyle='-', color='red', linewidth=1.5)
    ax_main.axhline(signal.take_profit, linestyle='-', color='green', linewidth=1.5)

    # RSI 30/70 reference lines
    ax_rsi.axhline(30, linestyle='--', color='green', linewidth=0.8, alpha=0.5)
    ax_rsi.axhline(70, linestyle='--', color='red', linewidth=0.8, alpha=0.5)

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=200, bbox_inches='tight')
    buf.seek(0)
    import matplotlib.pyplot as plt
    plt.close(fig)   # CRITICAL: prevent memory leak in long-running process
    return buf.read()

async def generate_chart(df: pd.DataFrame, signal, zones) -> bytes:
    """Async wrapper — offloads CPU-bound rendering to thread pool."""
    return await asyncio.to_thread(_render_chart, df, signal, zones)
```

### Pattern 5: Position Sizing Formula (from idea.md section 7.3)

```python
# Source: idea.md section 7.3 — canonical formula
def calculate_position_size(
    balance: float,
    current_stake_pct: float,
    entry_price: float,
    stop_loss: float,
    leverage: int,
) -> dict:
    """
    Returns: {risk_usdt, sl_distance, position_usdt, contracts}
    Example: balance=100, stake=3%, entry=145, sl=140, leverage=5x
      risk_usdt=3.00, sl_distance=3.45%, position_usdt=86.96, contracts=3.0 SOL
    """
    risk_usdt = balance * current_stake_pct / 100
    sl_distance = abs(entry_price - stop_loss) / entry_price   # as fraction
    position_usdt = risk_usdt / sl_distance
    contracts = (position_usdt * leverage) / entry_price
    return {
        "risk_usdt": risk_usdt,
        "sl_distance": sl_distance,
        "position_usdt": position_usdt,
        "contracts": contracts,
    }
```

### Pattern 6: Liquidation Price Validation (from PITFALLS.md Pitfall 1)

```python
# Source: Binance official docs on isolated margin liquidation
def validate_liquidation_safety(
    entry_price: float,
    stop_loss: float,
    leverage: int,
    liquidation_multiplier: float = 2.0,   # from risk_settings
    maintenance_margin_rate: float = 0.004,  # Binance USDT-M default ~0.4%
) -> tuple[bool, float]:
    """
    Liquidation price for LONG (isolated margin):
      liq = entry * (1 - 1/(leverage * (1 + mmr)))
    Liquidation distance must be >= multiplier * SL distance.
    Returns (is_safe, liquidation_price).
    """
    sl_distance = abs(entry_price - stop_loss) / entry_price
    # Long position liquidation
    liq_price = entry_price * (1 - 1 / (leverage * (1 + maintenance_margin_rate)))
    liq_distance = abs(entry_price - liq_price) / entry_price
    is_safe = liq_distance >= (liquidation_multiplier * sl_distance)
    return is_safe, liq_price
```

### Pattern 7: Daily Loss Circuit Breaker

```python
# Source: CONTEXT.md locked decision
async def check_daily_loss_limit(
    session: AsyncSession,
    risk_settings: RiskSettings,
    current_balance: float,
) -> bool:
    """
    Returns True if trading is HALTED (daily limit reached).
    Queries DailyStats for today's total_pnl vs starting_balance.
    On halt: new signals suppressed; existing positions remain open.
    """
    today_stats = await get_daily_stats(session, date.today())
    if today_stats is None:
        return False
    if today_stats.starting_balance is None:
        return False
    daily_loss_pct = abs(today_stats.total_pnl) / today_stats.starting_balance * 100
    if today_stats.total_pnl < 0 and daily_loss_pct >= risk_settings.daily_loss_limit_pct:
        return True   # HALTED
    return False
```

### Anti-Patterns to Avoid

- **Using future candle data in detection:** Never use `df['col'].shift(-N)` for any N > 0 in signal detection. All detection runs on `df.iloc[:-1]` (closed candles only). This is already a locked decision from CONTEXT.md.
- **Generating chart in Telegram handler:** mplfinance is CPU-bound (2-5s). Always pre-generate at signal time and pass BytesIO to Phase 4. Never call `_render_chart()` directly in an async handler.
- **Closing matplotlib figure in thread:** Always call `plt.close(fig)` after `savefig()` inside `_render_chart()`. In a long-running process, unclosed figures leak memory.
- **Hardcoding min_notional:** Fetch from Binance `exchangeInfo` filters per symbol — it varies by pair and changes over time.
- **Sharing axes index assumptions across panel layouts:** mplfinance axes list indexing depends on whether `volume=True`. With `volume=False`: axes[0]=main, axes[2]=panel1, axes[4]=panel2. Confirm at implementation time.
- **Running SMC on raw df (including forming candle):** Always slice `df.iloc[:-1]` before calling any detection function. Document this as a contract at module entry point.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MACD calculation | Custom EMA subtraction | `df.ta.macd(fast, slow, signal)` | pandas-ta-classic handles EMA initialization correctly; custom MACD has common warm-up period mistakes |
| RSI calculation | Custom RS ratio loop | `df.ta.rsi(length=period)` | Wilder smoothing (not simple EMA) is easy to get wrong; library is verified |
| Candlestick chart base | Raw matplotlib `plot()` calls | `mplfinance.plot(returnfig=True)` | mplfinance handles bar width calculation, OHLCV column mapping, date formatting |
| Chart in async context | Thread management boilerplate | `asyncio.to_thread(_render_chart, ...)` | Standard Python 3.9+ pattern; no ThreadPoolExecutor boilerplate needed |
| OB/FVG algorithm reference | From-scratch ICT interpretation | Read `smartmoneyconcepts` source at `joshyattridge/smart-money-concepts/blob/master/smartmoneyconcepts/smc.py` | Verified open-source reference for algorithm patterns; but use as reference only — not as dependency |

**Key insight:** The MACD and RSI calculations have subtle implementation details (warm-up periods, Wilder vs EMA smoothing) that hand-rolled implementations get wrong. Always delegate math to pandas-ta-classic.

---

## Common Pitfalls

### Pitfall 1: Look-Ahead Bias in SMC Detection (CRITICAL)

**What goes wrong:** Detection code uses `df['high'].shift(-1)` or accesses future candles to "confirm" an OB or FVG. Pattern appears valid because DataFrame contains all historical data simultaneously.

**Why it happens:** Pandas processes the full DataFrame at once. Writing `df['ob_confirmed'] = df['high'].shift(-1) > df['close']` is look-ahead — easy to miss during development.

**How to avoid:** Enforce `df.iloc[:-1]` at the entry point of every detection function. Add a unit test: call detection at candle N, verify output is identical to calling at candle N+1 (excluding the new candle). Any `shift(-N)` for N>0 is a bug.

**Warning signs:** Backtested winrate >65%; detection uses `shift(-1)` anywhere.

### Pitfall 2: mplfinance Axes Index Confusion

**What goes wrong:** After `returnfig=True`, the axes list has non-obvious indexing. With `volume=False`, addplot panels are at axes[0], axes[2], axes[4]. With `volume=True`, they shift. Code that hardcodes `axes[1]` for MACD gets the wrong panel.

**Why it happens:** mplfinance inserts hidden axes for shared x-axis. Odd-indexed axes are shared x-axis artifacts.

**How to avoid:** Use `volume=False` and `panel_ratios` to control heights. After `returnfig`, log `len(axes)` and verify indices in a test render. Document the index mapping at the top of `generator.py`.

**Warning signs:** MACD lines appearing on the main candle chart instead of the sub-panel.

### Pitfall 3: matplotlib Memory Leak from Unclosed Figures

**What goes wrong:** `_render_chart()` called on every signal, each call creates a matplotlib figure. Without `plt.close(fig)`, figures accumulate in memory. At 50 signals/day over weeks, memory usage grows steadily.

**How to avoid:** Always call `plt.close(fig)` (or `matplotlib.pyplot.close('all')`) after `fig.savefig()` inside the sync render function.

### Pitfall 4: MIN_NOTIONAL Varies by Symbol

**What goes wrong:** Risk Manager uses a hardcoded $5 notional floor. SOLUSDT minimum is $5; some altcoin pairs are $10-20. Order is rejected with Binance error -4164.

**How to avoid:** Fetch symbol-specific `minNotional` from `/fapi/v1/exchangeInfo` → symbol filters → `MIN_NOTIONAL` filter. Per CONTEXT.md: when below MIN_NOTIONAL, send signal as informational only (no Confirm button) rather than silently dropping it.

### Pitfall 5: Progressive Stake Not Reset on Restart

**What goes wrong:** `win_streak_current` and `current_stake_pct` are in DB (`RiskSettings`). If a loss occurs just before restart, and the DB update of `current_stake_pct` didn't commit, the next run uses the old elevated stake.

**How to avoid:** `win_streak_current` and `current_stake_pct` updates must be in a single atomic DB transaction with the Trade close record. Risk Manager reads from DB on every signal — never from in-memory state. This is already the design (RiskSettings in DB).

### Pitfall 6: 4h HTF Fetch Adds Latency to Signal Loop

**What goes wrong:** Signal Generator fetches 4h OHLCV for every coin on every scan cycle. Each `futures_historical_klines` call adds 200-500ms. For 10 coins, that's 2-5 seconds per cycle before any detection runs.

**How to avoid:** Cache the 4h data per symbol with a TTL of 55 minutes (4h candles close every 4h, so a 55-min cache only misses by 1-2 candles maximum, which is acceptable). Invalidate cache on new 4h close. Alternatively, fetch 15m and 4h data concurrently using `asyncio.gather()`.

### Pitfall 7: mplfinance with Docker — _tkinter Error

**What goes wrong:** In Docker without a display server, `import mplfinance` raises `_tkinter.TclError: no display name`.

**How to avoid:** Set `MPLBACKEND=Agg` in docker-compose.yml ENV section. Also add `import matplotlib; matplotlib.use('Agg')` at the top of `bot/charts/generator.py` before importing mplfinance. This is documented in PITFALLS.md.

### Pitfall 8: Liquidation Price Closer Than Stop Loss

**What goes wrong:** At high leverage (10x+) or wide SL, the SL is placed below the liquidation price. The position liquidates before the SL is hit — a scenario where even a correct trade setup causes full margin loss.

**How to avoid:** Always compute liquidation price before sizing. If `liq_distance < sl_distance * liquidation_multiplier`, reject the signal with reasoning "liquidation too close to entry". Configurable multiplier (default 2x) already in CONTEXT.md.

---

## Code Examples

Verified patterns from official sources:

### pandas-ta-classic: MACD with custom parameters

```python
# Source: pandas-ta-classic 0.4.47 API (pypi.org/project/pandas-ta-classic)
import pandas_ta as ta

df.ta.macd(fast=12, slow=26, signal=9, append=True)
# Appends columns: MACD_12_26_9, MACDH_12_26_9, MACDS_12_26_9

# Standalone (without modifying df):
macd_df = df.ta.macd(fast=12, slow=26, signal=9)
macd_line = macd_df['MACD_12_26_9']
macd_signal = macd_df['MACDS_12_26_9']
macd_hist = macd_df['MACDH_12_26_9']
```

### pandas-ta-classic: RSI

```python
# Source: pandas-ta-classic 0.4.47 API
df.ta.rsi(length=14, append=True)
# Appends column: RSI_14

rsi_series = df.ta.rsi(length=14)  # standalone, returns Series named RSI_14
```

### mplfinance: savefig to BytesIO

```python
# Source: mplfinance 0.12.10b0 (github.com/matplotlib/mplfinance)
from io import BytesIO
import mplfinance as mpf

buf = BytesIO()
mpf.plot(df, type='candle', savefig=buf)  # basic
buf.seek(0)
png_bytes = buf.read()
```

### mplfinance: returnfig with multi-panel addplot

```python
# Source: mplfinance panels.ipynb example
fig, axes = mpf.plot(
    df,
    type='candle',
    addplot=[
        mpf.make_addplot(macd_line, panel=1, color='blue'),
        mpf.make_addplot(macd_signal, panel=1, color='orange'),
        mpf.make_addplot(macd_hist, panel=1, type='bar', color='gray'),
        mpf.make_addplot(rsi_series, panel=2, color='purple', ylim=(0, 100)),
    ],
    panel_ratios=(3, 1, 1),
    returnfig=True,
    figsize=(12, 8),
)
ax_main = axes[0]    # candlestick panel (volume=False assumed)
ax_macd = axes[2]    # first addplot panel
ax_rsi = axes[4]     # second addplot panel
```

### mplfinance: Rectangle patch for OB zone

```python
# Source: mplfinance GitHub issue #179 — add_patch on returnfig axes
from matplotlib.patches import Rectangle

# x-coordinate is integer bar index (0-based in the sliced DataFrame)
rect = Rectangle(
    (bar_start_idx, low_price),     # (x, y) lower-left corner
    width=(len(df) - bar_start_idx),  # extend to right edge of chart
    height=(high_price - low_price),
    facecolor='green',   # or 'red' for bearish OB
    alpha=0.15,
    edgecolor='green',
    linewidth=1,
)
ax_main.add_patch(rect)
```

### Liquidation price formula

```python
# Source: Binance official docs — Liquidation Price for Isolated Margin
# Long position: liq_price = entry * (1 - 1/(leverage * (1 + MMR)))
# Short position: liq_price = entry * (1 + 1/(leverage * (1 + MMR)))
# Binance USDT-M perpetual default maintenance margin rate (MMR) varies by tier:
#   Tier 1 (notional <= 10,000 USDT): 0.40% (0.004)
# At $100 account, leverage 5x, all positions will be Tier 1

entry = 145.0
leverage = 5
mmr = 0.004   # Tier 1 for notional < $10,000
liq_long = entry * (1 - 1 / (leverage * (1 + mmr)))   # ~116.0
liq_short = entry * (1 + 1 / (leverage * (1 + mmr)))   # ~174.0
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pandas-ta (original) | pandas-ta-classic fork | 2024-2025 | Original at archival risk; fork actively maintained as of March 2026 |
| asyncio.get_event_loop().run_in_executor() | asyncio.to_thread() | Python 3.9 (2020) | Cleaner API for one-shot thread offload |
| Fixed candle count for chart (100-150) | Dynamic candle range based on OB/FVG zone span | Phase 3 design | Chart always shows all relevant zones — no zone cut off |
| matplotlib backend auto-detect | Explicit `Agg` backend | Long-standing Docker requirement | Prevents `_tkinter` error in headless containers |

**Deprecated/outdated:**
- `asyncio.get_event_loop()` (Python 3.10+): deprecated in favor of `asyncio.get_running_loop()` or `asyncio.to_thread()`
- Original `pandas-ta` package: do not add to requirements.txt

---

## Open Questions

1. **pandas 3.x + pandas-ta-classic compatibility**
   - What we know: pandas 3.0.1 is installed; pandas-ta-classic 0.4.47 released March 2026 supports "Python 3.9-3.13"; no explicit pandas 3.x incompatibility reported
   - What's unclear: Whether `df.ta.macd()` works correctly with pandas 3.0 Series internals (Copy-on-Write behavior changed in pandas 2.0+)
   - Recommendation: Add a smoke test in Wave 0 that calls `df.ta.macd()` and `df.ta.rsi()` on sample OHLCV data and asserts expected column names are returned. Fail fast if pandas 3.x breaks the extension.

2. **mplfinance axes indexing with panel=2 and volume=False**
   - What we know: With `volume=False` and two addplot panels, axes list has 5 elements: [0]=main, [1]=shared_x, [2]=panel1, [3]=shared_x, [4]=panel2
   - What's unclear: Whether this holds with the exact `panel_ratios=(3,1,1)` config — mplfinance 0.12.10b0 docs are minimal
   - Recommendation: Write a test render with known data and log `len(axes)` + inspect each axis' y-limits to confirm mapping.

3. **SMC OB/FVG parameter ranges**
   - What we know: ob_lookback_bars, fvg_min_size_pct are strategy JSON params optimized by Claude per coin
   - What's unclear: Reasonable defensive bounds — e.g., should ob_lookback_bars < 5 be rejected? What is a safe minimum fvg_min_size_pct to avoid noise?
   - Recommendation: Implement soft bounds validation in SMC detector: warn (log) if params are outside [5, 50] for ob_lookback_bars or [0.05%, 2%] for fvg_min_size_pct. Don't hard-reject — let the strategy JSON drive it. Document in code.

4. **Binance MIN_NOTIONAL per symbol — fetch strategy**
   - What we know: MIN_NOTIONAL is in `exchangeInfo` symbol filters array; varies by pair; $5-$20 range typical
   - What's unclear: Whether Risk Manager should fetch this live on each signal or cache from a startup fetch
   - Recommendation: Fetch `exchangeInfo` once at startup (or hourly with Market Scanner), store `min_notional` per symbol in a lightweight in-memory dict. Risk Manager reads from dict — no live API call per signal.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (version from requirements-dev or installed) |
| Config file | `pytest.ini` (exists at repo root) |
| Quick run command | `pytest tests/test_smc.py tests/test_indicators.py tests/test_risk_manager.py tests/test_chart_generator.py -q --tb=short` |
| Full suite command | `pytest tests/ -q --tb=short -m "not integration"` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SIG-01 | Signal Generator returns Signal when all entry conditions met | unit | `pytest tests/test_signal_generator.py::test_signal_generated_when_conditions_met -x` | Wave 0 |
| SIG-02 | OB detected at correct bar index; FVG detected with size filter; BOS/CHOCH detected | unit | `pytest tests/test_smc.py -x` | Wave 0 |
| SIG-03 | MACD crossover detected; RSI exit from oversold/overbought detected | unit | `pytest tests/test_indicators.py -x` | Wave 0 |
| SIG-04 | HTF 4h confirmation fetched and aligned with signal direction | unit (mocked Binance) | `pytest tests/test_signal_generator.py::test_htf_confirmation -x` | Wave 0 |
| SIG-05 | Volume above average multiplier threshold triggers volume_ok=True | unit | `pytest tests/test_signal_generator.py::test_volume_confirmation -x` | Wave 0 |
| SIG-06 | Signal object has all required fields populated | unit | `pytest tests/test_signal_generator.py::test_signal_fields -x` | Wave 0 |
| RISK-01 | Position size formula matches spec example: balance=100, stake=3%, entry=145, sl=140, lev=5 -> contracts~3.0 | unit | `pytest tests/test_risk_manager.py::test_position_size_formula -x` | Wave 0 |
| RISK-02 | Current stake advances 3->5->8% after consecutive wins | unit | `pytest tests/test_risk_manager.py::test_progressive_stakes -x` | Wave 0 |
| RISK-03 | Stake resets to base_stake_pct on any loss | unit | `pytest tests/test_risk_manager.py::test_stake_reset_on_loss -x` | Wave 0 |
| RISK-04 | New signal rejected when open_positions >= max_open_positions | unit | `pytest tests/test_risk_manager.py::test_max_positions_enforced -x` | Wave 0 |
| RISK-05 | Signal generation halted when daily_loss >= daily_loss_limit_pct | unit | `pytest tests/test_risk_manager.py::test_daily_loss_circuit_breaker -x` | Wave 0 |
| RISK-06 | Signal with rr_ratio below min_rr_ratio is filtered | unit | `pytest tests/test_risk_manager.py::test_rr_filter -x` | Wave 0 |
| RISK-08 | MIN_NOTIONAL breach produces informational-only signal (no Confirm) | unit | `pytest tests/test_risk_manager.py::test_min_notional_informational -x` | Wave 0 |
| RISK-09 | Liquidation price computed correctly; signal rejected if liq too close | unit | `pytest tests/test_risk_manager.py::test_liquidation_safety -x` | Wave 0 |
| CHART-01 | generate_chart() returns non-empty bytes (PNG header b'\x89PNG') | unit | `pytest tests/test_chart_generator.py::test_chart_returns_png -x` | Wave 0 |
| CHART-02 | Chart generation does not raise with OB zones in input | unit | `pytest tests/test_chart_generator.py::test_chart_with_ob_zones -x` | Wave 0 |
| CHART-05 | Entry/SL/TP lines present in chart (visual: regression test with known output) | unit | `pytest tests/test_chart_generator.py::test_chart_entry_sl_tp -x` | Wave 0 |
| CHART-09 | Returned bytes decode as valid PNG; no disk file created | unit | `pytest tests/test_chart_generator.py::test_chart_bytesio_no_disk -x` | Wave 0 |

**Note on CHART-03, CHART-04, CHART-06, CHART-07, CHART-08:** These are visual correctness requirements — automated testing verifies "no exception raised" and "output is valid PNG bytes". Visual inspection during manual review verifies correct rendering.

**Note on RISK-07 (isolated margin):** Enforced at order placement (Phase 5). Risk Manager in Phase 3 logs the margin_type from RiskSettings but doesn't make API calls. Test verifies margin_type='isolated' is read from settings.

**Note on RISK-10 (Telegram /risk command):** Phase 4 responsibility. Risk Manager module must expose a pure `update_risk_settings()` function that Phase 4's handler calls.

### Sampling Rate
- **Per task commit:** `pytest tests/test_smc.py tests/test_indicators.py tests/test_risk_manager.py tests/test_chart_generator.py -q --tb=short`
- **Per wave merge:** `pytest tests/ -q --tb=short -m "not integration"`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_smc.py` — unit tests for OB/FVG/BOS/CHOCH detection (covers SIG-02)
- [ ] `tests/test_indicators.py` — unit tests for MACD crossover and RSI signal detection (covers SIG-03)
- [ ] `tests/test_signal_generator.py` — unit tests for full signal generation pipeline (covers SIG-01, SIG-04, SIG-05, SIG-06)
- [ ] `tests/test_risk_manager.py` — unit tests for all risk calculations and guards (covers RISK-01 to RISK-09)
- [ ] `tests/test_chart_generator.py` — unit tests for chart rendering to BytesIO (covers CHART-01, CHART-02, CHART-05, CHART-09)
- [ ] `tests/fixtures/ohlcv_sample.csv` — sample 15m OHLCV data (100+ rows) for deterministic unit tests
- [ ] `requirements-dev.txt` addition: `pandas-ta-classic==0.4.47 mplfinance==0.12.10b0` — or add to `requirements.txt` (not yet present)

---

## Sources

### Primary (HIGH confidence)
- [pandas-ta-classic PyPI](https://pypi.org/project/pandas-ta-classic/) — version 0.4.47, March 17, 2026; MACD/RSI API
- [mplfinance GitHub (matplotlib org)](https://github.com/matplotlib/mplfinance) — addplot panel API, returnfig, savefig to BytesIO
- [mplfinance subplots.md](https://github.com/matplotlib/mplfinance/blob/master/markdown/subplots.md) — panel configuration documentation
- [mplfinance panels.ipynb](https://github.com/matplotlib/mplfinance/blob/master/examples/panels.ipynb) — multi-panel addplot code examples
- `bot/db/models.py` — Signal, RiskSettings, DailyStats, Position ORM models (confirmed existing schema)
- `bot/scanner/market_scanner.py` — fetch_ohlcv_15m() reusable function
- `bot/strategy/claude_engine.py` — StrategySchema defining strategy JSON structure
- `idea.md` section 7.3 — canonical position sizing formula
- `idea.md` section 9.1 — canonical chart visual specification (colors, panels, elements)
- `.planning/research/PITFALLS.md` — liquidation math, look-ahead bias, Docker mplfinance
- `.planning/research/STACK.md` — confirmed library choices

### Secondary (MEDIUM confidence)
- [smartmoneyconcepts PyPI](https://pypi.org/project/smartmoneyconcepts/) — v0.0.26, March 2025; OB/FVG/BOS-CHOCH API reference
- [smartmoneyconcepts source](https://github.com/joshyattridge/smart-money-concepts/blob/master/smartmoneyconcepts/smc.py) — algorithm reference for OB/FVG/BOS/CHOCH implementation patterns
- [Binance liquidation formula (official)](https://www.binance.com/en/support/faq/how-liquidation-works-in-futures-trading-7ba80e1b406f40a0a140a84b3a10c387) — liquidation price calculation

### Tertiary (LOW confidence — use as reference only)
- WebSearch results on mplfinance Rectangle patch usage — verified against mplfinance GitHub issue #179 (MEDIUM)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all library versions verified against PyPI as of 2026-03-19
- Architecture: HIGH — based on existing project code and confirmed design from Phases 1-2
- SMC detection algorithm: MEDIUM — ICT concepts have no single standardized implementation; parameter ranges not validated against live data
- Pitfalls: HIGH — all critical pitfalls verified against official Binance docs and existing project PITFALLS.md
- Chart rendering: MEDIUM-HIGH — mplfinance API verified but axes indexing for 3-panel layout needs test-time confirmation

**Research date:** 2026-03-19
**Valid until:** 2026-04-19 (pandas-ta-classic and mplfinance are stable; Binance API changes could affect MIN_NOTIONAL fetch)
