# Phase 5: Order Execution and Position Monitoring — Research

**Researched:** 2026-03-20
**Domain:** Binance USDT-M Futures order placement, bracket SL/TP management, APScheduler polling job, dry-run mode
**Confidence:** HIGH (core API patterns verified against Binance official docs and Binance Dev Community; python-binance method names confirmed from library source)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Market order by default for entry — guaranteed execution, handles slippage
- SL/TP bracket placed simultaneously with entry (after entry fill) — not before fill
- Set margin type to ISOLATED before every new position (enforced programmatically)
- No retry on any order failure — alert only, trader decides next step
- Simple polling every 60 seconds (no WebSocket) — check SL/TP order statuses on Binance
- Close detection: monitor SL and TP order statuses — when one fills, position is closed
- On close: send Telegram notification with final PnL and close reason (SL hit / TP hit)
- On close: create Trade record in DB (entry, exit, PnL, close reason)
- On close: update win streak counter (win = TP hit, loss = SL hit) for progressive stakes
- On close: update daily stats aggregation (PnL, trade count, win rate)
- Polling job runs as APScheduler IntervalTrigger (every 60 seconds)
- Insufficient balance: Telegram alert "⚠️ Недостаточно баланса: $X доступно, $Y необходимо", mark signal as 'failed', no retry
- API timeout: Telegram alert with error details, no retry (risk of duplicate orders)
- Unknown Binance errors: Telegram alert with error code and message, mark signal as 'error'
- All errors go through `send_error_alert()` from Phase 4 notifications (15-min throttle applies)
- No automatic retry on any order placement failure
- Dry-run: signal goes through full flow but order is logged to DB as 'dry_run' status instead of being sent to Binance
- Telegram shows "[DRY RUN]" prefix on confirmation messages
- Dry-run toggled via `/dryrun on/off` Telegram command — runtime toggle, no restart needed
- Dry-run state stored in module-level `_bot_state` dict (same pattern as `/pause` from Phase 4)
- Position monitoring skips dry-run signals (no Binance orders to monitor)

### Claude's Discretion
- Exact Binance Futures API method calls for bracket order placement
- Partial fill handling details (likely not needed for market orders on Futures)
- Position monitoring implementation (APScheduler job vs dedicated async task)
- How to reconcile DB state with Binance state on monitoring cycle
- Error code mapping (Binance error codes to user-friendly Russian messages)

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ORD-01 | Market order placed on Binance Futures after Telegram confirmation | `futures_create_order(type='MARKET')` after `handle_confirm` updates signal status |
| ORD-02 | SL and TP orders placed immediately after entry fill | Three separate API calls: MARKET entry, then STOP_MARKET + TAKE_PROFIT_MARKET with `closePosition=True` |
| ORD-03 | Order confirmation sent to Telegram with fill price and actual position size | `order['avgPrice']` and `order['executedQty']` from MARKET order response |
| ORD-04 | Order errors sent to Telegram immediately with actionable description | Binance error codes -4046, -4164, -2018, -2010, -1111 mapped to Russian messages via `send_error_alert()` |
| ORD-05 | Double-tap protection — DB-level unique constraint prevents duplicate orders | Unique constraint on `orders.signal_id` + check signal status before executing |
| MON-01 | Open positions tracked with current PnL via Binance API polling | `futures_position_information(symbol=sym)` every 60s yields `unRealizedProfit` |
| MON-02 | Notification sent when SL or TP is hit with final PnL | Check SL/TP order status: `futures_get_order(symbol, orderId)` — when status='FILLED', notify |
| MON-03 | Trade record created on position close | Create `Trade` row with exit_price from filled order response, close_reason='sl' or 'tp' |
| MON-04 | Win streak counter updated on position close | Update `RiskSettings.win_streak_current`; call `get_next_stake()` from risk manager |
| MON-05 | Daily stats aggregated (PnL, trade count, win rate) | UPSERT `DailyStats` row for today using `ON CONFLICT DO UPDATE` |
</phase_requirements>

---

## Summary

Phase 5 connects the confirmed Telegram trade signal to an actual Binance Futures market order with bracket SL/TP, then monitors open positions via periodic polling until close. The core complexity is the **three-call order sequence**: (1) set isolated margin + leverage, (2) place MARKET entry, (3) place STOP_MARKET and TAKE_PROFIT_MARKET bracket orders using `closePosition=True`. Because Binance has no native OTOCO (One-Triggers-One-Cancels-Other) endpoint, bracket management is manual — when the monitor detects one bracket order filled, it must cancel the surviving bracket via `futures_cancel_order`.

The trigger point is `handle_confirm` in `bot/telegram/handlers/callbacks.py`, which currently marks signals as 'confirmed' and stops. Phase 5 adds the Order Executor that detects newly-confirmed signals (either triggered directly from the callback or by a background scan of confirmed signals) and executes them. The Position Monitor runs as a new APScheduler `IntervalTrigger` job alongside the existing `strategy_scan` and `expiry_check` jobs in `main.py`.

