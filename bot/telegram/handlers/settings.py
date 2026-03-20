"""Settings command handlers: /risk, /criteria, /settings.

Handlers give the trader full runtime control over bot parameters via Telegram.
- /risk    — view/modify risk parameters (RiskSettings table)
- /criteria — view/modify strategy filter criteria (StrategyCriteria table)
- /settings — view/modify general settings (in-memory Settings object)
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from loguru import logger
from sqlalchemy import select, update

from bot.db.models import RiskSettings, StrategyCriteria, Strategy
from bot.risk.manager import update_risk_settings

router = Router()

# ---------------------------------------------------------------------------
# /risk alias table
# Format: alias -> (db_field_name, type, min_val, max_val)
# ---------------------------------------------------------------------------

RISK_ALIASES: dict[str, tuple] = {
    "stake":       ("base_stake_pct",       float, 1.0, 100.0),
    "max_stake":   ("max_stake_pct",         float, 1.0, 100.0),
    "rr":          ("min_rr_ratio",          float, 0.5, 10.0),
    "leverage":    ("leverage",              int,   1,   20),
    "daily_limit": ("daily_loss_limit_pct",  float, 1.0, 50.0),
    "max_pos":     ("max_open_positions",    int,   1,   20),
}

# Risk defaults for /risk reset
_RISK_DEFAULTS: list[tuple[str, object]] = [
    ("base_stake_pct",       3.0),
    ("max_stake_pct",        8.0),
    ("min_rr_ratio",         3.0),
    ("leverage",             5),
    ("daily_loss_limit_pct", 5.0),
    ("max_open_positions",   5),
    ("wins_to_increase",     1),
    ("progressive_stakes",   [3.0, 5.0, 8.0]),
    ("reset_on_loss",        True),
]

# ---------------------------------------------------------------------------
# /criteria alias tables
# ---------------------------------------------------------------------------

CRITERIA_ALIASES: dict[str, tuple] = {
    "period":   ("backtest_period_months", int,   1,    24),
    "return":   ("min_total_return_pct",   float, 10.0, 1000.0),
    "drawdown": ("max_drawdown_pct",       float, 1.0,  100.0),  # input positive, store negative
    "winrate":  ("min_win_rate_pct",       float, 30.0, 90.0),
    "pf":       ("min_profit_factor",      float, 1.0,  5.0),
    "trades":   ("min_trades",             int,   10,   200),
    "rr":       ("min_avg_rr",             float, 1.0,  5.0),
}

BOOL_ALIASES: dict[str, str] = {
    "notify": "notify_on_skip",
    "strict": "strict_mode",
}

# Criteria defaults for /criteria reset
_CRITERIA_DEFAULTS: dict[str, object] = {
    "backtest_period_months": 6,
    "min_total_return_pct":   200.0,
    "max_drawdown_pct":       -12.0,
    "min_win_rate_pct":       55.0,
    "min_profit_factor":      1.8,
    "min_trades":             30,
    "min_avg_rr":             2.0,
    "notify_on_skip":         True,
    "strict_mode":            False,
}

# ---------------------------------------------------------------------------
# /settings alias table
# ---------------------------------------------------------------------------

SETTINGS_ALIASES: dict[str, tuple] = {
    "top_n": ("top_n_coins", int, 1, 50),
    "norm_hours": ("volume_norm_hours", int, 1, 24),
    "growth_rate": ("min_volume_growth_rate", float, 0.1, 10.0),
}


# ---------------------------------------------------------------------------
# /risk handler
# ---------------------------------------------------------------------------

@router.message(Command("risk"))
async def cmd_risk(message: Message, session_factory, settings, **kwargs) -> None:
    """View or modify risk parameters.

    Usage:
      /risk                   — show all current risk parameters
      /risk stake 3           — set base_stake_pct to 3.0
      /risk max_stake 8       — set max_stake_pct to 8.0
      /risk rr 3.0            — set min_rr_ratio to 3.0
      /risk leverage 5        — set leverage to 5
      /risk daily_limit 5     — set daily_loss_limit_pct to 5.0
      /risk max_pos 5         — set max_open_positions to 5
      /risk progressive 3 5 8 — set progressive_stakes to [3.0, 5.0, 8.0]
      /risk reset             — restore all risk parameters to spec defaults
    """
    parts = message.text.split()

    # --- Show mode ---
    if len(parts) == 1:
        async with session_factory() as session:
            result = await session.execute(select(RiskSettings).limit(1))
            risk = result.scalars().first()

        if risk is None:
            await message.answer("❌ Настройки риска не найдены в БД.")
            return

        text = (
            "<b>Параметры риска:</b>\n"
            f"base_stake_pct:       {risk.base_stake_pct}%\n"
            f"max_stake_pct:        {risk.max_stake_pct}%\n"
            f"progressive_stakes:   {risk.progressive_stakes}\n"
            f"wins_to_increase:     {risk.wins_to_increase}\n"
            f"min_rr_ratio:         {risk.min_rr_ratio}\n"
            f"max_open_positions:   {risk.max_open_positions}\n"
            f"daily_loss_limit_pct: {risk.daily_loss_limit_pct}%\n"
            f"leverage:             {risk.leverage}x\n"
            f"margin_type:          {risk.margin_type}\n"
            f"win_streak_current:   {risk.win_streak_current} (read-only)"
        )
        await message.answer(text, parse_mode="HTML")
        return

    alias = parts[1]

    # --- Reset mode ---
    if alias == "reset":
        async with session_factory() as session:
            for field_name, default_value in _RISK_DEFAULTS:
                await update_risk_settings(session, field_name, default_value)

        logger.info("Risk settings reset to spec defaults via /risk reset")
        await message.answer("✅ Параметры риска сброшены до значений по умолчанию.")
        return

    # --- Progressive mode (special: 5 parts — cmd + "progressive" + 3 floats) ---
    if alias == "progressive":
        values_parts = parts[2:]
        if len(values_parts) != 3:
            await message.answer(
                "❌ progressive требует ровно 3 значения. "
                "Пример: /risk progressive 3 5 8"
            )
            return

        try:
            v1, v2, v3 = float(values_parts[0]), float(values_parts[1]), float(values_parts[2])
        except ValueError:
            await message.answer("❌ Неверное значение: progressive ожидает float.")
            return

        for v in [v1, v2, v3]:
            if not (0.0 <= v <= 100.0):
                await message.answer(
                    f"❌ Неверное значение: все значения progressive должны быть 0.0-100.0."
                )
                return

        async with session_factory() as session:
            result = await session.execute(select(RiskSettings).limit(1))
            risk = result.scalars().first()
            old_val = risk.progressive_stakes if risk else None
            await update_risk_settings(session, "progressive_stakes", [v1, v2, v3])

        await message.answer(f"✅ progressive_stakes: {old_val} → {[v1, v2, v3]}")
        return

    # --- Set mode (len == 3) ---
    if len(parts) != 3:
        await message.answer(
            "❌ Неизвестная команда. Используйте /help для справки."
        )
        return

    if alias not in RISK_ALIASES:
        await message.answer("❌ Неизвестная команда. Используйте /help для справки.")
        return

    field_name, cast_type, min_val, max_val = RISK_ALIASES[alias]

    try:
        typed_value = cast_type(parts[2])
    except (ValueError, TypeError):
        await message.answer(
            f"❌ Неверное значение: {alias} ожидает {cast_type.__name__}."
        )
        return

    # Fetch current value for validation error message
    async with session_factory() as session:
        result = await session.execute(select(RiskSettings).limit(1))
        risk = result.scalars().first()
        current_val = getattr(risk, field_name, "?") if risk else "?"

    if not (min_val <= typed_value <= max_val):
        await message.answer(
            f"❌ Неверное значение: {alias} должен быть {min_val}-{max_val}. "
            f"Текущее: {current_val}"
        )
        return

    old_val = current_val
    async with session_factory() as session:
        await update_risk_settings(session, field_name, typed_value)

    logger.info(f"risk_settings.{field_name} changed: {old_val} → {typed_value} via /risk")
    await message.answer(f"✅ {field_name}: {old_val} → {typed_value}")


# ---------------------------------------------------------------------------
# /criteria handler
# ---------------------------------------------------------------------------

@router.message(Command("criteria"))
async def cmd_criteria(message: Message, session_factory, settings, **kwargs) -> None:
    """View or modify strategy filter criteria.

    Usage:
      /criteria              — show all current criteria
      /criteria period 6     — set backtest_period_months to 6
      /criteria return 200   — set min_total_return_pct to 200.0
      /criteria drawdown 12  — set max_drawdown_pct to -12.0 (input positive, stored negative)
      /criteria winrate 55   — set min_win_rate_pct to 55.0
      /criteria pf 1.8       — set min_profit_factor to 1.8
      /criteria trades 30    — set min_trades to 30
      /criteria rr 2.0       — set min_avg_rr to 2.0
      /criteria notify on|off — set notify_on_skip to True/False
      /criteria strict on|off — set strict_mode to True/False
      /criteria reset        — restore all criteria to spec defaults
    """
    parts = message.text.split()

    # --- Show mode ---
    if len(parts) == 1:
        async with session_factory() as session:
            result = await session.execute(select(StrategyCriteria).limit(1))
            criteria = result.scalars().first()

        if criteria is None:
            await message.answer("❌ Критерии стратегий не найдены в БД.")
            return

        text = (
            "<b>Критерии стратегий:</b>\n"
            f"backtest_period_months: {criteria.backtest_period_months}\n"
            f"min_total_return_pct:   {criteria.min_total_return_pct}%\n"
            f"max_drawdown_pct:       {criteria.max_drawdown_pct}%\n"
            f"min_win_rate_pct:       {criteria.min_win_rate_pct}%\n"
            f"min_profit_factor:      {criteria.min_profit_factor}\n"
            f"min_trades:             {criteria.min_trades}\n"
            f"min_avg_rr:             {criteria.min_avg_rr}\n"
            f"notify_on_skip:         {criteria.notify_on_skip}\n"
            f"strict_mode:            {criteria.strict_mode}"
        )
        await message.answer(text, parse_mode="HTML")
        return

    alias = parts[1]

    # --- Reset mode ---
    if alias == "reset":
        async with session_factory() as session:
            result = await session.execute(select(StrategyCriteria).limit(1))
            criteria = result.scalars().first()

            if criteria is None:
                await message.answer("❌ Критерии стратегий не найдены в БД.")
                return

            for field_name, default_value in _CRITERIA_DEFAULTS.items():
                setattr(criteria, field_name, default_value)
            await session.commit()

        logger.info("Strategy criteria reset to spec defaults via /criteria reset")
        await message.answer("✅ Критерии стратегий сброшены до значений по умолчанию.")
        return

    if len(parts) != 3:
        await message.answer(
            "❌ Неизвестная команда. Используйте /help для справки."
        )
        return

    # --- Bool set mode (notify, strict) ---
    if alias in BOOL_ALIASES:
        field_name = BOOL_ALIASES[alias]
        raw = parts[2].lower()
        if raw == "on":
            new_bool = True
        elif raw == "off":
            new_bool = False
        else:
            await message.answer(
                f"❌ Неверное значение: {alias} ожидает 'on' или 'off'. "
                f"Пример: /criteria {alias} on"
            )
            return

        async with session_factory() as session:
            result = await session.execute(select(StrategyCriteria).limit(1))
            criteria = result.scalars().first()

            if criteria is None:
                await message.answer("❌ Критерии стратегий не найдены в БД.")
                return

            old_val = getattr(criteria, field_name)
            setattr(criteria, field_name, new_bool)
            await session.commit()

        logger.info(f"criteria.{field_name} changed: {old_val} → {new_bool} via /criteria")
        await message.answer(f"✅ {field_name}: {old_val} → {new_bool}")
        return

    # --- Numeric set mode ---
    if alias not in CRITERIA_ALIASES:
        await message.answer("❌ Неизвестная команда. Используйте /help для справки.")
        return

    field_name, cast_type, min_val, max_val = CRITERIA_ALIASES[alias]

    try:
        typed_value = cast_type(parts[2])
    except (ValueError, TypeError):
        await message.answer(
            f"❌ Неверное значение: {alias} ожидает {cast_type.__name__}."
        )
        return

    if not (min_val <= typed_value <= max_val):
        await message.answer(
            f"❌ Неверное значение: {alias} должен быть {min_val}-{max_val}. "
            f"Текущее значение: проверьте /criteria"
        )
        return

    # Special case: drawdown — input positive, store negative
    stored_value: float | int = typed_value
    if alias == "drawdown":
        stored_value = -abs(typed_value)

    async with session_factory() as session:
        result = await session.execute(select(StrategyCriteria).limit(1))
        criteria = result.scalars().first()

        if criteria is None:
            await message.answer("❌ Критерии стратегий не найдены в БД.")
            return

        old_val = getattr(criteria, field_name)
        setattr(criteria, field_name, stored_value)
        await session.commit()

    logger.info(f"criteria.{field_name} changed: {old_val} → {stored_value} via /criteria")
    await message.answer(f"✅ {field_name}: {old_val} → {stored_value}")


# ---------------------------------------------------------------------------
# /settings handler
# ---------------------------------------------------------------------------

@router.message(Command("settings"))
async def cmd_settings(message: Message, session_factory, settings, **kwargs) -> None:
    """View or modify general bot settings.

    Usage:
      /settings                    — show current settings
      /settings top_n 15           — set top_n_coins to 15 (in-memory only)
      /settings review_interval 14 — set review_interval_days for all active strategies
    """
    parts = message.text.split()

    # --- Show mode ---
    if len(parts) == 1:
        whitelist_count = len(settings.coin_whitelist) if hasattr(settings, "coin_whitelist") else "?"
        text = (
            "<b>Настройки бота:</b>\n"
            f"top_n_coins:       {settings.top_n_coins}\n"
            f"norm_hours:        {settings.volume_norm_hours}ч (базовый период объёма)\n"
            f"growth_rate:       {settings.min_volume_growth_rate}x (мин. темп роста)\n"
            f"coin_whitelist:    {whitelist_count} монет"
        )
        await message.answer(text, parse_mode="HTML")
        return

    if len(parts) < 3:
        await message.answer(
            "❌ Неизвестная настройка. Доступные: top_n, review_interval."
        )
        return

    alias = parts[1]

    # --- top_n: in-memory update ---
    if alias == "top_n":
        _, cast_type, min_val, max_val = SETTINGS_ALIASES["top_n"]
        try:
            new_value = cast_type(parts[2])
        except (ValueError, TypeError):
            await message.answer("❌ Неверное значение: top_n ожидает int.")
            return

        if not (min_val <= new_value <= max_val):
            await message.answer(
                f"❌ Неверное значение: top_n должен быть {min_val}-{max_val}. "
                f"Текущее: {settings.top_n_coins}"
            )
            return

        old_val = settings.top_n_coins
        settings.top_n_coins = new_value
        logger.info(f"settings.top_n_coins changed in-memory: {old_val} → {new_value} via /settings")
        await message.answer(
            f"✅ top_n_coins: {old_val} → {new_value}\n"
            "Изменение действует до следующего перезапуска."
        )
        return

    # --- review_interval: update all active Strategy rows ---
    if alias == "review_interval":
        try:
            new_interval = int(parts[2])
        except (ValueError, TypeError):
            await message.answer("❌ Неверное значение: review_interval ожидает int.")
            return

        if not (1 <= new_interval <= 365):
            await message.answer(
                f"❌ Неверное значение: review_interval должен быть 1-365. "
                f"Текущее: проверьте /strategies"
            )
            return

        async with session_factory() as session:
            result = await session.execute(
                select(Strategy).where(Strategy.is_active == True)  # noqa: E712
            )
            active_strategies = result.scalars().all()
            for strat in active_strategies:
                strat.review_interval_days = new_interval
            await session.commit()

        logger.info(
            f"review_interval_days updated to {new_interval} for all active strategies"
        )
        await message.answer(
            f"✅ review_interval_days → {new_interval} дней для всех активных стратегий."
        )
        return

    # --- Unknown subcommand ---
    await message.answer(
        "❌ Неизвестная настройка. Доступные: top_n, review_interval."
    )
