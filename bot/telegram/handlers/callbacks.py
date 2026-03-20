"""Inline keyboard callback handlers — Confirm, Reject, Pine Script.

Each handler:
  1. Calls callback.answer() FIRST (within Telegram's 60s deadline).
  2. Opens its own session (never shared between handlers).
  3. Uses SELECT ... FOR UPDATE for atomic idempotency on confirm/reject.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru import logger
from sqlalchemy import select

from bot.db.models import Signal, StrategyCriteria
from bot.order.executor import execute_order
from bot.telegram.callbacks import SignalAction, LoosenCriteria

router = Router()


class RejectReasonFSM(StatesGroup):
    waiting_reason = State()


# ---------------------------------------------------------------------------
# handle_confirm (TG-03)
# ---------------------------------------------------------------------------

@router.callback_query(SignalAction.filter(F.action == "confirm"))
async def handle_confirm(
    callback: CallbackQuery,
    callback_data: SignalAction,
    **kwargs,
) -> None:
    """Mark signal as confirmed — idempotent via SELECT FOR UPDATE.

    Double-tap protection: if signal is not found or not pending, removes buttons only.
    """
    # MUST answer first — Telegram's 60-second callback deadline
    await callback.answer()

    session_factory = kwargs.get("session_factory")
    async with session_factory() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.id == uuid.UUID(callback_data.signal_id),
                Signal.status == "pending",
            )
            .with_for_update()
        )
        signal = result.scalar_one_or_none()

        if signal is None:
            # Already confirmed / rejected / expired — double-tap safety: remove buttons
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as exc:
                logger.debug(f"Double-tap confirm: could not remove markup: {exc}")
            return

        signal.status = "confirmed"
        signal.updated_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(f"Signal {callback_data.signal_id} confirmed by user")

    # Fire order execution as a non-blocking task.
    # binance_client, settings, bot, session_factory are injected via dp workflow_data.
    asyncio.create_task(
        execute_order(
            signal_id=signal.id,
            session_factory=kwargs.get("session_factory"),
            binance_client=kwargs.get("binance_client"),
            settings=kwargs.get("settings"),
            bot=kwargs.get("bot"),
        )
    )

    try:
        confirmed_caption = (
            (signal.caption or callback.message.caption or "")
            + "\n\n✅ Подтверждено — размещение ордера..."
        )
        await callback.message.edit_caption(
            caption=confirmed_caption,
            reply_markup=None,
        )
    except Exception as exc:
        logger.debug(f"Could not edit confirmed signal caption: {exc}")


# ---------------------------------------------------------------------------
# handle_reject (TG-04)
# ---------------------------------------------------------------------------

@router.callback_query(SignalAction.filter(F.action == "reject"))
async def handle_reject(
    callback: CallbackQuery,
    callback_data: SignalAction,
    state: FSMContext,
    **kwargs,
) -> None:
    """Mark signal as rejected — idempotent via SELECT FOR UPDATE.

    After rejecting, asks for optional free-text reason (TG-04).
    Trader can type a reason or just ignore — next command clears the FSM state.
    """
    await callback.answer()

    session_factory = kwargs.get("session_factory")
    async with session_factory() as session:
        result = await session.execute(
            select(Signal)
            .where(
                Signal.id == uuid.UUID(callback_data.signal_id),
                Signal.status == "pending",
            )
            .with_for_update()
        )
        signal = result.scalar_one_or_none()

        if signal is None:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception as exc:
                logger.debug(f"Double-tap reject: could not remove markup: {exc}")
            return

        signal.status = "rejected"
        signal.updated_at = datetime.now(timezone.utc)
        await session.commit()

    logger.info(f"Signal {callback_data.signal_id} rejected by user")

    try:
        rejected_caption = (
            (signal.caption or callback.message.caption or "")
            + "\n\n❌ Отклонено"
        )
        await callback.message.edit_caption(
            caption=rejected_caption,
            reply_markup=None,
        )
    except Exception as exc:
        logger.debug(f"Could not edit rejected signal caption: {exc}")

    # Ask for optional reason — store signal_id in FSM state
    await state.set_state(RejectReasonFSM.waiting_reason)
    await state.update_data(rejected_signal_id=str(callback_data.signal_id))
    await callback.message.answer(
        "Причина отклонения? (необязательно — отправьте текст или /skip)"
    )


@router.message(RejectReasonFSM.waiting_reason, F.text == "/skip")
async def skip_reject_reason(message: Message, state: FSMContext) -> None:
    """Trader skips providing a reason."""
    await state.clear()
    await message.answer("Ок, без причины.")


@router.message(RejectReasonFSM.waiting_reason, F.text)
async def capture_reject_reason(message: Message, state: FSMContext, **kwargs) -> None:
    """Capture free-text rejection reason and store in DB."""
    data = await state.get_data()
    signal_id = data.get("rejected_signal_id")
    reason_text = message.text.strip()

    if not signal_id or not reason_text:
        await state.clear()
        return

    session_factory = kwargs.get("session_factory")
    async with session_factory() as session:
        result = await session.execute(
            select(Signal).where(Signal.id == uuid.UUID(signal_id))
        )
        signal = result.scalar_one_or_none()
        if signal:
            signal.rejection_reason = reason_text
            signal.updated_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(f"Signal {signal_id} rejection reason: {reason_text}")

    await state.clear()
    await message.answer(f"✅ Причина сохранена: {reason_text}")


# ---------------------------------------------------------------------------
# handle_pine (PINE-02)
# ---------------------------------------------------------------------------

@router.callback_query(SignalAction.filter(F.action == "pine"))
async def handle_pine(
    callback: CallbackQuery,
    callback_data: SignalAction,
    **kwargs,
) -> None:
    """Generate and send Pine Script v5 for the signal (PINE-01, PINE-02, PINE-03)."""
    await callback.answer()

    session_factory = kwargs.get("session_factory")
    async with session_factory() as session:
        result = await session.execute(
            select(Signal).where(Signal.id == uuid.UUID(callback_data.signal_id))
        )
        signal = result.scalar_one_or_none()

    if signal is None:
        await callback.message.answer("Сигнал не найден.")
        return

    try:
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
        await callback.message.answer_document(
            document=BufferedInputFile(pine_text.encode("utf-8"), filename=filename),
            caption=f"Pine Script — {signal.symbol} {signal.timeframe}",
        )
    except Exception as exc:
        logger.exception(f"Pine Script generation failed for signal {signal.id}: {exc}")
        await callback.message.answer("Ошибка генерации Pine Script. Проверьте логи.")


# ---------------------------------------------------------------------------
# handle_loosen_criteria (SKIP-04)
# ---------------------------------------------------------------------------

# Loosen adjustment rules: for each field, compute the new loosened value
_LOOSEN_RULES: dict[str, callable] = {
    "min_total_return_pct": lambda v: max(v * 0.75, 50.0),   # reduce by 25%, floor 50%
    "max_drawdown_pct":     lambda v: v * 1.25,               # more negative allowed (e.g. -12 -> -15)
    "min_win_rate_pct":     lambda v: max(v - 5.0, 30.0),     # reduce by 5 points, floor 30%
    "min_profit_factor":    lambda v: max(v - 0.2, 1.0),      # reduce by 0.2, floor 1.0
    "min_avg_rr":           lambda v: max(v - 0.5, 1.0),      # reduce by 0.5, floor 1.0
    "min_trades":           lambda v: max(int(v) - 10, 5),    # reduce by 10, floor 5
}

_CRITERION_LABELS_RU = {
    "min_total_return_pct": "Мин. доходность",
    "max_drawdown_pct": "Макс. просадка",
    "min_win_rate_pct": "Win Rate",
    "min_profit_factor": "Profit Factor",
    "min_avg_rr": "R/R Ratio",
    "min_trades": "Мин. сделок",
}


@router.callback_query(LoosenCriteria.filter())
async def handle_loosen_criteria(
    callback: CallbackQuery,
    callback_data: LoosenCriteria,
    **kwargs,
) -> None:
    """Loosen a single strategy criterion and confirm to user.

    Triggered by inline buttons on the consecutive-skip alert (SKIP-04).
    Uses the same StrategyCriteria update pattern as /criteria command.
    """
    await callback.answer()

    if callback_data.field == "noop":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Продолжаем ожидание. Критерии не изменены.")
        return

    field = callback_data.field
    if field not in _LOOSEN_RULES:
        await callback.message.answer(f"⚠️ Неизвестный критерий: {field}")
        return

    session_factory = kwargs.get("session_factory")
    async with session_factory() as session:
        result = await session.execute(select(StrategyCriteria).limit(1))
        criteria = result.scalars().first()

        if criteria is None:
            await callback.message.answer("⚠️ Таблица критериев пуста.")
            return

        current_value = getattr(criteria, field)
        new_value = _LOOSEN_RULES[field](current_value)
        setattr(criteria, field, new_value)
        criteria.updated_at = datetime.now(timezone.utc)
        await session.commit()

    label = _CRITERION_LABELS_RU.get(field, field)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"✅ {label} ослаблен: {current_value} → {new_value:.2f}\n"
        f"Изменение вступит в силу в следующем цикле сканирования."
    )
    logger.info(f"Criterion loosened via button: {field} {current_value} -> {new_value}")
