"""All query and control command handlers for the Telegram bot.

Handlers: /start, /status, /signals, /positions, /history, /strategies,
          /skipped, /scan, /chart, /pause, /resume, /help
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import sqlalchemy as sa
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from sqlalchemy import select, func

from bot.db.models import (
    Signal, Position, Trade, Strategy, SkippedCoin, RiskSettings, DailyStats,
)

router = Router()

# Module-level state dict — shared between handlers and dispatch (Plan 02)
# Plan 02 imports _bot_state to check ["paused"] before sending signal messages
# Phase 5 adds "dry_run" key — read by bot/order/executor.py to skip Binance API calls
_bot_state: dict = {"paused": False, "dry_run": False}

# Signal status emoji map
_STATUS_EMOJI = {
    "confirmed": "✅",
    "rejected": "❌",
    "expired": "⏱",
    "pending": "⏳",
}

# Trade close reason emoji map
_CLOSE_EMOJI = {
    "tp": "✅",
    "sl": "❌",
    "manual": "🖐",
    "expired": "⏱",
}


# ---------------------------------------------------------------------------
# /start (TG-05)
# ---------------------------------------------------------------------------

@router.message(Command("start"))
async def cmd_start(message: Message, session_factory, binance_client, settings, **kwargs) -> None:
    """Show system status: balance, open positions, current stake."""
    try:
        async with session_factory() as session:
            # Get current stake from risk settings
            risk_result = await session.execute(select(RiskSettings).limit(1))
            risk = risk_result.scalars().first()
            stake = risk.current_stake_pct if risk else 3.0

            # Count open positions
            pos_result = await session.execute(
                select(func.count()).select_from(Position).where(Position.status == "open")
            )
            open_count = pos_result.scalar() or 0

        # Get balance from Binance
        account = await binance_client.futures_account()
        balance = float(account.get("totalWalletBalance", 0))

        text = (
            f"Бот активен\n\n"
            f"💰 Баланс: ${balance:.2f}\n"
            f"📊 Открытых позиций: {open_count}\n"
            f"💪 Текущая ставка: {stake}%"
        )
    except Exception as e:
        logger.exception(f"/start error: {e}")
        text = "⚠️ Ошибка получения статуса. Проверьте логи."

    await message.answer(text)


# ---------------------------------------------------------------------------
# /status (TG-06)
# ---------------------------------------------------------------------------

@router.message(Command("status"))
async def cmd_status(message: Message, session_factory, binance_client, settings, **kwargs) -> None:
    """Show balance, open positions, today's PnL, win streak, current stake."""
    try:
        today = datetime.now(timezone.utc).date()

        async with session_factory() as session:
            risk_result = await session.execute(select(RiskSettings).limit(1))
            risk = risk_result.scalars().first()
            stake = risk.current_stake_pct if risk else 3.0
            streak = risk.win_streak_current if risk else 0

            pos_result = await session.execute(
                select(func.count()).select_from(Position).where(Position.status == "open")
            )
            open_count = pos_result.scalar() or 0

            # Today's daily stats
            stats_result = await session.execute(
                select(DailyStats).where(
                    sa.cast(DailyStats.date, sa.Date) == today
                )
            )
            stats = stats_result.scalars().first()
            daily_pnl = stats.total_pnl if stats else 0.0

        account = await binance_client.futures_account()
        balance = float(account.get("totalWalletBalance", 0))

        pnl_sign = "+" if daily_pnl >= 0 else ""
        text = (
            f"📈 Статус бота\n\n"
            f"💰 Баланс: ${balance:.2f}\n"
            f"📊 Открытых позиций: {open_count}\n"
            f"📅 PnL за сегодня: {pnl_sign}${daily_pnl:.2f}\n"
            f"🔥 Серия побед: {streak}\n"
            f"💪 Текущая ставка: {stake}%"
        )
    except Exception as e:
        logger.exception(f"/status error: {e}")
        text = "⚠️ Ошибка получения статуса. Проверьте логи."

    await message.answer(text)


# ---------------------------------------------------------------------------
# /signals (TG-09)
# ---------------------------------------------------------------------------

