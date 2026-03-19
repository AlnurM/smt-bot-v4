"""AllowedChatMiddleware — single-user security layer (TG-01)."""
from typing import Callable, Awaitable, Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class AllowedChatMiddleware(BaseMiddleware):
    """Blocks all updates from chat_ids other than the configured allowed_chat_id.

    Silently drops non-allowed updates — no response is sent to the blocked user.
    Handles both Message and CallbackQuery update types.
    """

    def __init__(self, allowed_chat_id: int) -> None:
        self.allowed_chat_id = allowed_chat_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[Any]],
        event: TelegramObject,
        data: dict,
    ) -> Any:
        chat_id: int | None = None
        if hasattr(event, "message") and event.message:
            chat_id = event.message.chat.id
        elif hasattr(event, "callback_query") and event.callback_query:
            chat_id = event.callback_query.message.chat.id

        if chat_id != self.allowed_chat_id:
            return  # silently drop — TG-01

        return await handler(event, data)
