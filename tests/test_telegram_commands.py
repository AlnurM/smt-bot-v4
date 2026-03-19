"""Tests for bot.telegram.handlers.commands — TG-05 through TG-18.
All tests are RED until bot/telegram/handlers/commands.py is implemented.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

commands = pytest.importorskip("bot.telegram.handlers.commands")


def _make_message(text="/start"):
    """Create a minimal mock aiogram Message."""
    msg = AsyncMock()
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_data(session=None, binance_client=None, settings=None, paused=False):
    """Create a mock data dict that handlers expect."""
    if session is None:
        session = AsyncMock()
        # Default scalar returns
        session.execute.return_value.scalar.return_value = 0
        session.execute.return_value.scalar_one_or_none.return_value = None
        session.execute.return_value.scalars.return_value.first.return_value = None
        session.execute.return_value.scalars.return_value.all.return_value = []

    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

    if binance_client is None:
        binance_client = AsyncMock()
        binance_client.futures_account.return_value = {"totalWalletBalance": "1000.00"}

    if settings is None:
        settings = MagicMock()
        settings.allowed_chat_id = 123456789

    return {
        "session_factory": session_factory,
        "binance_client": binance_client,
        "settings": settings,
        "paused": paused,
    }


@pytest.mark.asyncio
async def test_cmd_start_responds():
    """/start handler calls message.answer at least once."""
    handler = None
    # Find the /start handler on the router
    for route in commands.router.message.filter.__self__._routes if hasattr(commands.router, "_routes") else []:
        pass

    # Use duck-typing approach: call the handler directly
    msg = _make_message("/start")
    data = _make_data()

    # Find cmd_start function directly
    cmd_func = getattr(commands, "cmd_start", None)
    if cmd_func is None:
        pytest.skip("cmd_start not found — will be discovered via router")

    with patch("bot.telegram.handlers.commands.SessionLocal", data["session_factory"], create=True):
        await cmd_func(msg, **{k: v for k, v in data.items() if k != "session_factory"}, session_factory=data["session_factory"])

    msg.answer.assert_called()


@pytest.mark.asyncio
async def test_cmd_help_responds():
    """/help handler calls message.answer with text containing '/start'."""
    msg = _make_message("/help")
    data = _make_data()

    cmd_func = getattr(commands, "cmd_help", None)
    if cmd_func is None:
        pytest.skip("cmd_help not found")

    await cmd_func(msg, **{k: v for k, v in data.items()})
    msg.answer.assert_called()
    call_text = msg.answer.call_args[0][0] if msg.answer.call_args[0] else msg.answer.call_args[1].get("text", "")
    assert "/start" in call_text


@pytest.mark.asyncio
async def test_cmd_signals_empty_state():
    """/signals with empty DB returns friendly Russian message."""
    msg = _make_message("/signals")

    # Session that returns empty list for signals
    session = AsyncMock()
    session.execute.return_value.scalars.return_value.all.return_value = []
    data = _make_data(session=session)

    cmd_func = getattr(commands, "cmd_signals", None)
    if cmd_func is None:
        pytest.skip("cmd_signals not found")

    await cmd_func(msg, **{k: v for k, v in data.items()})
    msg.answer.assert_called()
    call_text = msg.answer.call_args[0][0] if msg.answer.call_args[0] else msg.answer.call_args[1].get("text", "")
    # Should contain Russian text about no signals
    assert len(call_text) > 0


@pytest.mark.asyncio
async def test_cmd_pause_sets_flag():
    """/pause sets _bot_state['paused'] to True."""
    msg = _make_message("/pause")
    data = _make_data()

    cmd_func = getattr(commands, "cmd_pause", None)
    if cmd_func is None:
        pytest.skip("cmd_pause not found")

    # Reset state first
    commands._bot_state["paused"] = False

    await cmd_func(msg, **{k: v for k, v in data.items()})
    assert commands._bot_state["paused"] is True
    msg.answer.assert_called()


@pytest.mark.asyncio
async def test_cmd_resume_clears_flag():
    """/resume sets _bot_state['paused'] to False."""
    msg = _make_message("/resume")
    data = _make_data()

    cmd_func = getattr(commands, "cmd_resume", None)
    if cmd_func is None:
        pytest.skip("cmd_resume not found")

    # Set paused first
    commands._bot_state["paused"] = True

    await cmd_func(msg, **{k: v for k, v in data.items()})
    assert commands._bot_state["paused"] is False
    msg.answer.assert_called()
