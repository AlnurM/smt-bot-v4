"""Callback data factories for inline keyboard buttons."""
from aiogram.filters.callback_data import CallbackData


class SignalAction(CallbackData, prefix="sig"):
    """Callback data for signal confirmation/rejection inline buttons.

    Produces callback_data strings like: sig:550e8400-...-0000-...:confirm
    Total length is well within the 64-byte Telegram callback_data limit.
    """

    signal_id: str   # UUID as string (36 chars)
    action: str      # "confirm" | "reject" | "pine"


class LoosenCriteria(CallbackData, prefix="lc"):
    """Callback data for 'loosen criterion' buttons on the consecutive-skip alert.

    field: name of the StrategyCriteria column to loosen (e.g. "min_total_return_pct")
    Produced by send_skipped_coins_alert, handled by handle_loosen_criteria.

    Prefix "lc" + field name stays well within the 64-byte limit.
    """

    field: str   # StrategyCriteria column name, e.g. "min_total_return_pct"
