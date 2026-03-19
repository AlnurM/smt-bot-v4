"""Tests for bot.telegram.middleware — AllowedChatMiddleware (TG-01).
All tests are RED until bot/telegram/middleware.py is implemented.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

middleware_mod = pytest.importorskip("bot.telegram.middleware")
AllowedChatMiddleware = middleware_mod.AllowedChatMiddleware


@pytest.mark.asyncio
async def test_allowed_chat_passes():
    """Middleware calls handler for matching chat_id."""
    middleware = AllowedChatMiddleware(allowed_chat_id=123456789)

    message = MagicMock()
    message.chat.id = 123456789

    event = MagicMock()
    event.message = message
    event.callback_query = None

    handler = AsyncMock(return_value="response")
    data = {}

    result = await middleware(handler, event, data)
    handler.assert_called_once_with(event, data)
    assert result == "response"


@pytest.mark.asyncio
async def test_blocked_chat_silently_ignored():
    """Middleware returns None for non-matching chat_id without calling handler."""
    middleware = AllowedChatMiddleware(allowed_chat_id=123456789)

    message = MagicMock()
    message.chat.id = 999999999  # different chat_id

    event = MagicMock()
    event.message = message
    event.callback_query = None

    handler = AsyncMock(return_value="response")
    data = {}

    result = await middleware(handler, event, data)
    handler.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_callback_query_chat_id_checked():
    """Middleware extracts chat_id from callback_query.message.chat.id for allowed chat."""
    middleware = AllowedChatMiddleware(allowed_chat_id=123456789)

    cb_message = MagicMock()
    cb_message.chat.id = 123456789

    callback_query = MagicMock()
    callback_query.message = cb_message

    event = MagicMock()
    event.message = None
    event.callback_query = callback_query

    handler = AsyncMock(return_value="cb_response")
    data = {}

    result = await middleware(handler, event, data)
    handler.assert_called_once_with(event, data)
    assert result == "cb_response"
