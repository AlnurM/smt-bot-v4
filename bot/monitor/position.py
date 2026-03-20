"""Position Monitor — APScheduler polling job (every 60 seconds).

Detects SL/TP fills on open positions, cancels surviving bracket,
creates Trade record, updates win streak, aggregates DailyStats,
sends Telegram close notification.

Skips: is_dry_run=True positions, positions without sl_order_id/tp_order_id.
"""
from __future__ import annotations

from datetime import datetime, timezone

from binance.exceptions import BinanceAPIException
from loguru import logger
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from bot.db.models import DailyStats, Position, RiskSettings, Trade
from bot.risk.manager import get_next_stake, get_stake_after_loss


async def monitor_positions(
    session_factory,
    binance_client,
    settings,
    bot,
) -> None:
    """Called every 60 seconds by APScheduler IntervalTrigger.

    Loads all open, non-dry-run positions with bracket order IDs and checks
    their SL/TP order statuses on Binance. Detects fills, closes positions,
    updates win streak + DailyStats, sends Telegram notifications.

    Processes positions sequentially (not concurrently) to prevent win streak
    race conditions when multiple positions close in the same cycle.
    """
    async with session_factory() as session:
        result = await session.execute(
            select(Position).where(
                Position.status == "open",
                Position.is_dry_run == False,  # noqa: E712
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
                    binance_client,
                    session_factory,
                    bot,
                    settings,
                    position,
                    close_reason="sl",
                    filled_order_id=position.sl_order_id,
                    surviving_order_id=position.tp_order_id,
                    exit_price=exit_price,
                )
            elif tp_order["status"] == "FILLED":
                exit_price = float(tp_order["avgPrice"])
                await _handle_position_close(
                    binance_client,
                    session_factory,
                    bot,
                    settings,
                    position,
                    close_reason="tp",
                    filled_order_id=position.tp_order_id,
                    surviving_order_id=position.sl_order_id,
                    exit_price=exit_price,
                )
            else:
                # Neither order filled — update unrealized PnL for /positions display
                await _update_unrealized_pnl(binance_client, session_factory, position)

        except BinanceAPIException as e:
            if e.code == -2013:
                # ORDER_DOES_NOT_EXIST — testnet wipe or manual cancellation
                logger.warning(
                    f"Monitor: stale order for {position.symbol} (id={position.id}) — "
                    f"ORDER_DOES_NOT_EXIST (-2013), marking as orphaned"
                )
                async with session_factory() as session:
                    pos_db = await session.get(Position, position.id)
                    if pos_db is not None:
                        pos_db.status = "orphaned"
                        pos_db.updated_at = datetime.now(timezone.utc)
                        await session.commit()
            else:
                logger.error(
                    f"Monitor: Binance API error for {position.symbol} (id={position.id}): "
                    f"code={e.code}, msg={e}"
                )
        except Exception as e:
            logger.error(
                f"Monitor: unexpected error for {position.symbol} (id={position.id}): {e}"
            )


async def _handle_position_close(
    binance_client,
    session_factory,
    bot,
    settings,
    position,
    close_reason: str,
    filled_order_id: str,
    surviving_order_id: str,
    exit_price: float,
) -> None:
    """Handle a detected SL or TP fill.

    Sequential steps:
      1. Cancel surviving bracket order (ignore -2011 already-cancelled)
      2. Fetch realized PnL from futures_account_trades (includes fees)
      3. DB: create Trade, close Position, upsert DailyStats, update RiskSettings
      4. Send Telegram close notification
    """
    # -------------------------------------------------------------------------
    # Step 1: Cancel surviving bracket order
    # -------------------------------------------------------------------------
    try:
        await binance_client.futures_cancel_order(
            symbol=position.symbol,
            orderId=int(surviving_order_id),
        )
    except BinanceAPIException as e:
        if e.code == -2011:
            # Already cancelled or expired — safe to ignore
            logger.debug(
                f"Monitor: surviving bracket order {surviving_order_id} already cancelled "
                f"for {position.symbol} (-2011 ignored)"
            )
        else:
            logger.warning(
                f"Monitor: unexpected error cancelling surviving bracket "
                f"{surviving_order_id} for {position.symbol}: code={e.code}, msg={e}"
            )

    # -------------------------------------------------------------------------
    # Step 2: Fetch realized PnL from account trades
    # -------------------------------------------------------------------------
    trades = await binance_client.futures_account_trades(
        symbol=position.symbol,
        limit=10,
    )
    realized_pnl = sum(
        float(t["realizedPnl"])
        for t in trades
        if t["orderId"] == int(filled_order_id)
    )

    # -------------------------------------------------------------------------
    # Step 3: DB writes — all in one session
    # -------------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    today = now.date()

    async with session_factory() as session:
        # 3a. Create Trade record
        trade = Trade(
            position_id=position.id,
            symbol=position.symbol,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            realized_pnl=realized_pnl,
            close_reason=close_reason,
            opened_at=position.created_at,
            closed_at=now,
        )
        session.add(trade)

        # 3b. Close Position
        pos_db = await session.get(Position, position.id)
        if pos_db is not None:
            pos_db.status = "closed"
            pos_db.updated_at = now

        # 3c. Upsert DailyStats (atomic ON CONFLICT DO UPDATE)
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
            },
        )
        await session.execute(stmt)

        # Compute win_rate: re-query after upsert
        stats_result = await session.execute(
            select(DailyStats).where(DailyStats.date == today)
        )
        stats_row = stats_result.scalar_one_or_none()
        if stats_row is not None and stats_row.trade_count > 0:
            stats_row.win_rate = stats_row.win_count / stats_row.trade_count

        # 3d. Update RiskSettings (single row)
        risk_result = await session.execute(select(RiskSettings).limit(1))
        risk = risk_result.scalar_one_or_none()
        if risk is not None:
            if close_reason == "tp":
                risk.win_streak_current += 1
                risk.current_stake_pct = get_next_stake(
                    risk.win_streak_current,
                    risk.progressive_stakes,
                    risk.base_stake_pct,
                    risk.wins_to_increase,
                )
            else:
                # SL hit — reset streak
                risk.win_streak_current = 0
                risk.current_stake_pct = get_stake_after_loss(risk.base_stake_pct)
            risk.updated_at = now

        await session.commit()

    # -------------------------------------------------------------------------
    # Step 4: Send Telegram close notification
    # -------------------------------------------------------------------------
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
    logger.info(
        f"Position closed: {position.symbol} {position.side} | "
        f"reason={close_reason} | exit={exit_price:.4f} | pnl={pnl_sign}{realized_pnl:.2f}"
    )