@router.message(Command("signals"))
async def cmd_signals(message: Message, session_factory, **kwargs) -> None:
    """Show last 10 signals with status emojis."""
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Signal).order_by(Signal.created_at.desc()).limit(10)
            )
            signals = result.scalars().all()

        if not signals:
            await message.answer("Нет сигналов. История появится после первого сигнала.")
            return

        lines = ["📡 Последние сигналы:\n"]
        for sig in signals:
            emoji = _STATUS_EMOJI.get(sig.status, "❓")
            direction = "LONG" if sig.direction == "long" else "SHORT"
            lines.append(
                f"{emoji} {sig.symbol} {direction} | {sig.status} | "
                f"${sig.entry_price:.4f} | RR {sig.rr_ratio:.1f}"
            )

        await message.answer("\n".join(lines))
    except Exception as e:
        logger.exception(f"/signals error: {e}")
        await message.answer("⚠️ Ошибка получения сигналов.")


# ---------------------------------------------------------------------------
# /positions (TG-10)
# ---------------------------------------------------------------------------

@router.message(Command("positions"))
async def cmd_positions(message: Message, session_factory, **kwargs) -> None:
    """Show all open positions."""
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Position).where(Position.status == "open")
            )
            positions = result.scalars().all()

        if not positions:
            await message.answer("Нет открытых позиций.")
            return

        lines = ["📊 Открытые позиции:\n"]
        for pos in positions:
            pnl = pos.unrealized_pnl or 0.0
            pnl_str = f"{pnl:+.2f}"
            lines.append(
                f"{pos.symbol} {pos.side.upper()} @ ${pos.entry_price:.4f}  |  PnL: {pnl_str}"
            )

        await message.answer("\n".join(lines))
    except Exception as e:
        logger.exception(f"/positions error: {e}")
        await message.answer("⚠️ Ошибка получения позиций.")


# ---------------------------------------------------------------------------
# /history (TG-11)
# ---------------------------------------------------------------------------

@router.message(Command("history"))
async def cmd_history(message: Message, session_factory, **kwargs) -> None:
    """Show last 20 closed trades."""
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Trade).order_by(Trade.closed_at.desc()).limit(20)
            )
            trades = result.scalars().all()

        if not trades:
            await message.answer("История сделок пуста.")
            return

        lines = ["📜 История сделок:\n"]
        for trade in trades:
            emoji = _CLOSE_EMOJI.get(trade.close_reason or "", "❓")
            pnl = trade.realized_pnl or 0.0
            pnl_str = f"{pnl:+.2f}"
            lines.append(f"{emoji} {trade.symbol} | PnL: {pnl_str}")

        await message.answer("\n".join(lines))
    except Exception as e:
        logger.exception(f"/history error: {e}")
        await message.answer("⚠️ Ошибка получения истории.")


# ---------------------------------------------------------------------------
# /strategies (TG-12)
# ---------------------------------------------------------------------------

@router.message(Command("strategies"))
async def cmd_strategies(message: Message, session_factory, **kwargs) -> None:
    """Show all active strategies."""
    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active == True).order_by(
                    Strategy.created_at.desc()
                )
            )
            strategies = result.scalars().all()

        if not strategies:
            await message.answer("Нет активных стратегий.")
            return

        lines = ["🧠 Активные стратегии:\n"]
        for strat in strategies:
            score = strat.backtest_score or 0.0
            review = (
                strat.next_review_at.strftime("%Y-%m-%d")
                if strat.next_review_at else "N/A"
            )
            lines.append(
                f"{strat.symbol} | score: {score:.2f} | review: {review}"
            )

        await message.answer("\n".join(lines))
    except Exception as e:
        logger.exception(f"/strategies error: {e}")
        await message.answer("⚠️ Ошибка получения стратегий.")


# ---------------------------------------------------------------------------
# /skipped (TG-13)
# ---------------------------------------------------------------------------