Dry-run mode is new in this phase: the `/dryrun on/off` command extends the `_bot_state` dict in `commands.py` with a `dry_run` key. In dry-run mode, orders are logged to DB with `status='dry_run'` and monitoring ignores them — no Binance API calls.

**Primary recommendation:** Trigger Order Executor directly from `handle_confirm` via `asyncio.create_task(execute_order(signal_id, ...))` — this avoids a polling scan for 'confirmed' signals and matches the existing `asyncio.create_task` pattern used for market scans. Monitor runs as a 60-second `IntervalTrigger` APScheduler job.

---

## Standard Stack

### Core (all already in project dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-binance | 1.0.35 | Futures order API, position polling | Already in use; `AsyncClient` covers all needed endpoints |
| APScheduler | 3.11.2 | 60-second position monitoring job | Already in use; `IntervalTrigger` is the right trigger type for polling |
| SQLAlchemy | 2.0.48 | Order/Position/Trade/DailyStats DB ops | Already in use; async session pattern established |
| aiogram | 3.26.0 | `/dryrun` command, Telegram notifications | Already in use; extend `commands.py` router |
| loguru | 0.7+ | Structured logging for order events | Already in use |

### No new dependencies required

All necessary libraries are already in `requirements.txt`. Phase 5 adds new modules (`bot/order/executor.py`, `bot/monitor/position.py`) using the existing stack.

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
bot/
├── order/
│   ├── __init__.py
│   └── executor.py          # execute_order() — margin, leverage, market order, bracket
├── monitor/
│   ├── __init__.py
│   └── position.py          # monitor_positions() — polling job, close detection
```

Existing files modified:
- `bot/telegram/handlers/callbacks.py` — `handle_confirm` triggers `execute_order`
- `bot/telegram/handlers/commands.py` — adds `/dryrun on/off` command
- `bot/main.py` — registers position monitoring APScheduler job

### Pattern 1: Order Execution Sequence

**What:** Three sequential API calls for a bracket order. Isolated margin and leverage are set before the market order. SL and TP are placed after entry fill confirmation.

**When to use:** Every time `handle_confirm` fires for a non-dry-run signal.

```python
# Source: Binance Futures API + python-binance library
# bot/order/executor.py

async def execute_order(
    signal_id: uuid.UUID,
    session_factory,
    binance_client: AsyncClient,
    settings: Settings,
    bot,  # aiogram Bot
) -> None:
    """Full order placement flow for one confirmed signal.

    Steps:
      1. Load signal from DB (guard: must be status='confirmed')
      2. Load risk settings
      3. Dry-run guard: if _bot_state["dry_run"], log and return
      4. Check daily loss limit (circuit breaker)
      5. Check max open positions
      6. Set isolated margin (ignore -4046 "already set")
      7. Set leverage
      8. Calculate position size (uses actual current price, not signal.entry_price)
      9. Validate MIN_NOTIONAL
      10. Place MARKET entry order
      11. Create Order + Position rows in DB
      12. Place STOP_MARKET order (closePosition=True)
      13. Place TAKE_PROFIT_MARKET order (closePosition=True)
      14. Update Order rows with SL/TP binance_order_ids
      15. Send Telegram confirmation with fill price + size
    """
    ...

async def _set_isolated_margin(client: AsyncClient, symbol: str) -> None:
    """Set margin type to ISOLATED. Silently ignore -4046 (already set)."""
    try:
        await client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
    except BinanceAPIException as e:
        if e.code == -4046:  # "No need to change margin type"
            return
        raise  # propagate unexpected errors

async def _set_leverage(client: AsyncClient, symbol: str, leverage: int) -> None:
    await client.futures_change_leverage(symbol=symbol, leverage=leverage)
```

### Pattern 2: Bracket Order Placement

**What:** STOP_MARKET and TAKE_PROFIT_MARKET orders placed after the MARKET entry fills. Both use `closePosition=True` and `reduceOnly` is implied. For a LONG, SL side=SELL and TP side=SELL. For a SHORT, SL side=BUY and TP side=BUY.

```python
# Source: Binance Futures API documentation + Binance Dev Community verified patterns

# Entry order — MARKET
entry_order = await client.futures_create_order(
    symbol=signal.symbol,
    side="BUY" if signal.direction == "long" else "SELL",
    type="MARKET",
    quantity=formatted_quantity,  # rounded to stepSize
)
fill_price = float(entry_order["avgPrice"])
filled_qty = float(entry_order["executedQty"])

# SL order — STOP_MARKET
sl_side = "SELL" if signal.direction == "long" else "BUY"
sl_order = await client.futures_create_order(
    symbol=signal.symbol,
    side=sl_side,
    type="STOP_MARKET",
    stopPrice=formatted_sl_price,   # rounded to tickSize
    closePosition=True,
    timeInForce="GTE_GTC",
    workingType="MARK_PRICE",
    priceProtect=True,
)

