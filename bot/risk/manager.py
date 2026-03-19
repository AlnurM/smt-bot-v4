"""Risk Manager — position sizing, circuit breakers, and safety checks.

All calculation functions are pure (no side effects, no DB, no network).
update_risk_settings() is the only async function (writes to DB).

Formulas are canonical from idea.md section 7.3.
Liquidation formula from Binance official docs (isolated margin USDT-M).
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Position sizing (idea.md section 7.3 — exact formulas)
# ---------------------------------------------------------------------------

def calculate_position_size(
    balance: float,
    current_stake_pct: float,
    entry_price: float,
    stop_loss: float,
    leverage: int,
) -> dict:
    """Calculate position size using the canonical spec formula.

    Formula:
      risk_usdt     = balance x current_stake_pct / 100
      sl_distance   = |entry_price - stop_loss| / entry_price  (fraction)
      position_usdt = risk_usdt / sl_distance
      contracts     = position_usdt x leverage / entry_price

    Example: balance=100, stake=3%, entry=145, sl=140, leverage=5
      risk_usdt=3.00, sl_distance=0.03448, position_usdt=86.96, contracts~3.0

    Returns dict with keys: risk_usdt, sl_distance, position_usdt, contracts.
    Raises ValueError if entry_price == stop_loss (zero SL distance).
    """
    if entry_price == stop_loss:
        raise ValueError(
            f"entry_price ({entry_price}) equals stop_loss ({stop_loss}) — zero SL distance"
        )

    risk_usdt = balance * current_stake_pct / 100
    sl_distance = abs(entry_price - stop_loss) / entry_price
    position_usdt = risk_usdt / sl_distance
    contracts = (position_usdt * leverage) / entry_price

    logger.debug(
        f"Position size: risk_usdt={risk_usdt:.2f}, sl_distance={sl_distance:.4f}, "
        f"position_usdt={position_usdt:.2f}, contracts={contracts:.4f}"
    )
    return {
        "risk_usdt": round(risk_usdt, 4),
        "sl_distance": round(sl_distance, 6),
        "position_usdt": round(position_usdt, 4),
        "contracts": round(contracts, 4),
    }


# ---------------------------------------------------------------------------
# Progressive stakes (idea.md section 7.2)
# ---------------------------------------------------------------------------

def get_next_stake(
    win_streak: int,
    progressive_stakes: list[float],
    base_stake_pct: float,
    wins_to_increase: int,
) -> float:
    """Determine current stake based on win streak.

    win_streak 0                    -> base_stake_pct
    win_streak >= wins_to_increase  -> progressive_stakes[tier], capped at last tier

    Example with progressive_stakes=[3,5,8], wins_to_increase=1:
      streak=0 -> 3.0 (base)
      streak=1 -> 5.0 (tier 1)
      streak=2 -> 8.0 (tier 2 = max)
      streak=5 -> 8.0 (capped at max)
    """
    if not progressive_stakes:
        return base_stake_pct

    if win_streak <= 0:
        return base_stake_pct

    tier_index = win_streak // wins_to_increase
    # Clamp to last tier
    tier_index = min(tier_index, len(progressive_stakes) - 1)
    stake = progressive_stakes[tier_index]
    logger.debug(
        f"Progressive stake: win_streak={win_streak} -> tier_index={tier_index} -> stake={stake}%"
    )
    return float(stake)


def get_stake_after_loss(base_stake_pct: float) -> float:
    """Reset stake to base after any loss (per reset_on_loss=True design).

    Always returns base_stake_pct. Win streak resets to 0 (handled by caller).
    """
    logger.debug(f"Stake reset to base: {base_stake_pct}%")
    return float(base_stake_pct)


# ---------------------------------------------------------------------------
# Circuit breakers and guards (pure functions)
# ---------------------------------------------------------------------------

def check_max_positions(open_count: int, max_open_positions: int) -> bool:
    """Return True if a new position is allowed (open_count < max_open_positions).

    Returns False if at or above the limit.
    """
    allowed = open_count < max_open_positions
    if not allowed:
        logger.debug(f"Max positions reached: {open_count}/{max_open_positions}")
    return allowed


def check_daily_loss(
    total_pnl: float,
    starting_balance: float,
    daily_loss_limit_pct: float,
) -> bool:
    """Return True if daily loss limit is reached (trading HALTED).

    Condition: total_pnl < 0 AND |total_pnl| / starting_balance * 100 >= daily_loss_limit_pct

    Returns False if total_pnl is positive (no loss), or starting_balance is 0.
    """
    if starting_balance <= 0:
        logger.warning(
            "check_daily_loss: starting_balance <= 0, cannot compute loss percentage"
        )
        return False
    if total_pnl >= 0:
        return False
    loss_pct = abs(total_pnl) / starting_balance * 100
    halted = loss_pct >= daily_loss_limit_pct
    if halted:
        logger.warning(
            f"Daily loss limit reached: {loss_pct:.2f}% >= {daily_loss_limit_pct}% — "
            "new signal generation HALTED"
        )
    return halted


def check_rr_ratio(rr_ratio: float, min_rr_ratio: float) -> bool:
    """Return True if rr_ratio passes the minimum threshold (signal allowed).

    Returns False if rr_ratio < min_rr_ratio (signal filtered).
    """
    passes = rr_ratio >= min_rr_ratio
    if not passes:
        logger.debug(
            f"R/R filter: {rr_ratio:.2f} < min {min_rr_ratio:.2f} — signal filtered"
        )
    return passes


def check_min_notional(position_usdt: float, min_notional: float) -> bool:
    """Return True if position size meets MIN_NOTIONAL requirement.

    Returns False if position_usdt < min_notional.
    Per CONTEXT.md: caller sends signal as informational-only when this returns False.
    """
    passes = position_usdt >= min_notional
    if not passes:
        logger.debug(
            f"MIN_NOTIONAL check: position_usdt={position_usdt:.2f} < "
            f"min_notional={min_notional:.2f} — signal will be informational-only (no Confirm button)"
        )
    return passes


def validate_liquidation_safety(
    entry_price: float,
    stop_loss: float,
    leverage: int,
    liquidation_multiplier: float = 2.0,
    maintenance_margin_rate: float = 0.004,
) -> tuple[bool, float]:
    """Validate that the stop loss is not closer than the liquidation price.

    Liquidation price formulas (Binance isolated margin USDT-M):
      Long:  liq = entry * (1 - 1 / (leverage * (1 + MMR)))
      Short: liq = entry * (1 + 1 / (leverage * (1 + MMR)))

    Safety condition: liq_distance >= liquidation_multiplier * sl_distance

    Returns (is_safe, liquidation_price).

    is_safe=False means the position would be liquidated before the SL is hit
    at the configured leverage — this signal should be rejected.
    """
    sl_distance = abs(entry_price - stop_loss) / entry_price

    # Determine direction from SL position
    if stop_loss < entry_price:
        # Long position
        liq_price = entry_price * (1 - 1 / (leverage * (1 + maintenance_margin_rate)))
    else:
        # Short position
        liq_price = entry_price * (1 + 1 / (leverage * (1 + maintenance_margin_rate)))

    liq_distance = abs(entry_price - liq_price) / entry_price
    # Safety condition: liq_distance * multiplier >= leverage * sl_distance
    # This accounts for leverage amplification: at higher leverage the liquidation
    # is closer to entry, so the SL must be proportionally tighter.
    # Equivalent to: sl_distance <= liq_distance * multiplier / leverage
    is_safe = (liq_distance * liquidation_multiplier) >= (leverage * sl_distance)

    if not is_safe:
        logger.warning(
            f"Liquidation safety check FAILED: "
            f"liq_distance*mult={liq_distance * liquidation_multiplier:.4f} < "
            f"leverage*sl_distance={leverage * sl_distance:.4f}. "
            f"liq_price={liq_price:.2f}, entry={entry_price:.2f}, sl={stop_loss:.2f}, "
            f"leverage={leverage}x"
        )

    return is_safe, round(liq_price, 6)


# ---------------------------------------------------------------------------
# RISK-07: Margin type check (informational — order placement is Phase 5)
# ---------------------------------------------------------------------------

def check_margin_type(margin_type: str) -> bool:
    """Return True if margin_type is 'isolated' (required by spec).

    Phase 5 enforces this at order placement. Phase 3 logs a warning if wrong.
    """
    if margin_type != "isolated":
        logger.warning(
            f"margin_type='{margin_type}' is not 'isolated'. "
            "Isolated margin is required per spec. Phase 5 will enforce this."
        )
        return False
    return True


# ---------------------------------------------------------------------------
# RISK-10: update_risk_settings — exposed for Phase 4 Telegram /risk handler
# ---------------------------------------------------------------------------

async def update_risk_settings(
    session: AsyncSession,
    field_name: str,
    value: object,
) -> bool:
    """Update a single field in the risk_settings table.

    Called by Phase 4 Telegram /risk command handler.
    Returns True on success, False if field_name is not a valid column.

    Valid fields: base_stake_pct, max_stake_pct, progressive_stakes, wins_to_increase,
                  min_rr_ratio, max_open_positions, daily_loss_limit_pct, leverage,
                  margin_type, reset_on_loss
    """
    from bot.db.models import RiskSettings  # local import to avoid circular

    UPDATABLE_FIELDS = {
        "base_stake_pct", "max_stake_pct", "progressive_stakes", "wins_to_increase",
        "reset_on_loss", "min_rr_ratio", "max_open_positions", "daily_loss_limit_pct",
        "leverage", "margin_type",
    }

    if field_name not in UPDATABLE_FIELDS:
        logger.warning(f"update_risk_settings: '{field_name}' is not an updatable field")
        return False

    result = await session.execute(select(RiskSettings).limit(1))
    risk_row = result.scalar_one_or_none()
    if risk_row is None:
        logger.error("update_risk_settings: No risk_settings row found in DB")
        return False

    setattr(risk_row, field_name, value)
    await session.commit()
    logger.info(f"risk_settings.{field_name} updated to {value!r}")
    return True
