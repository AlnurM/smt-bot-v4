"""Notification helpers — error throttling, daily loss warning, skipped coins alert.

TG-20: check_and_warn_daily_loss — fires at 80% of daily loss limit
TG-21: send_error_alert — throttled to once per 15 min per error key
TG-22: send_skipped_coins_alert — fires when consecutive empty cycles >= threshold
"""
from datetime import datetime, timezone, timedelta

from loguru import logger

# In-memory throttle state — persists for the life of the process
_last_alert: dict[str, datetime] = {}

_THROTTLE_MINUTES = 15


async def send_error_alert(bot, chat_id: int, error_key: str, message: str) -> None:
    """Send an error alert to the allowed chat, throttled to once per 15 min per key.

    If the same error_key was sent within the last 15 minutes, the message is silently
    dropped. This prevents alert storms for repeated errors.
    """
    now = datetime.now(timezone.utc)
    last_sent = _last_alert.get(error_key)

    if last_sent is not None:
        elapsed = (now - last_sent).total_seconds() / 60
        if elapsed < _THROTTLE_MINUTES:
            logger.debug(
                f"Alert throttled: key={error_key}, elapsed={elapsed:.1f}min < {_THROTTLE_MINUTES}min"
            )
            return

    _last_alert[error_key] = now
    try:
        await bot.send_message(chat_id, f"⚠️ {message}")
    except Exception as e:
        logger.error(f"Failed to send error alert (key={error_key}): {e}")


async def check_and_warn_daily_loss(
    bot,
    chat_id: int,
    total_pnl: float,
    starting_balance: float,
    daily_loss_limit_pct: float,
) -> None:
    """Send a warning when daily loss reaches 80% of the configured limit.

    Args:
        bot: aiogram Bot instance
        chat_id: Telegram chat ID to send to
        total_pnl: Today's total PnL (negative means loss)
        starting_balance: Balance at start of trading day
        daily_loss_limit_pct: Max allowed daily loss as % of starting balance
    """
    if starting_balance <= 0 or total_pnl >= 0:
        return

    loss_pct = abs(total_pnl) / starting_balance * 100
    limit_reached_pct = loss_pct / daily_loss_limit_pct * 100

    if limit_reached_pct >= 80:
        loss_abs = abs(total_pnl)
        limit_abs = starting_balance * daily_loss_limit_pct / 100
        msg = (
            f"🚨 ВНИМАНИЕ: Дневной убыток {limit_reached_pct:.0f}% от лимита "
            f"(${loss_abs:.2f}/${limit_abs:.2f}). "
            f"Следующий убыток может остановить торговлю."
        )
        await send_error_alert(bot, chat_id, "daily_loss_80pct", msg)


async def send_skipped_coins_alert(
    bot,
    chat_id: int,
    consecutive_count: int,
    threshold: int,
) -> None:
    """Send an alert when all coins have been skipped for consecutive scan cycles.

    Args:
        bot: aiogram Bot instance
        chat_id: Telegram chat ID to send to
        consecutive_count: Number of consecutive empty scan cycles
        threshold: Minimum count to trigger the alert
    """
    if consecutive_count < threshold:
        return

    msg = (
        f"⚠️ {consecutive_count} циклов сканирования без новых стратегий. "
        f"Попробуйте ослабить критерии отбора (/criteria)."
    )
    await send_error_alert(bot, chat_id, "all_coins_skipped", msg)