# TP order — TAKE_PROFIT_MARKET
tp_order = await client.futures_create_order(
    symbol=signal.symbol,
    side=sl_side,  # same as SL side
    type="TAKE_PROFIT_MARKET",
    stopPrice=formatted_tp_price,   # rounded to tickSize
    closePosition=True,
    timeInForce="GTE_GTC",
    workingType="MARK_PRICE",
    priceProtect=True,
)
```

**Key detail:** `closePosition=True` means Binance will close the entire position when triggered. This is correct for a simple bracket; no `quantity` needed on SL/TP orders.

### Pattern 3: Quantity and Price Precision

**What:** Binance rejects orders where `quantity` or `price` has more decimal places than the symbol's `stepSize` (for quantity) or `tickSize` (for price). Use `round_step_size` from `binance.helpers`.

```python
# Source: python-binance helpers module
from binance.helpers import round_step_size

# Fetch exchange info once per symbol (cache it) to get stepSize and tickSize
# GET /fapi/v1/exchangeInfo
info = await client.futures_exchange_info()
symbol_info = next(s for s in info["symbols"] if s["symbol"] == symbol)
step_size = float(next(f["stepSize"] for f in symbol_info["filters"] if f["filterType"] == "LOT_SIZE"))
tick_size = float(next(f["tickSize"] for f in symbol_info["filters"] if f["filterType"] == "PRICE_FILTER"))

quantity = round_step_size(raw_contracts, step_size)
sl_price = round_step_size(signal.stop_loss, tick_size)
tp_price = round_step_size(signal.take_profit, tick_size)
```

**Warning:** Caching exchange info per-session is recommended. Do NOT call `futures_exchange_info()` on every order — it's expensive. Cache in memory for the bot's lifetime (exchange info changes rarely).

### Pattern 4: Position Monitor Polling Job

**What:** APScheduler `IntervalTrigger` job runs every 60 seconds. Loads all open positions from DB, checks their SL/TP order statuses on Binance, detects fills, closes positions.

**When to use:** Registered in `main.py` alongside existing jobs.

```python
# bot/monitor/position.py

async def monitor_positions(
    session_factory,
    binance_client: AsyncClient,
    settings: Settings,
    bot,
) -> None:
    """Called every 60 seconds by APScheduler.

    For each open Position in DB with non-dry-run status:
      1. Fetch order status for sl_order_id and tp_order_id from Binance
      2. If sl_order_id status == 'FILLED' -> close_reason = 'sl'
      3. If tp_order_id status == 'FILLED' -> close_reason = 'tp'
      4. If position itself is gone from Binance (positionAmt == 0) -> close_reason = 'manual'
      5. On detection: cancel the surviving bracket order
      6. Fetch realized PnL from trade history
      7. Create Trade record, close Position, update DailyStats, update win streak
      8. Send Telegram close notification
    """

# main.py addition
scheduler.add_job(
    lambda: asyncio.create_task(
        monitor_positions(SessionLocal, binance_client, settings, bot)
    ),
    trigger=IntervalTrigger(seconds=60),
    id="position_monitor",
    replace_existing=True,
)
```

### Pattern 5: Close Detection Logic

**What:** When one bracket order fills, cancel the surviving bracket. Binance does NOT automatically cancel the survivor.

```python
# Source: Binance Dev Community confirmed behavior

async def _handle_position_close(
    client, session_factory, bot, settings,
    position: Position,
    close_reason: str,   # 'sl' or 'tp'
    filled_order_id: str,
    surviving_order_id: str,
    exit_price: float,
) -> None:
    # Cancel the surviving bracket order
    try:
        await client.futures_cancel_order(
            symbol=position.symbol,
            orderId=int(surviving_order_id),
        )
    except BinanceAPIException as e:
        # -2011: Unknown order — already cancelled or expired; safe to ignore
        if e.code != -2011:
            logger.warning(f"Unexpected error cancelling surviving bracket: {e}")

    # Fetch realized PnL from recent trade history
    trades = await client.futures_account_trades(
        symbol=position.symbol,
        limit=5,
    )
    realized_pnl = sum(float(t["realizedPnl"]) for t in trades
                       if t["orderId"] == int(filled_order_id))

    # DB: create Trade, close Position, upsert DailyStats, update RiskSettings
    async with session_factory() as session:
        # ... DB writes ...

    # Telegram notification
    pnl_sign = "+" if realized_pnl >= 0 else ""
    close_emoji = "✅" if close_reason == "tp" else "❌"
    msg = (
        f"{close_emoji} Позиция закрыта: {position.symbol} {position.side.upper()}\n\n"
        f"Цена входа:  ${position.entry_price:.4f}\n"
        f"Цена выхода: ${exit_price:.4f}\n"
        f"PnL: {pnl_sign}${realized_pnl:.2f}\n"
        f"Причина: {'Take Profit' if close_reason == 'tp' else 'Stop Loss'}"
    )
    await bot.send_message(settings.allowed_chat_id, msg)
```

### Pattern 6: Dry-Run Mode

**What:** Extends `_bot_state` dict with a `dry_run` key. When True, Order Executor skips all Binance API calls and creates an Order row with `status='dry_run'`.

```python
# bot/telegram/handlers/commands.py — extend existing _bot_state

