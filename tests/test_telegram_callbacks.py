"""Tests for bot.telegram.handlers.callbacks — Confirm, Reject, Pine Script handlers.

RED state: all tests are stubs that fail because production module doesn't exist yet.
pytest.importorskip at module level skips cleanly when callbacks.py is absent.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import uuid

callbacks = pytest.importorskip("bot.telegram.handlers.callbacks")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pending_signal():
    """Mock Signal ORM object with status='pending'."""
    sig = MagicMock()
    sig.id = uuid.uuid4()
    sig.status = "pending"
    sig.caption = "Signal caption text"
    return sig


@pytest.fixture
def mock_session_factory(pending_signal):
    """Session factory that returns a pending signal on execute."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = pending_signal

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, mock_session


@pytest.fixture
def mock_session_factory_empty():
    """Session factory that returns None (signal not found / not pending)."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, mock_session


def make_callback(signal_id: str, action: str, session_factory):
    """Build a mock CallbackQuery with all required attributes."""
    cb_data = MagicMock()
    cb_data.signal_id = signal_id
    cb_data.action = action

    mock_message = AsyncMock()
    mock_message.caption = "Signal caption"

    callback = AsyncMock()
    callback.answer = AsyncMock()
    callback.message = mock_message
    callback.data = f"sig:{signal_id}:{action}"
    return callback, cb_data


# ---------------------------------------------------------------------------
# handle_confirm tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirm_callback_marks_confirmed(mock_session_factory, pending_signal):
    """Confirm handler sets signal.status='confirmed' and commits."""
    factory, mock_session = mock_session_factory
    signal_id = str(pending_signal.id)
    callback, cb_data = make_callback(signal_id, "confirm", factory)

    await callbacks.handle_confirm(
        callback=callback,
        callback_data=cb_data,
        session_factory=factory,
    )

    assert pending_signal.status == "confirmed"
    mock_session.commit.assert_called_once()
    callback.answer.assert_called_once()


@pytest.mark.asyncio
async def test_double_confirm_noop(mock_session_factory_empty):
    """Double-tap confirm: session returns None, no DB write, buttons removed."""
    factory, mock_session = mock_session_factory_empty
    signal_id = str(uuid.uuid4())
    callback, cb_data = make_callback(signal_id, "confirm", factory)

    await callbacks.handle_confirm(
        callback=callback,
        callback_data=cb_data,
        session_factory=factory,
    )

    # No commit should happen — signal was None
    mock_session.commit.assert_not_called()
    # answer() must still be called (Telegram deadline)
    callback.answer.assert_called_once()


# ---------------------------------------------------------------------------
# handle_reject tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_callback_marks_rejected(mock_session_factory, pending_signal):
    """Reject handler sets signal.status='rejected', commits, and asks for optional reason."""
    factory, mock_session = mock_session_factory
    signal_id = str(pending_signal.id)
    callback, cb_data = make_callback(signal_id, "reject", factory)

    mock_state = AsyncMock()
    mock_state.set_state = AsyncMock()
    mock_state.update_data = AsyncMock()

    await callbacks.handle_reject(
        callback=callback,
        callback_data=cb_data,
        state=mock_state,
        session_factory=factory,
    )

    assert pending_signal.status == "rejected"
    mock_session.commit.assert_called_once()
    callback.answer.assert_called_once()
    # Should ask for optional reason via FSM
    mock_state.set_state.assert_called_once()
    callback.message.answer.assert_called_once()
    reason_prompt = callback.message.answer.call_args[0][0]
    assert "Причина" in reason_prompt or "причина" in reason_prompt


# ---------------------------------------------------------------------------
# handle_pine tests
# ---------------------------------------------------------------------------

@pytest.fixture
def pine_signal():
    """Mock Signal ORM object with all fields required for Pine Script generation."""
    sig = MagicMock()
    sig.id = uuid.uuid4()
    sig.symbol = "SOLUSDT"
    sig.timeframe = "1h"
    sig.direction = "long"
    sig.entry_price = 145.30
    sig.stop_loss = 140.00
    sig.take_profit = 163.20
    sig.rr_ratio = 3.37
    sig.signal_strength = "Strong"
    sig.zones_data = None
    return sig


@pytest.fixture
def mock_session_factory_pine(pine_signal):
    """Session factory that returns a pine_signal on execute."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = pine_signal

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, mock_session


@pytest.mark.asyncio
async def test_pine_callback_sends_document(mock_session_factory_pine, pine_signal):
    """Pine Script handler answers callback and sends a .txt document."""
    factory, _ = mock_session_factory_pine
    signal_id = str(pine_signal.id)
    callback = AsyncMock()
    callback.answer = AsyncMock()
    callback.message = AsyncMock()
    callback.message.answer_document = AsyncMock()
    cb_data = MagicMock()
    cb_data.signal_id = signal_id
    cb_data.action = "pine"

    await callbacks.handle_pine(
        callback=callback,
        callback_data=cb_data,
        session_factory=factory,
    )

    callback.answer.assert_called_once()
    callback.message.answer_document.assert_called_once()
    # Verify filename contains symbol and timeframe
    call_kwargs = callback.message.answer_document.call_args
    caption = call_kwargs[1].get("caption", "") or ""
    assert "SOLUSDT" in caption or "1h" in caption


@pytest.mark.asyncio
async def test_pine_callback_signal_not_found(mock_session_factory_empty):
    """Pine Script handler sends error message when signal not found."""
    factory, _ = mock_session_factory_empty
    signal_id = str(uuid.uuid4())
    callback = AsyncMock()
    callback.answer = AsyncMock()
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    cb_data = MagicMock()
    cb_data.signal_id = signal_id
    cb_data.action = "pine"

    await callbacks.handle_pine(
        callback=callback,
        callback_data=cb_data,
        session_factory=factory,
    )

    callback.answer.assert_called_once()
    callback.message.answer.assert_called_once()
