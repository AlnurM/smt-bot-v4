"""Tests for bot.telegram.dispatch — send_signal_message, schedule_signal_expiry, expire_signal_job.

RED state: all tests are stubs that fail because production module doesn't exist yet.
pytest.importorskip at module level skips cleanly when dispatch.py is absent.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import uuid

dispatch = pytest.importorskip("bot.telegram.dispatch")
send_signal_message = dispatch.send_signal_message
schedule_signal_expiry = dispatch.schedule_signal_expiry
expire_signal_job = dispatch.expire_signal_job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_signal():
    """Minimal signal dict matching generate_signal() output shape."""
    return {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "direction": "long",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": 53000.0,
        "rr_ratio": 3.0,
        "signal_strength": "Strong",
        "reasoning": "Multiple confluence: OB, FVG, structure break confirmed",
        "zones": {"order_blocks": [], "fvgs": [], "structure_levels": []},
    }


@pytest.fixture
def sample_position_size():
    """Minimal position_size dict matching calculate_position_size() output."""
    return {
        "risk_usdt": 3.0,
        "sl_distance": 1000.0,
        "position_usdt": 300.0,
        "contracts": 0.006,
        "stake_pct": 3.0,
    }


@pytest.fixture
def chart_bytes():
    """Fake PNG bytes for chart."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


# ---------------------------------------------------------------------------
# send_signal_message tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_signal_message_calls_send_photo(sample_signal, sample_position_size, chart_bytes):
    """send_signal_message calls bot.send_photo exactly once."""
    mock_bot = AsyncMock()
    mock_message = MagicMock()
    mock_message.message_id = 42
    mock_bot.send_photo.return_value = mock_message

    result = await send_signal_message(
        bot=mock_bot,
        chat_id=123456789,
        signal=sample_signal,
        chart_bytes=chart_bytes,
        position_size=sample_position_size,
        is_min_notional=False,
    )

    mock_bot.send_photo.assert_called_once()
    assert result == 42


@pytest.mark.asyncio
async def test_caption_truncated_at_1020_chars(sample_position_size, chart_bytes):
    """Caption is truncated to 1020 chars if over that limit."""
    long_signal = {
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "direction": "long",
        "entry_price": 50000.0,
        "stop_loss": 49000.0,
        "take_profit": 53000.0,
        "rr_ratio": 3.0,
        "signal_strength": "Strong",
        "reasoning": "X" * 500,  # very long reasoning — forces truncation
        "zones": {"order_blocks": [], "fvgs": [], "structure_levels": []},
    }
    mock_bot = AsyncMock()
    mock_message = MagicMock()
    mock_message.message_id = 1
    mock_bot.send_photo.return_value = mock_message

    await send_signal_message(
        bot=mock_bot,
        chat_id=123456789,
        signal=long_signal,
        chart_bytes=chart_bytes,
        position_size=sample_position_size,
        is_min_notional=False,
    )

    # Extract caption from the call args
    call_kwargs = mock_bot.send_photo.call_args
    caption = call_kwargs.kwargs.get("caption") or call_kwargs[1].get("caption") or call_kwargs[0][2]
    assert len(caption) <= 1024, f"Caption too long: {len(caption)}"


@pytest.mark.asyncio
async def test_normal_signal_has_3_buttons(sample_signal, sample_position_size, chart_bytes):
    """Normal signal (is_min_notional=False) produces keyboard with 3 buttons total."""
    mock_bot = AsyncMock()
    mock_message = MagicMock()
    mock_message.message_id = 10
    mock_bot.send_photo.return_value = mock_message

    await send_signal_message(
        bot=mock_bot,
        chat_id=123456789,
        signal=sample_signal,
        chart_bytes=chart_bytes,
        position_size=sample_position_size,
        is_min_notional=False,
    )

    call_kwargs = mock_bot.send_photo.call_args
    reply_markup = call_kwargs.kwargs.get("reply_markup") or call_kwargs[1].get("reply_markup")
    assert reply_markup is not None

    # Count total buttons across all rows
    all_buttons = [btn for row in reply_markup.inline_keyboard for btn in row]
    assert len(all_buttons) == 3, f"Expected 3 buttons, got {len(all_buttons)}"


@pytest.mark.asyncio
async def test_min_notional_signal_has_2_buttons(sample_signal, sample_position_size, chart_bytes):
    """MIN_NOTIONAL signal (is_min_notional=True) produces keyboard with only 2 buttons (no Confirm)."""
    mock_bot = AsyncMock()
    mock_message = MagicMock()
    mock_message.message_id = 11
    mock_bot.send_photo.return_value = mock_message

    await send_signal_message(
        bot=mock_bot,
        chat_id=123456789,
        signal=sample_signal,
        chart_bytes=chart_bytes,
        position_size=sample_position_size,
        is_min_notional=True,
    )

    call_kwargs = mock_bot.send_photo.call_args
    reply_markup = call_kwargs.kwargs.get("reply_markup") or call_kwargs[1].get("reply_markup")
    assert reply_markup is not None

    all_buttons = [btn for row in reply_markup.inline_keyboard for btn in row]
    assert len(all_buttons) == 2, f"Expected 2 buttons, got {len(all_buttons)}"


# ---------------------------------------------------------------------------
# schedule_signal_expiry tests
# ---------------------------------------------------------------------------

def test_signal_expiry_job_scheduled(sample_signal, sample_position_size):
    """schedule_signal_expiry calls scheduler.add_job with id containing signal_id."""
    mock_scheduler = MagicMock()
    mock_bot = AsyncMock()
    mock_session_factory = MagicMock()
    signal_id = str(uuid.uuid4())

    schedule_signal_expiry(
        scheduler=mock_scheduler,
        bot=mock_bot,
        chat_id=123456789,
        message_id=42,
        signal_id=signal_id,
        session_factory=mock_session_factory,
        timeout_minutes=15,
    )

    mock_scheduler.add_job.assert_called_once()
    call_kwargs = mock_scheduler.add_job.call_args
    job_id = call_kwargs.kwargs.get("id") or call_kwargs[1].get("id")
    assert signal_id in job_id, f"Expected signal_id in job id, got: {job_id}"


# ---------------------------------------------------------------------------
# expire_signal_job tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_expire_signal_marks_expired():
    """expire_signal_job sets signal.status='expired' when signal is pending."""
    mock_signal = MagicMock()
    mock_signal.status = "pending"
    mock_signal.caption = "original caption"

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_signal
    mock_session.execute.return_value = mock_result

    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    mock_bot = AsyncMock()
    mock_bot.edit_message_caption = AsyncMock()

    signal_id = str(uuid.uuid4())

    await expire_signal_job(
        bot=mock_bot,
        chat_id=123456789,
        message_id=42,
        signal_id=signal_id,
        session_factory=mock_session_factory,
    )

    assert mock_signal.status == "expired"
    mock_session.commit.assert_called_once()