# Existing:
_bot_state: dict = {"paused": False}

# After Phase 5:
_bot_state: dict = {"paused": False, "dry_run": False}

# New command handler:
@router.message(Command("dryrun"))
async def cmd_dryrun(message: Message, **kwargs) -> None:
    """Toggle dry-run mode: /dryrun on or /dryrun off"""
    parts = (message.text or "").split()
    if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
        status = "ВКЛ" if _bot_state.get("dry_run") else "ВЫКЛ"
        await message.answer(f"Dry-run: {status}\nИспользование: /dryrun on|off")
        return
    _bot_state["dry_run"] = (parts[1].lower() == "on")
    status = "ВКЛ" if _bot_state["dry_run"] else "ВЫКЛ"
    await message.answer(f"Dry-run: {status}")
```

### Pattern 7: DailyStats UPSERT

**What:** When a trade closes, update today's DailyStats row. Use PostgreSQL `ON CONFLICT DO UPDATE` via SQLAlchemy `insert()`.

```python
# Source: SQLAlchemy 2.0 PostgreSQL dialect
from sqlalchemy.dialects.postgresql import insert as pg_insert

today = datetime.now(timezone.utc).date()

stmt = pg_insert(DailyStats).values(
    date=today,
    total_pnl=realized_pnl,
    trade_count=1,
    win_count=1 if close_reason == "tp" else 0,
).on_conflict_do_update(
    index_elements=["date"],
    set_={
        "total_pnl": DailyStats.total_pnl + realized_pnl,
        "trade_count": DailyStats.trade_count + 1,
        "win_count": DailyStats.win_count + (1 if close_reason == "tp" else 0),
    }
)
await session.execute(stmt)
await session.commit()
# Then compute win_rate = win_count / trade_count and update separately
```

### Anti-Patterns to Avoid

- **Do not use `reduceOnly=True` with `closePosition=True`** — these parameters conflict. Binance returns an error if both are set. Use only `closePosition=True` for bracket orders.
- **Do not call `futures_exchange_info()` on every order** — cache the result at startup or per-session.
- **Do not poll ALL positions every cycle if symbol list is large** — fetch `futures_position_information()` once per cycle (returns all), then filter by open DB positions. This is one API call instead of N.
- **Do not store only binance_order_id as string without the symbol** — `futures_get_order` and `futures_cancel_order` require both `symbol` AND `orderId`. Store the symbol on the Position/Order row (already done in DB model).
- **Do not assume MARKET orders always fill fully** — on Futures testnet they do, on production they can partially fill on illiquid pairs. Check `executedQty` vs `origQty`. For this project's pairs (top-N by volume), partial fills are rare but log a warning if `executedQty != origQty`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Quantity precision rounding | Custom rounding logic | `binance.helpers.round_step_size` | Handles float precision edge cases |
| Error code detection | String parsing of error messages | `BinanceAPIException.code` attribute | Type-safe, doesn't break on message wording changes |
| Position PnL fetch | Deriving PnL from entry/exit math | `futures_account_trades()` realizedPnl field | Binance applies funding rates, fees — manual math will be wrong |
| DailyStats aggregation | Recomputing from full Trade history | `INSERT ... ON CONFLICT DO UPDATE` with increments | Atomic; avoids race conditions and full-scan recalculation |
| Win streak update | In-memory counter | Update `RiskSettings.win_streak_current` in DB | Survives restarts; same source of truth as `get_next_stake()` |

---

## Common Pitfalls

### Pitfall 1: Margin Type Change Error (-4046) Treated as Fatal

**What goes wrong:** `futures_change_margin_type()` raises `BinanceAPIException` with code -4046 when the margin is already ISOLATED. If the executor doesn't catch this specifically, the order fails on every subsequent call after the first position.

**Why it happens:** Binance returns -4046 ("No need to change margin type") not as a success, but as an exception in python-binance. The first call for a symbol succeeds; all subsequent calls for the same symbol fail.

**How to avoid:** Wrap `futures_change_margin_type` in a try/except that specifically catches `-4046` and continues. Re-raise on any other code.

**Warning signs:** First order succeeds, second order for the same symbol fails with a margin error.

---

### Pitfall 2: SL/TP Order Triggers Immediately (-2021)

**What goes wrong:** When placing the STOP_MARKET (SL) or TAKE_PROFIT_MARKET (TP) order after the market fill, the stop price may already be past the current mark price, causing Binance to reject with `-2021 ORDER_WOULD_IMMEDIATELY_TRIGGER`.

**Why it happens:** Slippage on the market order fill: the actual fill price differs from `signal.entry_price`. If the signal had tight SL/TP relative to entry, the filled price may already have passed the stop price.

**How to avoid:** After the MARKET order fills, re-validate SL/TP prices against the actual `fill_price` (not the signal's `entry_price`). If `fill_price` is past the SL: alert via `send_error_alert()`, cancel the entry (close position), mark signal as 'error'. If the SL is valid, proceed.

**Warning signs:** Order executor uses `signal.stop_loss` directly without checking fill price delta.

---

### Pitfall 3: Surviving Bracket Order Causes Unexpected Re-Entry

**What goes wrong:** SL fires, position closes. The TP order is still open on Binance. Price reverses and passes the TP price, triggering the TP order — which now opens a NEW position in the opposite direction (since the original position is already closed).

**Why it happens:** `closePosition=True` on a TAKE_PROFIT_MARKET order means "close current open position when triggered." But if there's no position in that direction, Binance may interpret it as a new order on some account configurations.

**How to avoid:** Cancel the surviving bracket order immediately when the other fills. Do not allow the monitor cycle to miss a cancellation. Verify via `futures_get_order` after cancel that the order is in CANCELED status.

---

### Pitfall 4: Double-Order on Signal (ORD-05)

**What goes wrong:** `handle_confirm` fires twice (double-tap, network retry). Both instances enter `execute_order()` concurrently. Both check signal status before the other has updated it. Two market orders are placed.

**Why it happens:** The callback handler's SELECT FOR UPDATE pattern prevents the status update from racing, but `execute_order` is called as an `asyncio.create_task` — both tasks can be in flight simultaneously.

**How to avoid:** Inside `execute_order`, wrap the signal status check and update in a SELECT FOR UPDATE before any Binance API call. If signal status is not 'confirmed' when the task runs, return early. Additionally, add a UNIQUE constraint on `(orders.signal_id)` — if two Order rows are inserted for the same signal_id, the second will fail at the DB level.

**Note:** The `Order` DB model has `signal_id` as a nullable foreign key but no unique constraint. The planner should add `__table_args__ = (UniqueConstraint("signal_id"),)` to the Order model (or in a migration) to enforce ORD-05 at the DB level.

---

### Pitfall 5: Monitoring Polls Correct Symbol but Wrong DB Position

**What goes wrong:** Bot has two positions open for the same symbol (e.g., a long opened before a short from the same bot cycle). The monitor detects a fill on one SL/TP pair and closes the wrong DB position record.

**Why it happens:** DB positions are matched to Binance orders by symbol alone, not by order ID.

**How to avoid:** Store `sl_order_id` and `tp_order_id` on the `Position` row (or in a JSONB metadata field). Monitor checks order status by order ID, not by symbol alone. Match closes by order ID. The Position model currently lacks `sl_order_id` and `tp_order_id` fields — these must be added in a migration.

---

### Pitfall 6: Polling Rate Accumulation on Multiple Open Positions

**What goes wrong:** With 5 open positions and 60-second polling, each cycle makes at minimum 5 `futures_get_order` calls for SL + 5 for TP = 10 calls. Plus 1 `futures_position_information` call. Rate limit is 2400 weight/minute; each call costs ~5 weight = 55 weight per cycle, well within limits. But if `futures_exchange_info` is also called per cycle, this escalates quickly.

**How to avoid:** Cache exchange info at startup. Use a single `futures_position_information()` call (returns all positions) rather than per-symbol calls. Only call `futures_get_order` for positions where both SL and TP order IDs are known and non-null.

---

### Pitfall 7: Testnet Monthly Wipe Orphans DB Positions

**What goes wrong:** Testnet resets monthly. All open positions and orders on Binance vanish. DB still has open Position rows with stale `binance_order_id` values. Monitor polls these stale IDs and receives errors.

**How to avoid:** The existing `startup_position_sync()` in `main.py` already detects DB positions not on Binance and logs a warning. For Phase 5: when `futures_get_order` returns `-2013 ORDER_DOES_NOT_EXIST`, log a warning and close the DB position as 'orphaned'. Do not alert the trader via Telegram for this — only log. This is a testnet-only concern.

---

### Pitfall 8: Win Streak Update Race Between Monitor and DB

**What goes wrong:** Two positions close on the same monitoring cycle (unlikely but possible). Both try to update `RiskSettings.win_streak_current`. The second update overwrites the first increment rather than stacking.

**How to avoid:** Process position closes sequentially within a single monitoring job execution (not as concurrent tasks). The 60-second polling interval makes this manageable — process positions one at a time inside the monitor loop.

---

## DB Model Gaps (Required Additions)

The existing `Position` model needs two new columns. These must be added via Alembic migration in Wave 0 or Plan 00:

```python
# Addition to bot/db/models.py Position class
sl_order_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
tp_order_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
is_dry_run: Mapped[bool] = mapped_column(
    sa.Boolean, server_default=text("false"), nullable=False
)
```

The `Order` model needs a unique constraint on `signal_id` for ORD-05:

```python
# Addition to bot/db/models.py Order class __table_args__
__table_args__ = (sa.UniqueConstraint("signal_id", name="uq_orders_signal_id"),)
```

The `Signal` model needs an additional status value: `'dry_run'` (already `String(20)`, no schema change needed — just a new valid string value).

---

## Code Examples

### Full Order Execution Flow (Pseudocode)

```python
# bot/order/executor.py
# Source: Binance Futures API + python-binance patterns

