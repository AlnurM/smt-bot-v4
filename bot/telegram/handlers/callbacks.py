"""Inline keyboard callback handlers — Confirm, Reject, Pine Script.

Each handler:
  1. Calls callback.answer() FIRST (within Telegram's 60s deadline).
  2. Opens its own session (never shared between handlers).
  3. Uses SELECT ... FOR UPDATE for atomic idempotency on confirm/reject.
"""
import uuid
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import CallbackQuery
from loguru import logger
from sqlalchemy import select

from bot.db.models import Signal
from bot.telegram.callbacks import SignalAction

router = Router()


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
    **kwargs,
) -> None:
    """Mark signal as rejected — idempotent via SELECT FOR UPDATE."""
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
            # Already handled — remove buttons silently
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


# ---------------------------------------------------------------------------
# handle_pine (TG-15 Phase 6 placeholder)
# ---------------------------------------------------------------------------

@router.callback_query(SignalAction.filter(F.action == "pine"))
async def handle_pine(
    callback: CallbackQuery,
    callback_data: SignalAction,
    **kwargs,
) -> None:
    """Pine Script placeholder — Phase 6 implementation deferred."""
    await callback.answer()
    await callback.message.answer(
        "📊 Pine Script будет доступен в следующем обновлении."
    )
