"""Tests for bot.telegram.notifications — TG-20, TG-21, TG-22.
All tests are RED until bot/telegram/notifications.py is implemented.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

notifications = pytest.importorskip("bot.telegram.notifications")


@pytest.mark.asyncio
async def test_80pct_warning_sent_at_threshold():
    """check_and_warn_daily_loss sends alert when loss_pct/limit >= 80%."""
    bot = AsyncMock()
    chat_id = 123456789

    # Clear the _last_alert cache to ensure fresh state
    notifications._last_alert.clear()

    # total_pnl=-4.0, starting_balance=100, limit=5.0%
    # loss_pct = 4.0, limit_reached_pct = 80% — exactly at threshold
    await notifications.check_and_warn_daily_loss(
        bot=bot,
        chat_id=chat_id,
        total_pnl=-4.0,
        starting_balance=100.0,
        daily_loss_limit_pct=5.0,
    )
    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    assert call_args[0][0] == chat_id


@pytest.mark.asyncio
async def test_80pct_warning_not_sent_below_threshold():
    """check_and_warn_daily_loss does NOT send when loss < 80% of limit."""
    bot = AsyncMock()
    chat_id = 123456789

    notifications._last_alert.clear()

    # loss_pct=3.0, limit=5.0% → limit_reached_pct=60% — below threshold
    await notifications.check_and_warn_daily_loss(
        bot=bot,
        chat_id=chat_id,
        total_pnl=-3.0,
        starting_balance=100.0,
        daily_loss_limit_pct=5.0,
    )
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_error_throttle_suppresses_within_15min():
    """Second send_error_alert call with same error_key within 15 min does NOT send."""
    bot = AsyncMock()
    chat_id = 123456789
    error_key = "test_throttle_key_unique"

    notifications._last_alert.clear()

    # First call — should send
    await notifications.send_error_alert(bot, chat_id, error_key, "First error")
    assert bot.send_message.call_count == 1

    # Second call within window — should NOT send
    await notifications.send_error_alert(bot, chat_id, error_key, "Second error")
    assert bot.send_message.call_count == 1  # still 1


@pytest.mark.asyncio
async def test_error_throttle_sends_after_window():
    """send_error_alert sends again after 15 min gap."""
    bot = AsyncMock()
    chat_id = 123456789
    error_key = "test_window_key_unique"

    notifications._last_alert.clear()

    # Simulate an entry that is 16 minutes old
    past_time = datetime.now(timezone.utc) - timedelta(minutes=16)
    notifications._last_alert[error_key] = past_time

    await notifications.send_error_alert(bot, chat_id, error_key, "After window error")
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_skipped_coins_alert_fires():
    """send_skipped_coins_alert calls bot.send_message when consecutive_count >= threshold."""
    bot = AsyncMock()
    chat_id = 123456789

    notifications._last_alert.clear()

    await notifications.send_skipped_coins_alert(
        bot=bot,
        chat_id=chat_id,
        consecutive_count=3,
        threshold=3,
    )
    bot.send_message.assert_called_once()
    call_args = bot.send_message.call_args
    assert call_args[0][0] == chat_id