@router.message(Command("skipped"))
async def cmd_skipped(message: Message, session_factory, **kwargs) -> None:
    """Show skipped coins with compact list or drill-down.

    Usage:
      /skipped           — compact list, last 24h (symbol, failed count, time)
      /skipped week      — compact list, last 7 days
      /skipped XRPUSDT   — drill-down for specific coin (backtest + criteria)
    """
    try:
        parts = (message.text or "").split()
        filter_symbol: str | None = None
        hours_back = 24
        drill_down = False

        if len(parts) >= 2:
            arg = parts[1].strip()
            if arg.lower() == "week":
                hours_back = 24 * 7
            elif arg.endswith("h") and arg[:-1].isdigit():
                hours_back = int(arg[:-1])
            elif arg.endswith("d") and arg[:-1].isdigit():
                hours_back = int(arg[:-1]) * 24
            else:
                # Symbol drill-down
                filter_symbol = arg.upper()
                hours_back = 0
                drill_down = True

        async with session_factory() as session:
            query = select(SkippedCoin)
            if filter_symbol:
                query = query.where(SkippedCoin.symbol == filter_symbol)
            elif hours_back > 0:
                cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
                query = query.where(SkippedCoin.created_at >= cutoff)
            query = query.order_by(SkippedCoin.created_at.desc()).limit(30)

            result = await session.execute(query)
            coins = result.scalars().all()

        if not coins:
            label = filter_symbol or (f"за {hours_back}ч" if hours_back <= 24 else "за 7 дн.")
            await message.answer(f"Нет пропущенных монет ({label}).")
            return

        if drill_down and filter_symbol:
            # Full drill-down: symbol history with backtest details
            label = f"История: {filter_symbol}"
            lines = [f"⛔ {label}\n"]
            for coin in coins:
                ts = coin.created_at.strftime("%m-%d %H:%M")
                criteria_str = ", ".join(coin.failed_criteria or []) or "N/A"
                lines.append(f"🕐 {ts} | Провалено: {criteria_str}")

                # Backtest results if available
                br = coin.backtest_results or {}
                if br:
                    ret = br.get("total_return_pct")
                    dd = br.get("max_drawdown_pct")
                    wr = br.get("win_rate")
                    pf = br.get("profit_factor")
                    trades = br.get("total_trades")
                    parts_br = []
                    if ret is not None:
                        parts_br.append(f"Доходность: {ret:+.1f}%")
                    if dd is not None:
                        parts_br.append(f"Просадка: {dd:.1f}%")
                    if wr is not None:
                        wr_pct = wr * 100 if wr <= 1.0 else wr
                        parts_br.append(f"WR: {wr_pct:.0f}%")
                    if pf is not None:
                        parts_br.append(f"PF: {pf:.2f}")
                    if trades is not None:
                        parts_br.append(f"Сделок: {trades}")
                    if parts_br:
                        lines.append("  " + " | ".join(parts_br))
                lines.append("")
        else:
            # Compact list: one line per coin
            label = filter_symbol or (f"за {hours_back}ч" if hours_back <= 24 else "за 7 дн.")
            lines = [f"⛔ Пропущенные монеты ({label}):\n"]
            for coin in coins:
                ts = coin.created_at.strftime("%m-%d %H:%M")
                failed_count = len(coin.failed_criteria or [])
                criteria_str = ", ".join(coin.failed_criteria or []) or "N/A"
                lines.append(
                    f"{coin.symbol} | {failed_count} крит. | {ts}\n"
                    f"  ↳ {criteria_str}"
                )

        await message.answer("\n".join(lines))
    except Exception as e:
        logger.exception(f"/skipped error: {e}")
        await message.answer("⚠️ Ошибка получения пропущенных монет.")


# ---------------------------------------------------------------------------
# /scan (TG-14)
# ---------------------------------------------------------------------------

@router.message(Command("scan"))
async def cmd_scan(message: Message, session_factory, binance_client, settings, **kwargs) -> None:
    """Trigger an immediate strategy scan (non-blocking)."""
    await message.answer("Запуск сканирования рынка...")
    try:
        from bot.strategy.manager import run_strategy_scan
        bot = kwargs.get("bot")
        scheduler = kwargs.get("scheduler")
        asyncio.create_task(
            run_strategy_scan(session_factory, binance_client, settings, bot, scheduler)
        )
    except Exception as e:
        logger.exception(f"/scan task creation error: {e}")


# ---------------------------------------------------------------------------
# /chart (TG-15)
# ---------------------------------------------------------------------------