from binance.exceptions import BinanceAPIException
from binance.helpers import round_step_size

async def execute_order(signal_id, session_factory, binance_client, settings, bot, bot_state):
    # Step 0: Dry-run guard
    if bot_state.get("dry_run"):
        async with session_factory() as session:
            # mark signal as 'dry_run', create Order row with status='dry_run'
            ...
        await bot.send_message(
            settings.allowed_chat_id,
            "[DRY RUN] Ордер не размещён — режим тестирования."
        )
        return

    # Step 1: Load signal (must be status='confirmed')
    async with session_factory() as session:
        result = await session.execute(
            select(Signal).where(Signal.id == signal_id, Signal.status == "confirmed")
            .with_for_update()
        )
        signal = result.scalar_one_or_none()
        if signal is None:
            return  # already processed or not confirmed
        signal.status = "executing"
        await session.commit()

    # Step 2: Load risk settings
    async with session_factory() as session:
        risk = (await session.execute(select(RiskSettings).limit(1))).scalar_one()

    # Step 3: Circuit breakers (daily loss, max positions)
    # ... check_daily_loss, check_max_positions ...

    # Step 4: Get current account balance
    account = await binance_client.futures_account()
    balance = float(account["totalWalletBalance"])

    # Step 5: Set isolated margin (ignore -4046)
    await _set_isolated_margin(binance_client, signal.symbol)

    # Step 6: Set leverage
    await binance_client.futures_change_leverage(
        symbol=signal.symbol, leverage=risk.leverage
    )

    # Step 7: Get precision info
    # (use cached exchange_info if available)
    info = await binance_client.futures_exchange_info()
    sym_info = next(s for s in info["symbols"] if s["symbol"] == signal.symbol)
    step_size = float(next(f["stepSize"] for f in sym_info["filters"] if f["filterType"] == "LOT_SIZE"))
    tick_size = float(next(f["tickSize"] for f in sym_info["filters"] if f["filterType"] == "PRICE_FILTER"))

    # Step 8: Get current price for sizing (not signal.entry_price — it may be stale)
    ticker = await binance_client.futures_symbol_ticker(symbol=signal.symbol)
    current_price = float(ticker["price"])

    # Step 9: Calculate position size
    pos_size = calculate_position_size(
        balance=balance,
        current_stake_pct=risk.current_stake_pct,
        entry_price=current_price,
        stop_loss=signal.stop_loss,
        leverage=risk.leverage,
    )
    quantity = round_step_size(pos_size["contracts"], step_size)
    sl_price = round_step_size(signal.stop_loss, tick_size)
    tp_price = round_step_size(signal.take_profit, tick_size)

    # Step 10: Place MARKET entry order
    entry_side = "BUY" if signal.direction == "long" else "SELL"
    try:
        entry_order = await binance_client.futures_create_order(
            symbol=signal.symbol,
            side=entry_side,
            type="MARKET",
            quantity=quantity,
        )
    except BinanceAPIException as e:
        await _handle_order_error(e, signal, session_factory, bot, settings)
        return

    fill_price = float(entry_order["avgPrice"])
    filled_qty = float(entry_order["executedQty"])

    # Step 11: Create Order + Position rows in DB
    # ...

    # Step 12: Place bracket SL + TP
    bracket_side = "SELL" if signal.direction == "long" else "BUY"
    try:
        sl_order = await binance_client.futures_create_order(
            symbol=signal.symbol,
            side=bracket_side,
            type="STOP_MARKET",
            stopPrice=sl_price,
            closePosition=True,
            timeInForce="GTE_GTC",
            workingType="MARK_PRICE",
            priceProtect=True,
        )
        tp_order = await binance_client.futures_create_order(
            symbol=signal.symbol,
            side=bracket_side,
            type="TAKE_PROFIT_MARKET",
            stopPrice=tp_price,
            closePosition=True,
            timeInForce="GTE_GTC",
            workingType="MARK_PRICE",
            priceProtect=True,
        )
    except BinanceAPIException as e:
        # Bracket placement failed — close the open position immediately
        await binance_client.futures_create_order(
            symbol=signal.symbol,
            side=bracket_side,
            type="MARKET",
            quantity=filled_qty,
            reduceOnly=True,
        )
        await _handle_order_error(e, signal, session_factory, bot, settings)
        return

    # Step 13: Update Position with sl_order_id, tp_order_id
    # ...

    # Step 14: Telegram confirmation
    msg = (
        f"✅ Ордер открыт: {signal.symbol} {'LONG' if signal.direction == 'long' else 'SHORT'}\n\n"
        f"Цена входа:    ${fill_price:.4f}\n"
        f"Размер:        {filled_qty} контрактов\n"
        f"Stop Loss:     ${sl_price:.4f}\n"
        f"Take Profit:   ${tp_price:.4f}"
    )
    await bot.send_message(settings.allowed_chat_id, msg)