async def _update_unrealized_pnl(
    binance_client,
    session_factory,
    position,
) -> None:
    """Update unrealized PnL for an open position that hasn't closed yet.

    Called each monitor cycle when neither SL nor TP has filled.
    Uses futures_position_information() to get current mark price and PnL.

    If positionAmt == 0: the position may have closed without bot detecting it
    (manual close, liquidation). Logs a warning but does NOT change status —
    the next monitor cycle will detect the filled order status.
    """
    pos_info_list = await binance_client.futures_position_information(
        symbol=position.symbol,
    )

    # Find the matching symbol entry
    pi = next((p for p in pos_info_list if p["symbol"] == position.symbol), None)
    if pi is None:
        logger.warning(
            f"Monitor: no position info found for {position.symbol} in "
            f"futures_position_information() response"
        )
        return

    position_amt = float(pi.get("positionAmt", "0"))
    if position_amt == 0:
        logger.warning(
            f"Monitor: {position.symbol} shows positionAmt=0 from Binance "
            f"but DB status is still 'open'. Will detect close on next SL/TP order check."
        )
        return

    # Update unrealized PnL and current price
    async with session_factory() as session:
        pos_db = await session.get(Position, position.id)
        if pos_db is not None:
            pos_db.unrealized_pnl = float(pi["unRealizedProfit"])
            if "markPrice" in pi:
                pos_db.current_price = float(pi["markPrice"])
            pos_db.updated_at = datetime.now(timezone.utc)
            await session.commit()
