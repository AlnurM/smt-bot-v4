"""Order Executor — turns a confirmed Telegram signal into an isolated-margin
Binance Futures market order with bracket SL/TP.

Full 19-step execution flow:
  0.  Dry-run guard
  1.  Load signal (must be status='confirmed') via SELECT FOR UPDATE
  2.  Mark signal 'executing'
  3.  Load RiskSettings
  4.  Load DailyStats + open Position count
  5.  Circuit breakers (daily loss, max positions)
  6.  Fetch account balance
  7.  Set isolated margin (ignore -4046)
  8.  Set leverage
  9.  Get symbol precision (step_size, tick_size)
  10. Get current price
  11. Calculate position size + MIN_NOTIONAL check
  12. Round quantity + SL/TP prices
  13. Place MARKET entry order
  14. Validate fill price vs SL
  15. Create Order row
  16. Create Position row
  17. Place STOP_MARKET + TAKE_PROFIT_MARKET bracket orders
  18. Update position with SL/TP order IDs; mark signal 'filled'
  19. Send Telegram confirmation
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from binance.exceptions import BinanceAPIException
from binance.helpers import round_step_size
from loguru import logger
from sqlalchemy import select, func

from bot.db.models import Signal, Order, Position, RiskSettings, DailyStats
from bot.risk.manager import (
    calculate_position_size,
    check_max_positions,
    check_daily_loss,
    check_min_notional,
)
from bot.telegram.notifications import send_error_alert

# Module-level exchange info cache — keyed by symbol, populated on first order per symbol.
# Avoids calling futures_exchange_info() on every order (expensive, changes rarely).
_exchange_info_cache: dict[str, dict] = {}

# Binance error code -> Russian-language description
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
    """Map Binance error codes to Russian-language descriptions.

    Falls back to a generic message including the raw code and text.
    """
    return BINANCE_ERROR_MESSAGES.get(
        code,
        f"Ошибка Binance [{code}]: {raw_message}",
    )


async def _set_isolated_margin(client, symbol: str) -> None:
    """Set margin type to ISOLATED for the given symbol.

    Silently ignores -4046 ("No need to change margin type") which Binance
    raises when the margin is already ISOLATED. Re-raises on all other codes.
    """
    try:
        await client.futures_change_margin_type(symbol=symbol, marginType="ISOLATED")
    except BinanceAPIException as e:
        if e.code == -4046:
            return  # already isolated — safe to continue
        raise


async def _set_leverage(client, symbol: str, leverage: int) -> None:
    """Set leverage for the given symbol."""
    await client.futures_change_leverage(symbol=symbol, leverage=leverage)


async def _get_symbol_filters(client, symbol: str) -> tuple[float, float]:
    """Return (step_size, tick_size) for the given symbol.

    Checks module-level _exchange_info_cache first; fetches from Binance on cache miss.
    Returns:
        step_size: minimum quantity increment (LOT_SIZE filter)
        tick_size: minimum price increment (PRICE_FILTER filter)
    """
    global _exchange_info_cache

    if symbol not in _exchange_info_cache:
        info = await client.futures_exchange_info()
        for sym_info in info["symbols"]:
            s = sym_info["symbol"]
            step = float(
                next(
                    f["stepSize"]
                    for f in sym_info["filters"]
                    if f["filterType"] == "LOT_SIZE"
                )
            )
            tick = float(
                next(
                    f["tickSize"]
                    for f in sym_info["filters"]
                    if f["filterType"] == "PRICE_FILTER"
                )
            )
            _exchange_info_cache[s] = {"step_size": step, "tick_size": tick}

    cached = _exchange_info_cache[symbol]
    return cached["step_size"], cached["tick_size"]


async def _handle_order_error(
    e: BinanceAPIException,
    signal,
    session_factory,
    bot,
    settings,
) -> None:
    """Handle a Binance API exception during order placement.

    - Maps the error code to a Russian-language message.
    - Marks the signal as 'failed' (for known error codes) or 'error' (unknown).
    - Sends a throttled error alert via send_error_alert().
    """
    code = getattr(e, "code", 0)
    raw_msg = getattr(e, "message", str(e))
    is_known = code in BINANCE_ERROR_MESSAGES
    new_status = "failed" if is_known else "error"

    logger.error(
        f"Binance order error for signal {signal.id}: code={code}, msg={raw_msg}, "
        f"marking signal as '{new_status}'"
    )

    async with session_factory() as session:
        result = await session.execute(select(Signal).where(Signal.id == signal.id))
        sig_row = result.scalar_one_or_none()
        if sig_row is not None:
            sig_row.status = new_status
            sig_row.updated_at = datetime.now(timezone.utc)
            await session.commit()

    error_key = f"order_error_{signal.symbol}"
    message = get_error_message(code, raw_msg)
    await send_error_alert(bot, settings.allowed_chat_id, error_key, message)


async def execute_order(
    signal_id: uuid.UUID,
    session_factory,
    binance_client,
    settings,
    bot,
) -> None:
    """Execute a confirmed signal: place MARKET entry + bracket SL/TP on Binance Futures.

    This is the main order execution coroutine, fired via asyncio.create_task()
    from handle_confirm after signal status is committed as 'confirmed'.

    In dry-run mode (when _bot_state["dry_run"] is True):
    - No Binance API calls are made.
    - An Order row with status='dry_run' is created in DB.
    - A "[DRY RUN]" prefixed message is sent to Telegram.

    Double-tap protection:
    - The signal is loaded with SELECT FOR UPDATE, filtered to status='confirmed'.
    - If None (already executing/processed), returns immediately.
    """
    # Lazy import to avoid circular import: commands -> executor -> commands
    from bot.telegram.handlers.commands import _bot_state

    # -------------------------------------------------------------------------
    # Step 0: Dry-run guard
    # -------------------------------------------------------------------------
    if _bot_state.get("dry_run"):
        logger.info(f"DRY RUN: skipping Binance API for signal {signal_id}")
        async with session_factory() as session:
            # Load signal for direction/symbol info
            result = await session.execute(
                select(Signal).where(Signal.id == signal_id)
            )
            sig = result.scalar_one_or_none()
            if sig is None:
                logger.warning(f"DRY RUN: signal {signal_id} not found in DB")
                return

            entry_side = "BUY" if sig.direction == "long" else "SELL"
            direction_label = "LONG" if sig.direction == "long" else "SHORT"

            order = Order(
                signal_id=signal_id,
                status="dry_run",
                side=entry_side,
                environment=settings.binance_env,
            )
            session.add(order)
            sig.status = "dry_run"
            sig.updated_at = datetime.now(timezone.utc)
            await session.commit()

        dry_msg = (
            f"[DRY RUN] Ордер НЕ размещён — режим тестирования.\n"
            f"{sig.symbol} {direction_label}\n"
            f"Entry: ${sig.entry_price:.4f}"
        )
        await bot.send_message(settings.allowed_chat_id, dry_msg)
        return

    # -------------------------------------------------------------------------
    # Step 1: Load signal (double-tap protection via SELECT FOR UPDATE)
    # -------------------------------------------------------------------------
    async with session_factory() as session:
        result = await session.execute(
            select(Signal)
            .where(Signal.id == signal_id, Signal.status == "confirmed")
            .with_for_update()
        )
        signal = result.scalar_one_or_none()

        if signal is None:
            # Already executing or processed — return silently
            logger.debug(
                f"execute_order: signal {signal_id} not in 'confirmed' state — returning early"
            )
            return

        # Step 2: Mark as executing
        signal.status = "executing"
        signal.updated_at = datetime.now(timezone.utc)
        await session.commit()

    # Keep a local snapshot of signal fields for later use
    signal_id_val = signal.id
    symbol = signal.symbol
    direction = signal.direction
    entry_side = "BUY" if direction == "long" else "SELL"
    bracket_side = "SELL" if direction == "long" else "BUY"

    try:
        # -------------------------------------------------------------------------
        # Step 3: Load RiskSettings
        # -------------------------------------------------------------------------
        async with session_factory() as session:
            risk_result = await session.execute(select(RiskSettings).limit(1))
            risk = risk_result.scalar_one_or_none()
            if risk is None:
                logger.error("execute_order: no RiskSettings row found in DB")
                await send_error_alert(
                    bot,
                    settings.allowed_chat_id,
                    f"order_error_{symbol}_risk",
                    "Ошибка: настройки риска не найдены в базе данных",
                )
                return

        # -------------------------------------------------------------------------
        # Step 4: Load DailyStats + open Position count
        # -------------------------------------------------------------------------
        async with session_factory() as session:
            today = datetime.now(timezone.utc).date()
            stats_result = await session.execute(
                select(DailyStats).where(
                    DailyStats.date == today
                )
            )
            stats = stats_result.scalar_one_or_none()

            count_result = await session.execute(
                select(func.count()).select_from(Position).where(
                    Position.status == "open",
                    Position.is_dry_run == False,
                )
            )
            open_count = count_result.scalar() or 0

        # -------------------------------------------------------------------------
        # Step 5: Circuit breakers
        # -------------------------------------------------------------------------
        if stats is not None:
            total_pnl = stats.total_pnl or 0.0
            starting_balance = stats.starting_balance or 1.0
            if check_daily_loss(total_pnl, starting_balance, risk.daily_loss_limit_pct):
                logger.warning(
                    f"execute_order: daily loss limit reached — halting order for signal {signal_id}"
                )
                await send_error_alert(
                    bot,
                    settings.allowed_chat_id,
                    "daily_loss_halt",
                    "Дневной лимит убытков достигнут — торговля приостановлена",
                )
                async with session_factory() as session:
                    result = await session.execute(select(Signal).where(Signal.id == signal_id_val))
                    sig = result.scalar_one_or_none()
                    if sig:
                        sig.status = "failed"
                        sig.updated_at = datetime.now(timezone.utc)
                        await session.commit()
                return

        if not check_max_positions(open_count, risk.max_open_positions):
            logger.warning(
                f"execute_order: max open positions reached ({open_count}/{risk.max_open_positions}) "
                f"— halting order for signal {signal_id}"
            )
            await send_error_alert(
                bot,
                settings.allowed_chat_id,
                "max_positions_halt",
                f"Достигнут максимум открытых позиций ({open_count}/{risk.max_open_positions})",
            )
            async with session_factory() as session:
                result = await session.execute(select(Signal).where(Signal.id == signal_id_val))
                sig = result.scalar_one_or_none()
                if sig:
                    sig.status = "failed"
                    sig.updated_at = datetime.now(timezone.utc)
                    await session.commit()
            return

        # -------------------------------------------------------------------------
        # Step 6: Fetch account balance
        # -------------------------------------------------------------------------
        account = await binance_client.futures_account()
        balance = float(account["totalWalletBalance"])

        # -------------------------------------------------------------------------
        # Step 7: Set isolated margin (ignore -4046 "already set")
        # -------------------------------------------------------------------------
        await _set_isolated_margin(binance_client, symbol)

        # -------------------------------------------------------------------------
        # Step 8: Set leverage
        # -------------------------------------------------------------------------
        await _set_leverage(binance_client, symbol, risk.leverage)

        # -------------------------------------------------------------------------
        # Step 9: Get symbol precision filters
        # -------------------------------------------------------------------------
        step_size, tick_size = await _get_symbol_filters(binance_client, symbol)

        # -------------------------------------------------------------------------
        # Step 10: Get current market price (not signal.entry_price — may be stale)
        # -------------------------------------------------------------------------
        ticker = await binance_client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker["price"])

        # -------------------------------------------------------------------------
        # Step 11: Calculate position size + MIN_NOTIONAL check
        # -------------------------------------------------------------------------
        async with session_factory() as session:
            result = await session.execute(select(Signal).where(Signal.id == signal_id_val))
            signal = result.scalar_one_or_none()

        pos_size = calculate_position_size(
            balance=balance,
            current_stake_pct=risk.current_stake_pct,
            entry_price=current_price,
            stop_loss=signal.stop_loss,
            leverage=risk.leverage,
        )

        if not check_min_notional(pos_size["position_usdt"], min_notional=5.0):
            logger.warning(
                f"execute_order: position size ${pos_size['position_usdt']:.2f} is below "
                f"MIN_NOTIONAL $5.00 for {symbol}"
            )
            await send_error_alert(
                bot,
                settings.allowed_chat_id,
                f"order_error_{symbol}_notional",
                BINANCE_ERROR_MESSAGES[-4164],
            )
            async with session_factory() as session:
                result = await session.execute(select(Signal).where(Signal.id == signal_id_val))
                sig = result.scalar_one_or_none()
                if sig:
                    sig.status = "failed"
                    sig.updated_at = datetime.now(timezone.utc)
                    await session.commit()
            return

        # -------------------------------------------------------------------------
        # Step 12: Round quantity and SL/TP prices to symbol precision
        # -------------------------------------------------------------------------
        quantity = round_step_size(pos_size["contracts"], step_size)
        sl_price = round_step_size(signal.stop_loss, tick_size)
        tp_price = round_step_size(signal.take_profit, tick_size)

        # -------------------------------------------------------------------------
        # Step 13: Place MARKET entry order
        # -------------------------------------------------------------------------
        try:
            entry_order = await binance_client.futures_create_order(
                symbol=symbol,
                side=entry_side,
                type="MARKET",
                quantity=quantity,
            )
        except BinanceAPIException as e:
            await _handle_order_error(e, signal, session_factory, bot, settings)
            return

        fill_price = float(entry_order["avgPrice"])
        filled_qty = float(entry_order["executedQty"])
        binance_order_id = str(entry_order["orderId"])

        # Log a warning on partial fills (market orders on Futures testnet always fill fully,
        # but check just in case for production pairs with low liquidity)
        orig_qty = float(entry_order.get("origQty", filled_qty))
        if filled_qty != orig_qty:
            logger.warning(
                f"Partial fill: signal={signal_id}, requested={orig_qty}, filled={filled_qty}"
            )

        # -------------------------------------------------------------------------
        # Step 14: Validate fill_price vs SL (check -2021 scenario)
        # -------------------------------------------------------------------------
        # For a long: SL is below entry; if fill_price <= sl_price, SL already triggered.
        # For a short: SL is above entry; if fill_price >= sl_price, SL already triggered.
        sl_would_trigger = (
            (direction == "long" and fill_price <= float(sl_price))
            or (direction == "short" and fill_price >= float(sl_price))
        )

        if sl_would_trigger:
            logger.error(
                f"execute_order: fill_price={fill_price} already past SL={sl_price} for "
                f"{symbol} {direction}. Closing position immediately."
            )
            # Close entry via reduceOnly MARKET
            try:
                await binance_client.futures_create_order(
                    symbol=symbol,
                    side=bracket_side,
                    type="MARKET",
                    quantity=filled_qty,
                    reduceOnly=True,
                )
            except BinanceAPIException as close_err:
                logger.error(f"Failed to close position after SL check: {close_err}")

            # Create a synthetic BinanceAPIException with code -2021
            class _SyntheticException:
                code = -2021
                message = "Fill price already past stop loss"

            await _handle_order_error(
                _SyntheticException(),  # type: ignore[arg-type]
                signal,
                session_factory,
                bot,
                settings,
            )
            return

        # -------------------------------------------------------------------------
        # Step 15: Create Order row (filled entry)
        # -------------------------------------------------------------------------
        async with session_factory() as session:
            order = Order(
                signal_id=signal.id,
                binance_order_id=binance_order_id,
                status="filled",
                side=entry_side,
                quantity=filled_qty,
                executed_price=fill_price,
                filled_at=datetime.now(timezone.utc),
                environment=settings.binance_env,
            )
            session.add(order)
            await session.flush()  # populate order.id before using it in Position

            # -------------------------------------------------------------------------
            # Step 16: Create Position row
            # -------------------------------------------------------------------------
            position = Position(
                symbol=symbol,
                side=direction,  # 'long' or 'short'
                entry_price=fill_price,
                quantity=filled_qty,
                status="open",
                environment=settings.binance_env,
                order_id=order.id,
                is_dry_run=False,
            )
            session.add(position)
            await session.commit()
            # Refresh to get generated IDs
            await session.refresh(order)
            await session.refresh(position)
            order_id = order.id
            position_id = position.id

        # -------------------------------------------------------------------------
        # Step 17: Place STOP_MARKET + TAKE_PROFIT_MARKET bracket orders
        # -------------------------------------------------------------------------
        try:
            sl_order = await binance_client.futures_create_order(
                symbol=symbol,
                side=bracket_side,
                type="STOP_MARKET",
                stopPrice=sl_price,
                closePosition=True,
                timeInForce="GTE_GTC",
                workingType="MARK_PRICE",
                priceProtect=True,
            )
            tp_order = await binance_client.futures_create_order(
                symbol=symbol,
                side=bracket_side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=tp_price,
                closePosition=True,
                timeInForce="GTE_GTC",
                workingType="MARK_PRICE",
                priceProtect=True,
            )
        except BinanceAPIException as e:
            logger.error(
                f"execute_order: bracket order failed for {symbol}: {e}. Closing position."
            )
            # Close the entry — cannot leave an unprotected position open
            try:
                await binance_client.futures_create_order(
                    symbol=symbol,
                    side=bracket_side,
                    type="MARKET",
                    quantity=filled_qty,
                    reduceOnly=True,
                )
            except BinanceAPIException as close_err:
                logger.error(f"Failed to close position after bracket error: {close_err}")

            await _handle_order_error(e, signal, session_factory, bot, settings)
            return

        # -------------------------------------------------------------------------
        # Step 18: Update Position with SL/TP order IDs; mark signal 'filled'
        # -------------------------------------------------------------------------
        async with session_factory() as session:
            pos_result = await session.execute(
                select(Position).where(Position.id == position_id)
            )
            pos = pos_result.scalar_one_or_none()
            if pos:
                pos.sl_order_id = str(sl_order["orderId"])
                pos.tp_order_id = str(tp_order["orderId"])

            sig_result = await session.execute(
                select(Signal).where(Signal.id == signal_id_val)
            )
            sig = sig_result.scalar_one_or_none()
            if sig:
                sig.status = "filled"
                sig.updated_at = datetime.now(timezone.utc)

            await session.commit()

        # -------------------------------------------------------------------------
        # Step 19: Send Telegram confirmation
        # -------------------------------------------------------------------------
        direction_label = "LONG" if direction == "long" else "SHORT"
        msg = (
            f"✅ Ордер открыт: {symbol} {direction_label}\n\n"
            f"Цена входа:    ${fill_price:.4f}\n"
            f"Размер:        {filled_qty} контрактов\n"
            f"Stop Loss:     ${sl_price:.4f}\n"
            f"Take Profit:   ${tp_price:.4f}"
        )
        await bot.send_message(settings.allowed_chat_id, msg)
        logger.info(
            f"Order executed: {symbol} {direction_label} | fill={fill_price} | qty={filled_qty}"
        )

    except Exception as e:
        logger.exception(
            f"execute_order: unexpected error for signal {signal_id}: {e}"
        )
        # Mark signal as 'error' and alert
        async with session_factory() as session:
            result = await session.execute(select(Signal).where(Signal.id == signal_id_val))
            sig = result.scalar_one_or_none()
            if sig:
                sig.status = "error"
                sig.updated_at = datetime.now(timezone.utc)
                await session.commit()
        await send_error_alert(
            bot,
            settings.allowed_chat_id,
            f"order_error_{symbol}_unexpected",
            f"Неожиданная ошибка при размещении ордера для {symbol}: {e}",
        )
