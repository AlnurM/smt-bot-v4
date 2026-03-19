"""Strategy Manager — lifecycle: generate, filter, save, expire, version history."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import sqlalchemy as sa
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from bot.db.models import Strategy, SkippedCoin
from bot.strategy.filter import FilterResult


# In-memory counter for consecutive empty scan cycles (persists until restart)
_consecutive_empty_cycles: int = 0


async def get_coins_needing_strategy(
    symbols: list[str],
    session: AsyncSession,
) -> tuple[list[str], list[str]]:
    """Return (no_strategy_coins, expired_strategy_coins) from the given symbol list.

    Active (non-expired) strategies are excluded — no Claude call needed for them (STRAT-05).
    Expired strategies (is_active=True, next_review_at <= now) are included in the second
    list — they stay active until save_strategy replaces them (CONTEXT.md: no coverage gap).
    Priority order: no_strategy first, expired second.
    """
    now_utc = datetime.now(timezone.utc)

    # Active (non-expired) symbols
    active_result = await session.execute(
        select(Strategy.symbol).where(
            Strategy.is_active == True,
            Strategy.next_review_at > now_utc,
        )
    )
    active_symbols = set(active_result.scalars().all())

    # Expired symbols (is_active=True but next_review_at has passed)
    expired_result = await session.execute(
        select(Strategy.symbol).where(
            Strategy.is_active == True,
            Strategy.next_review_at <= now_utc,
        )
    )
    expired_symbols = set(expired_result.scalars().all())

    no_strategy = [s for s in symbols if s not in active_symbols and s not in expired_symbols]
    expired_in_list = [s for s in symbols if s in expired_symbols]

    logger.debug(
        f"Priority queue: {len(no_strategy)} new coins, {len(expired_in_list)} expired, "
        f"{len(active_symbols)} active (skipped)"
    )
    return no_strategy, expired_in_list


async def get_expired_active_strategies(session: AsyncSession) -> list[Strategy]:
    """Return all active strategies where next_review_at <= now (LIFE-02)."""
    now_utc = datetime.now(timezone.utc)
    result = await session.execute(
        select(Strategy).where(
            Strategy.is_active == True,
            Strategy.next_review_at <= now_utc,
        )
    )
    return list(result.scalars().all())


async def save_strategy(
    session: AsyncSession,
    symbol: str,
    strategy_data: dict,
    criteria_snapshot: dict,
    review_interval_days: int = 30,
) -> Strategy:
    """Deactivate existing active strategies for symbol, insert new active strategy.

    Old strategies are preserved with is_active=False — never hard-deleted (LIFE-03).
    This is the ONLY place strategies are deactivated. run_expiry_check does not
    deactivate — it only logs. This ensures no coverage gap (CONTEXT.md locked decision).
    criteria_snapshot is stored for audit trail (LIFE-05).
    backtest_score = profit_factor * win_rate (LIFE-01).
    """
    # Deactivate all existing active strategies for this symbol (LIFE-03: never DELETE)
    await session.execute(
        sa.update(Strategy)
        .where(Strategy.symbol == symbol, Strategy.is_active == True)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )

    backtest = strategy_data.get("backtest", {})
    backtest_score = backtest.get("profit_factor", 0.0) * backtest.get("win_rate", 0.0)

    new_strategy = Strategy(
        symbol=symbol,
        timeframe=strategy_data.get("timeframe", "15m"),
        strategy_data=strategy_data,
        backtest_score=backtest_score,
        is_active=True,
        next_review_at=datetime.now(timezone.utc) + timedelta(days=review_interval_days),
        review_interval_days=review_interval_days,
        source="claude_generated",
        criteria_snapshot=criteria_snapshot,
    )
    session.add(new_strategy)
    await session.commit()
    logger.info(
        f"Strategy saved for {symbol} | score={backtest_score:.3f} | "
        f"next_review_at={new_strategy.next_review_at.date()}"
    )
    return new_strategy


async def log_skipped_coin(
    session: AsyncSession,
    symbol: str,
    strategy_data: dict,
    filter_result: FilterResult,
) -> None:
    """Insert a SkippedCoin record for a strategy that failed the filter (FILT-04)."""
    skipped = SkippedCoin(
        symbol=symbol,
        reason="filter_failed",
        backtest_results=strategy_data.get("backtest"),
        failed_criteria=filter_result.failed_criteria,
    )
    session.add(skipped)
    await session.commit()
    logger.info(
        f"Skipped coin logged: {symbol} | failed: {filter_result.failed_criteria}"
    )


async def deactivate_strategy(session: AsyncSession, strategy_id) -> None:
    """Mark a strategy as inactive (LIFE-03 — never delete).

    NOTE: This function exists for explicit one-off deactivation (e.g. admin action).
    It is NOT called by run_expiry_check — expiry leaves strategies active until
    save_strategy replaces them (CONTEXT.md locked decision: no coverage gap).
    """
    await session.execute(
        sa.update(Strategy)
        .where(Strategy.id == strategy_id)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    await session.commit()


async def run_strategy_scan(
    session_factory,
    binance_client,
    settings,
) -> None:
    """Hourly APScheduler job: scan whitelist, generate strategies for coins that need them.

    Priority queue: no_strategy first -> expired -> skip active (STRAT-05).
    Sequential Claude calls — no parallelism (CONTEXT.md locked decision).
    On ClaudeTimeoutError or ClaudeRateLimitError: alert and stop processing for this cycle.
    Consecutive empty cycle tracking for CONTEXT.md alert threshold.
    """
    global _consecutive_empty_cycles

    # Import here to avoid circular imports at module load
    from bot.scanner.market_scanner import get_top_n_by_volume, fetch_ohlcv_15m
    from bot.strategy.claude_engine import (
        generate_strategy, ClaudeTimeoutError, ClaudeRateLimitError, StrategySchemaError
    )
    from bot.strategy.filter import filter_strategy

    logger.info("Starting hourly strategy scan cycle")

    async with session_factory() as session:
        # Use settings defaults for criteria
        criteria = {
            "backtest_period_months": settings.backtest_period_months,
            "min_total_return_pct": settings.min_total_return_pct,
            "max_drawdown_pct": settings.max_drawdown_pct,
            "min_win_rate_pct": settings.min_win_rate_pct,
            "min_profit_factor": settings.min_profit_factor,
            "min_trades": settings.min_trades,
            "min_avg_rr": settings.min_avg_rr,
            "strict_mode": settings.strict_mode,
        }

        # Get ranked whitelist
        top_coins = await get_top_n_by_volume(
            binance_client,
            whitelist=settings.coin_whitelist,
            top_n=settings.top_n_coins,
            min_volume_usdt=settings.min_volume_usdt,
        )
        if not top_coins:
            logger.warning("Scanner returned no coins — all below volume threshold")
            return

        no_strategy, expired = await get_coins_needing_strategy(top_coins, session)
        candidates = no_strategy + expired  # no_strategy first per priority queue

        if not candidates:
            _consecutive_empty_cycles += 1
            logger.info(
                f"All {len(top_coins)} coins have active strategies. "
                f"Consecutive empty cycles: {_consecutive_empty_cycles}"
            )
            if _consecutive_empty_cycles >= settings.consecutive_empty_cycles_alert:
                logger.warning(
                    f"ALERT: {_consecutive_empty_cycles} consecutive scan cycles with no strategy generation needed. "
                    f"Consider loosening criteria."
                )
            return

        _consecutive_empty_cycles = 0  # reset on any activity

        for symbol in candidates:
            logger.info(f"Generating strategy for {symbol}")
            try:
                ohlcv_df = await fetch_ohlcv_15m(
                    binance_client, symbol, months=criteria["backtest_period_months"]
                )
                if ohlcv_df.empty:
                    logger.warning(f"Skipping {symbol}: insufficient OHLCV history")
                    continue

                strategy_data = await generate_strategy(
                    symbol=symbol,
                    ohlcv_df=ohlcv_df,
                    criteria=criteria,
                    api_key=settings.anthropic_api_key.get_secret_value(),
                    timeout=180,
                )

                filter_result = filter_strategy(
                    strategy_data, criteria, strict_mode=criteria["strict_mode"]
                )
                criteria_snapshot = {k: v for k, v in criteria.items()}

                if filter_result.passed:
                    await save_strategy(session, symbol, strategy_data, criteria_snapshot)
                    logger.info(f"Strategy saved for {symbol}")
                else:
                    await log_skipped_coin(session, symbol, strategy_data, filter_result)

            except (ClaudeTimeoutError, ClaudeRateLimitError) as e:
                logger.error(
                    f"Claude API error for {symbol}: {e}. "
                    f"Stopping scan cycle — will retry in next cycle."
                )
                # TODO: send Telegram alert (Phase 4 wires this)
                break
            except StrategySchemaError as e:
                logger.error(f"Strategy schema error for {symbol}: {e}. Skipping coin.")
                continue
            except Exception as e:
                logger.exception(f"Unexpected error processing {symbol}: {e}")
                continue

    logger.info("Strategy scan cycle complete")


async def run_expiry_check(session_factory) -> None:
    """Daily APScheduler job: log expired strategies awaiting re-generation.

    IMPORTANT: This job does NOT deactivate expired strategies. Expired strategies
    stay is_active=True so trading continues uninterrupted (CONTEXT.md locked decision:
    'Old strategy stays is_active=true until new one passes filter — no gap in coverage
    during re-generation').

    The hourly scan's get_coins_needing_strategy already surfaces expired strategies
    (is_active=True AND next_review_at <= now) into the re-generation queue.
    save_strategy atomically deactivates the old strategy when the replacement passes
    the filter. This job's role is visibility/alerting only.
    """
    logger.info("Running daily expiry check")
    async with session_factory() as session:
        expired = await get_expired_active_strategies(session)
        if not expired:
            logger.info("No expired strategies found")
            return
        logger.info(
            f"Found {len(expired)} expired strategies pending re-generation: "
            f"{[s.symbol for s in expired]}. "
            f"Strategies remain active until the hourly scan replaces them."
        )
        # No deactivation here — expired strategies stay active until save_strategy
        # atomically replaces them. get_coins_needing_strategy queues them for the
        # next hourly scan cycle automatically.