```

### Error Code to Russian Message Mapping

```python
# Source: Binance Futures API error code docs

BINANCE_ERROR_MESSAGES = {
    -2018: "Недостаточно баланса: баланс аккаунта недостаточен для открытия позиции",
    -4164: "MIN_NOTIONAL: размер позиции слишком мал для этой пары",
    -2021: "Ордер сработал бы немедленно: цена SL/TP уже достигнута",
    -1111: "Ошибка точности: некорректное количество или цена",
    -4061: "Конфликт направления позиции (positionSide)",
    -2010: "Ордер отклонён биржей",
    -4131: "Недостаточно ликвидности для рыночного ордера",
}

def get_error_message(code: int, raw_message: str) -> str:
    return BINANCE_ERROR_MESSAGES.get(
        code,
        f"Ошибка Binance [{code}]: {raw_message}"
    )
```

### Position Monitoring Cycle (Core Logic)

```python
# bot/monitor/position.py
# Source: python-binance AsyncClient methods

async def monitor_positions(session_factory, binance_client, settings, bot) -> None:
    """APScheduler IntervalTrigger job — runs every 60 seconds."""
    async with session_factory() as session:
        result = await session.execute(
            select(Position).where(
                Position.status == "open",
                Position.is_dry_run == False,
                Position.sl_order_id.is_not(None),
                Position.tp_order_id.is_not(None),
            )
        )
        positions = result.scalars().all()

    for position in positions:
        try:
            sl_order = await binance_client.futures_get_order(
                symbol=position.symbol,
                orderId=int(position.sl_order_id),
            )
            tp_order = await binance_client.futures_get_order(
                symbol=position.symbol,
                orderId=int(position.tp_order_id),
            )

            if sl_order["status"] == "FILLED":
                exit_price = float(sl_order["avgPrice"])
                await _handle_position_close(
                    binance_client, session_factory, bot, settings,
                    position, "sl", position.sl_order_id, position.tp_order_id, exit_price
                )
            elif tp_order["status"] == "FILLED":
                exit_price = float(tp_order["avgPrice"])
                await _handle_position_close(
                    binance_client, session_factory, bot, settings,
                    position, "tp", position.tp_order_id, position.sl_order_id, exit_price
                )
            # Also update unrealized_pnl for /positions command
            else:
                pos_info = await binance_client.futures_position_information(
                    symbol=position.symbol
                )
                for pi in pos_info:
                    if pi["symbol"] == position.symbol:
                        unrealized = float(pi["unRealizedProfit"])
                        async with session_factory() as session:
                            pos_db = await session.get(Position, position.id)
                            pos_db.unrealized_pnl = unrealized
                            await session.commit()

        except BinanceAPIException as e:
            if e.code == -2013:  # ORDER_DOES_NOT_EXIST — testnet wipe
                logger.warning(f"Monitor: stale order for {position.symbol} — testnet wipe?")
            else:
                logger.error(f"Monitor error for {position.symbol}: {e}")
        except Exception as e:
            logger.error(f"Monitor unexpected error for {position.symbol}: {e}")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Polling every 10s for position monitoring | Polling every 60s (project decision) | Phase 5 design | Lower API weight cost; 60s acceptable for SL/TP detection latency |
