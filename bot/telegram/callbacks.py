"""Callback data factories for inline keyboard buttons."""
from aiogram.filters.callback_data import CallbackData


class SignalAction(CallbackData, prefix="sig"):
    """Callback data for signal confirmation/rejection inline buttons.

    Produces callback_data strings like: sig:550e8400-...-0000-...:confirm
    Total length is well within the 64-byte Telegram callback_data limit.
    """

    signal_id: str   # UUID as string (36 chars)
    action: str      # "confirm" | "reject" | "pine"
