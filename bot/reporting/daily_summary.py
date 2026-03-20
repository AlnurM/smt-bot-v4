"""Daily summary notification — sent at 21:00 UTC+5 (TG-19)."""
import asyncio
from datetime import datetime, timezone, timedelta, date

import sqlalchemy as sa
from loguru import logger
from sqlalchemy import select, func

from bot.db.models import DailyStats, Trade, Strategy, RiskSettings


async def send_daily_summary(
    session_factory,
    binance_client,
    settings,
    bot,
) -> None:
    """Compose and send the daily summary message.

    Queries:
    1. DailyStats row for today (UTC date)
    2. Today's trades from Trade table for best/worst
    3. Active strategy count + strategies due for review (next_review_at <= now+7d)
    4. Current balance from Binance futures_account()
    5. Current stake from RiskSettings

    Sends to settings.allowed_chat_id.
    All exceptions are caught — never propagates to APScheduler.
    """
    try:
        today_utc: date = datetime.now(timezone.utc).date()
        now_utc = datetime.now(timezone.utc)

        async with session_factory() as session:
            # 1. DailyStats for today
            stats_result = await session.execute(
                select(DailyStats).where(
                    sa.cast(DailyStats.date, sa.Date) == today_utc
                )
            )
            stats = stats_result.scalars().first()

            # 2. Best and worst trade today
            trades_result = await session.execute(
                select(Trade).where(
                    sa.cast(Trade.closed_at, sa.Date) == today_utc
                )
            )
            today_trades = trades_result.scalars().all()

            # 3. Active strategies + due for review count
            active_result = await session.execute(
                select(func.count()).select_from(Strategy).where(
                    Strategy.is_active == True
                )
            )
            active_count = active_result.scalar() or 0

            review_cutoff = now_utc + timedelta(days=7)
            due_result = await session.execute(
                select(func.count()).select_from(Strategy).where(
                    Strategy.is_active == True,
                    Strategy.next_review_at <= review_cutoff,
                )
            )
            due_count = due_result.scalar() or 0

            # 4. Current stake from RiskSettings
            risk_result = await session.execute(select(RiskSettings).limit(1))
            risk = risk_result.scalars().first()
            stake_pct = risk.current_stake_pct if risk else 3.0

        # 5. Current balance from Binance
        try:
            account = await binance_client.futures_account()
            balance = float(account.get("totalWalletBalance", 0))
        except Exception as exc:
            logger.warning(f"Daily summary: could not fetch balance: {exc}")
            balance = 0.0

        # Compose message
        total_pnl = stats.total_pnl if stats else 0.0
        trade_count = stats.trade_count if stats else 0
        win_rate = stats.win_rate if stats else None

        if trade_count == 0:
            text = (
                f"📅 Итоги дня\n\n"
                f"Нет сделок за сегодня.\n"
                f"💰 Баланс: ${balance:.2f}\n"
                f"💪 Ставка: {stake_pct:.0f}%"
            )
        else:
            pnl_sign = "+" if total_pnl >= 0 else ""
            win_rate_str = f"{win_rate:.0f}%" if win_rate is not None else "N/A"

            # Best / worst trade
            best_trade = max(today_trades, key=lambda t: t.realized_pnl or 0.0, default=None)
            worst_trade = min(today_trades, key=lambda t: t.realized_pnl or 0.0, default=None)

            best_str = (
                f"{best_trade.symbol} {pnl_sign_fmt(best_trade.realized_pnl or 0)}"
                if best_trade else "N/A"
            )
            worst_str = (
                f"{worst_trade.symbol} {pnl_sign_fmt(worst_trade.realized_pnl or 0)}"
                if worst_trade else "N/A"
            )

            text = (
                f"📅 Итоги дня\n\n"
                f"💰 PnL: {pnl_sign}${total_pnl:.2f}\n"
                f"📊 Сделок: {trade_count}\n"
                f"🎯 Win Rate: {win_rate_str}\n"
                f"💪 Ставка: {stake_pct:.0f}%\n"
                f"💰 Баланс: ${balance:.2f}\n\n"
                f"🏆 Лучшая: {best_str}\n"
                f"💀 Худшая: {worst_str}\n\n"
                f"🧠 Стратегий: {active_count} активных, {due_count} на обновлении (7 дн.)"
            )

        await bot.send_message(settings.allowed_chat_id, text)
        logger.info(f"Daily summary sent: trades={trade_count}, pnl=${total_pnl:.2f}")

    except Exception as exc:
        logger.exception(f"Daily summary failed: {exc}")
        try:
            await bot.send_message(
                settings.allowed_chat_id,
                "⚠️ Ошибка формирования ежедневного отчёта. Проверьте логи."
            )
        except Exception:
            pass


def pnl_sign_fmt(pnl: float) -> str:
    """Format PnL with sign prefix: +$12.50 or -$3.10."""
    sign = "+" if pnl >= 0 else "-"
    return f"{sign}${abs(pnl):.2f}"