@router.message(Command("chart"))
async def cmd_chart(message: Message, session_factory, **kwargs) -> None:
    """Return Pine Script v5 .txt file for the most recent signal of the given symbol.

    Usage: /chart SOLUSDT
    """
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("Использование: /chart SYMBOL\nПример: /chart SOLUSDT")
        return

    symbol = parts[1].strip().upper()

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(Signal)
                .where(Signal.symbol == symbol)
                .order_by(Signal.created_at.desc())
                .limit(1)
            )
            signal = result.scalars().first()

        if signal is None:
            await message.answer(f"Нет сигналов для {symbol}.")
            return

        from bot.reporting.pine_script import generate_pine_script
        from aiogram.types import BufferedInputFile

        pine_text = generate_pine_script(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            direction=signal.direction,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            rr_ratio=signal.rr_ratio,
            signal_strength=signal.signal_strength,
            zones_data=signal.zones_data,
        )
        filename = f"pine_script_{signal.symbol}_{signal.timeframe}.txt"
        await message.answer_document(
            document=BufferedInputFile(pine_text.encode("utf-8"), filename=filename),
            caption=f"Pine Script — {signal.symbol} {signal.timeframe}",
        )

    except Exception as exc:
        logger.exception(f"/chart error for {symbol}: {exc}")
        await message.answer(f"Ошибка получения Pine Script для {symbol}.")


# ---------------------------------------------------------------------------
# /pause (TG-17a)
# ---------------------------------------------------------------------------

@router.message(Command("pause"))
async def cmd_pause(message: Message, **kwargs) -> None:
    """Pause signal generation."""
    _bot_state["paused"] = True
    logger.info("Bot paused via /pause command")
    await message.answer("⏸ Генерация сигналов приостановлена.")


# ---------------------------------------------------------------------------
# /resume (TG-17b)
# ---------------------------------------------------------------------------

@router.message(Command("resume"))
async def cmd_resume(message: Message, **kwargs) -> None:
    """Resume signal generation."""
    _bot_state["paused"] = False
    logger.info("Bot resumed via /resume command")
    await message.answer("▶️ Генерация сигналов возобновлена.")


# ---------------------------------------------------------------------------
# /dryrun (ORD-DRY) — toggle dry-run mode at runtime without restart
# ---------------------------------------------------------------------------

@router.message(Command("dryrun"))
async def cmd_dryrun(message: Message, **kwargs) -> None:
    """Toggle dry-run mode: /dryrun on or /dryrun off.

    Without argument: shows current state.
    In dry-run mode, execute_order() skips all Binance API calls and creates
    an Order row with status='dry_run'.
    """
    parts = (message.text or "").split()
    if len(parts) < 2 or parts[1].lower() not in ("on", "off"):
        status = "ВКЛ" if _bot_state.get("dry_run") else "ВЫКЛ"
        await message.answer(
            f"Dry-run режим: {status}\n"
            f"Использование: /dryrun on — включить, /dryrun off — выключить"
        )
        return
    _bot_state["dry_run"] = (parts[1].lower() == "on")
    status = "ВКЛ" if _bot_state["dry_run"] else "ВЫКЛ"
    logger.info(f"Dry-run mode set to {_bot_state['dry_run']} via /dryrun command")
    await message.answer(f"Dry-run режим: {status}")


# ---------------------------------------------------------------------------
# /help (TG-18)
# ---------------------------------------------------------------------------

@router.message(Command("help"))
async def cmd_help(message: Message, **kwargs) -> None:
    """Show all available commands."""
    text = (
        "📚 Команды бота:\n\n"
        "📊 Информация:\n"
        "/start — Статус системы (баланс, позиции, ставка)\n"
        "/status — Подробный статус (PnL, серия побед)\n"
        "/signals — Последние 10 сигналов\n"
        "/positions — Открытые позиции\n"
        "/history — История закрытых сделок\n"
        "/strategies — Активные стратегии\n"
        "/skipped [24h|7d|SYMBOL] — Пропущенные монеты\n"
        "/chart SYMBOL — Pine Script для монеты\n\n"
        "⚙️ Управление:\n"
        "/scan — Запустить сканирование рынка\n"
        "/pause — Приостановить генерацию сигналов\n"
        "/resume — Возобновить генерацию сигналов\n"
        "/dryrun [on|off] — Режим тестирования без реальных ордеров\n"
        "/help — Эта справка"
    )
    await message.answer(text)
