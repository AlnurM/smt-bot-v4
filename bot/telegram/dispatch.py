"""Signal dispatch module — sends photo+caption+keyboard to Telegram and schedules expiry.

Exported functions:
  send_signal_message()     — sends photo with caption and inline keyboard; returns message_id
  schedule_signal_expiry()  — registers APScheduler DateTrigger job to expire signal
  expire_signal_job()       — async job called by scheduler on signal timeout
"""
from datetime import datetime, timezone, timedelta

from aiogram import Bot
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from apscheduler.triggers.date import DateTrigger
from loguru import logger
from sqlalchemy import select

from bot.db.models import Signal
from bot.telegram.callbacks import SignalAction
from bot.telegram.handlers.commands import _bot_state


# ---------------------------------------------------------------------------
# Caption formatter (private)
# ---------------------------------------------------------------------------

def _format_signal_caption(signal: dict, pos: dict, is_min_notional: bool) -> str:
    """Build the Telegram caption for a signal photo message.

    Args:
        signal:          generate_signal() return dict
        pos:             position_size dict (must include 'stake_pct' key)
        is_min_notional: if True, append MIN_NOTIONAL warning and omit Confirm button hint

    Returns:
        Caption string, max 1020+3 chars (truncated with '...' if over limit).
    """
    direction = signal["direction"]
    direction_emoji = "🟢" if direction == "long" else "🔴"
    direction_label = "LONG" if direction == "long" else "SHORT"

    entry = signal["entry_price"]
    sl = signal["stop_loss"]
    tp = signal["take_profit"]
    rr = signal["rr_ratio"]
    symbol = signal["symbol"]
    timeframe = signal["timeframe"]
    strength = signal.get("signal_strength", "")
    reasoning = signal.get("reasoning") or ""

    stake_pct = pos.get("stake_pct", 0)
    risk_usdt = pos.get("risk_usdt", 0)
    contracts = pos.get("contracts", 0)
    position_usdt = pos.get("position_usdt", 0)

    sl_pct = abs(entry - sl) / entry * 100 if entry else 0
    tp_pct = abs(tp - entry) / entry * 100 if entry else 0

    caption = (
        f"{direction_emoji} СИГНАЛ: {direction_label}  |  {symbol}  |  {timeframe}\n\n"
        f"📌 Вход:         ${entry:.4f}  (рыночный)\n"
        f"🛑 Stop Loss:    ${sl:.4f}  (-{sl_pct:.2f}%)\n"
        f"🎯 Take Profit:  ${tp:.4f}  (+{tp_pct:.2f}%)\n"
        f"⚖️  R/R Ratio:    1 : {rr:.2f}\n"
        f"💰 Ставка:        {stake_pct:.0f}% депозита  (${risk_usdt:.2f} риск)\n"
        f"📊 Размер:        ~{contracts:.2f} контр.  (${position_usdt:.2f} с плечом)\n"
        f"💪 Сила сигнала: {strength}"
    )

    if is_min_notional:
        caption += "\n⚠️ Позиция слишком мала для исполнения (MIN_NOTIONAL)"

    if reasoning:
        caption += f"\n📈 Обоснование:\n  • {reasoning[:200]}"

    if len(caption) > 1020:
        caption = caption[:1020] + "..."

    return caption


# ---------------------------------------------------------------------------
# send_signal_message
# ---------------------------------------------------------------------------

async def send_signal_message(
    bot: Bot,
    chat_id: int,
    signal: dict,
    chart_bytes: bytes,
    position_size: dict,
    is_min_notional: bool = False,
) -> int:
    """Send a signal as a photo+caption+keyboard Telegram message.

    Returns:
        message_id of the sent message, or -1 if bot is paused.
    """
    if _bot_state.get("paused", False):
        logger.info("Signal dispatch skipped — bot is paused")
        return -1

    caption = _format_signal_caption(signal, position_size, is_min_notional)

    # Build signal_id: get from signal dict if present; otherwise use a placeholder
    # (real signal_id from DB is passed by the caller in Phase 5)
    signal_id = signal.get("id") or "00000000-0000-0000-0000-000000000000"

    builder = InlineKeyboardBuilder()

    if not is_min_notional:
        builder.button(
            text="✅ Открыть сделку",
            callback_data=SignalAction(signal_id=str(signal_id), action="confirm"),
        )

    builder.button(
        text="❌ Отклонить",
        callback_data=SignalAction(signal_id=str(signal_id), action="reject"),
    )
    builder.button(
        text="📊 Pine Script",
        callback_data=SignalAction(signal_id=str(signal_id), action="pine"),
    )

    # Row layout: 2 buttons on row 1, 1 button on row 2 for normal; 1+1 for min_notional
    if not is_min_notional:
        builder.adjust(2, 1)
    else:
        builder.adjust(1, 1)

    msg = await bot.send_photo(
        chat_id=chat_id,
        photo=BufferedInputFile(chart_bytes, filename="chart.png"),
        caption=caption,
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )

    return msg.message_id


# ---------------------------------------------------------------------------
# schedule_signal_expiry
# ---------------------------------------------------------------------------

def schedule_signal_expiry(
    scheduler,
    bot: Bot,
    chat_id: int,
    message_id: int,
    signal_id: str,
    session_factory,
    timeout_minutes: int = 15,
) -> None:
    """Register an APScheduler DateTrigger job to expire the signal after timeout.

    The job id is 'expire_{signal_id}' — replace_existing=True prevents duplicates.
    """
    run_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
    scheduler.add_job(
        expire_signal_job,
        trigger=DateTrigger(run_date=run_at),
        args=[bot, chat_id, message_id, signal_id, session_factory],
        id=f"expire_{signal_id}",
        replace_existing=True,
    )
    logger.debug(
        f"Signal {signal_id} expiry scheduled at {run_at.isoformat()} "
        f"(message_id={message_id})"
    )


# ---------------------------------------------------------------------------
# expire_signal_job (async APScheduler job)
# ---------------------------------------------------------------------------

async def expire_signal_job(
    bot: Bot,
    chat_id: int,
    message_id: int,
    signal_id: str,
    session_factory,
) -> None:
    """APScheduler job — marks signal as 'expired' and edits Telegram message.

    - Only acts on signals still in 'pending' status (idempotent).
    - Message edit failure (e.g. message was deleted) is logged as debug — not fatal.
    """
    import uuid as _uuid

    async with session_factory() as session:
        result = await session.execute(
            select(Signal).where(Signal.id == _uuid.UUID(signal_id))
        )
        signal = result.scalar_one_or_none()

        if signal and signal.status == "pending":
            signal.status = "expired"
            signal.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(f"Signal {signal_id} expired (message_id={message_id})")

            # Edit Telegram message to show expiry — may fail if message was deleted
            try:
                expired_caption = (signal.caption or "") + "\n\n⏱ Истёк срок действия"
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=message_id,
                    caption=expired_caption,
                    reply_markup=None,
                )
            except Exception as exc:
                logger.debug(
                    f"Could not edit expired signal message {message_id} — "
                    f"likely deleted: {exc}"
                )
        else:
            logger.debug(
                f"expire_signal_job: signal {signal_id} not found or not pending "
                f"(status={signal.status if signal else 'None'}) — skipping"
            )