| WebSocket user data stream for fills | REST polling (project decision) | Phase 5 design | Simpler — no reconnect handling; acceptable for single-trader bot |
| `reduceOnly=True` on bracket orders | `closePosition=True` (preferred) | Binance API evolution | `closePosition=True` closes entire position without specifying quantity; safer |
| Separate OCO implementation | Three separate orders with manual cancel | Binance Futures has no native OCO | Binance Futures does NOT support OCO — three-order approach is the only option |

---

## Open Questions

1. **Trigger mechanism for execute_order**
   - What we know: `handle_confirm` marks signal as 'confirmed'. Options: (A) call `asyncio.create_task(execute_order(...))` directly from the callback handler, (B) have a background scanner detect 'confirmed' signals periodically.
   - What's unclear: Option A is more direct but requires `binance_client` and `bot` to be accessible in the callback handler's kwargs. Option B has up to 60s latency.
   - Recommendation: Use Option A — extend `handle_confirm` to receive `binance_client` and `bot` from `dp` workflow data (already injected there). This maintains the "within 5 seconds" target from the spec.

2. **Realized PnL source**
   - What we know: `futures_account_trades()` returns per-trade realized PnL including fees. `futures_position_information()` returns `unRealizedProfit`. After position close, unrealized becomes 0.
   - What's unclear: The most reliable way to get final realized PnL is `futures_account_trades(symbol=..., limit=5)` filtered to the filled order's ID. This should cover funding and fees.
   - Recommendation: Use `futures_account_trades()` filtered by `orderId` for accurate post-close PnL.

3. **Exchange info caching strategy**
   - What we know: `stepSize` and `tickSize` are needed for every order. They change rarely (only when Binance adjusts contract specs).
   - Recommendation: Cache in a module-level dict `_exchange_info_cache: dict[str, dict]` populated on first order per symbol. TTL not needed for a single-session bot.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24+ |
| Config file | `pytest.ini` (already exists, `asyncio_mode = auto`) |
| Quick run command | `pytest tests/test_order_executor.py tests/test_position_monitor.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ORD-01 | Market order placed after confirmation | unit | `pytest tests/test_order_executor.py::test_market_order_placed -x` | ❌ Wave 0 |
| ORD-02 | SL + TP bracket placed after fill | unit | `pytest tests/test_order_executor.py::test_bracket_orders_placed -x` | ❌ Wave 0 |
| ORD-03 | Telegram confirmation with fill price | unit | `pytest tests/test_order_executor.py::test_confirmation_notification -x` | ❌ Wave 0 |
| ORD-04 | Binance errors sent to Telegram | unit | `pytest tests/test_order_executor.py::test_error_handling -x` | ❌ Wave 0 |
| ORD-05 | Double-tap protection via signal status lock | unit | `pytest tests/test_order_executor.py::test_double_tap_protection -x` | ❌ Wave 0 |
| MON-01 | Position PnL updated via polling | unit | `pytest tests/test_position_monitor.py::test_pnl_update -x` | ❌ Wave 0 |
| MON-02 | Close notification sent on SL/TP fill | unit | `pytest tests/test_position_monitor.py::test_close_notification -x` | ❌ Wave 0 |
| MON-03 | Trade record created on close | unit | `pytest tests/test_position_monitor.py::test_trade_record_created -x` | ❌ Wave 0 |
| MON-04 | Win streak updated on close | unit | `pytest tests/test_position_monitor.py::test_win_streak_update -x` | ❌ Wave 0 |
| MON-05 | DailyStats aggregated on close | unit | `pytest tests/test_position_monitor.py::test_daily_stats_update -x` | ❌ Wave 0 |
| DRY-RUN | Dry-run skips Binance API, marks status='dry_run' | unit | `pytest tests/test_order_executor.py::test_dry_run_mode -x` | ❌ Wave 0 |
| DRY-CMD | /dryrun on/off toggles _bot_state["dry_run"] | unit | `pytest tests/test_telegram_commands.py::test_cmd_dryrun -x` | ❌ Wave 0 (extend existing) |

**Note on existing test:** `tests/test_telegram_commands.py` exists and tests the commands router. The `/dryrun` handler test should be added there rather than a new file.

### Sampling Rate

- **Per task commit:** `pytest tests/test_order_executor.py tests/test_position_monitor.py -x -q`
- **Per wave merge:** `pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_order_executor.py` — covers ORD-01 through ORD-05 and dry-run
- [ ] `tests/test_position_monitor.py` — covers MON-01 through MON-05
- [ ] Mock `AsyncClient` extension in `tests/conftest.py`:
  - `mock_binance_client.futures_change_margin_type`
  - `mock_binance_client.futures_change_leverage`
  - `mock_binance_client.futures_create_order`
  - `mock_binance_client.futures_get_order`
  - `mock_binance_client.futures_cancel_order`
  - `mock_binance_client.futures_account_trades`
  - `mock_binance_client.futures_symbol_ticker`
- [ ] Alembic migration stub: `Position.sl_order_id`, `Position.tp_order_id`, `Position.is_dry_run`, `Order.signal_id` unique constraint

---

## Sources

### Primary (HIGH confidence)
- Binance USDT-M Futures REST API: `https://developers.binance.com/docs/derivatives/usds-margined-futures/` — error codes, order types, parameter names verified
- Binance Futures error codes: `https://developers.binance.com/docs/derivatives/usds-margined-futures/error-code` — error -4046, -4164, -2018, -2021, -1111 confirmed
- python-binance library (existing project usage) — `AsyncClient.futures_create_order`, `futures_change_margin_type`, `futures_change_leverage` method names confirmed from existing bot code and library search
- `binance.helpers.round_step_size` — confirmed from python-binance helpers module

### Secondary (MEDIUM confidence)
- Binance Dev Community: OTOCO bracket order approach (three separate orders, no native OCO) — confirmed in official Binance developer forum at `dev.binance.vision/t/how-to-implement-otoco-tp-sl-orders-using-api/1622`
- `closePosition=True` + `workingType='MARK_PRICE'` + `priceProtect=True` pattern — verified from multiple Binance developer forum posts and community code examples
- Error -4046 "No need to change margin type" behavior — confirmed from Binance developer community `dev.binance.vision/t/how-to-isolate-funds-for-futures-isolated-margin-account-type/17064` and freqtrade issue #6224

### Tertiary (LOW confidence — project-specific design)
- Trigger approach (Option A: asyncio.create_task from handle_confirm) — architectural recommendation based on existing project patterns; not validated against the actual implementation
- Exchange info caching pattern — standard practice, not verified against python-binance behavior

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries already in use; no new dependencies
- Binance API calls (method names, parameters): HIGH — verified against official docs and community sources
- Architecture patterns: MEDIUM — logical extension of established project patterns; not yet implemented
- Pitfalls: HIGH — sourced from official error codes + existing project PITFALLS.md

**Research date:** 2026-03-20
**Valid until:** 2026-06-20 (Binance API changes rarely; python-binance version pinned at 1.0.35)
