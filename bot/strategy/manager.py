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
    bot=None,       # NEW: Bot instance for Telegram alerts (Phase 4)
    scheduler=None, # NEW: APScheduler instance for signal expiry scheduling (Phase 4)
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
                if bot is not None:
                    from bot.telegram.notifications import send_skipped_coins_alert
                    asyncio.create_task(
                        send_skipped_coins_alert(
                            bot,
                            settings.allowed_chat_id,
                            _consecutive_empty_cycles,
                            settings.consecutive_empty_cycles_alert,
                        )
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

                    # Signal dispatch wiring (TG-02 key link — Phase 4)
                    # After strategy is saved, generate and dispatch a signal if bot is available.
                    # bot/telegram/dispatch module is created in Plan 02.
                    if bot is not None:
                        from bot.signals.generator import generate_signal
                        from bot.charts.generator import generate_chart
                        from bot.risk.manager import calculate_position_size, check_rr_ratio
                        from bot.db.models import RiskSettings as RiskSettingsModel, Signal as SignalModel
                        from bot.telegram.dispatch import send_signal_message, schedule_signal_expiry

                        MIN_NOTIONAL_USDT = 5.0

                        risk_result = await session.execute(
                            select(RiskSettingsModel).limit(1)
                        )
                        risk_settings = risk_result.scalars().first()

                        signal = await generate_signal(
                            binance_client, symbol, strategy_data, ohlcv_df
                        )
                        if signal is not None:
                            # R/R filter (RISK-03) — skip signal if below min threshold
                            min_rr = risk_settings.min_rr_ratio if risk_settings else 1.5
                            if not check_rr_ratio(signal["rr_ratio"], min_rr):
                                logger.info(
                                    f"Signal for {symbol} filtered: rr_ratio={signal['rr_ratio']:.2f} "
                                    f"< min_rr_ratio={min_rr:.2f}"
                                )
                                continue  # skip to next candidate coin

                            chart_bytes = await generate_chart(
                                ohlcv_df, signal, signal.get("zones", {})
                            )
                            leverage = risk_settings.leverage if risk_settings else 5
                            balance_info = await binance_client.futures_account()
                            balance = float(balance_info.get("totalWalletBalance", 0))
                            stake_pct = risk_settings.current_stake_pct if risk_settings else 3.0
                            position_size = calculate_position_size(
                                balance=balance,
                                current_stake_pct=stake_pct,
                                entry_price=signal["entry_price"],
                                stop_loss=signal["stop_loss"],
                                leverage=leverage,
                            )
                            position_size["stake_pct"] = stake_pct
                            is_min_notional = (
                                position_size.get("contracts", 0) * signal["entry_price"]
                                < MIN_NOTIONAL_USDT
                            )

                            # Insert Signal DB row BEFORE dispatch (Gap 1 fix — SIG-01..06)
                            signal_row = SignalModel(
                                symbol=signal["symbol"],
                                timeframe=signal.get("timeframe", "15m"),
                                direction=signal["direction"],
                                entry_price=signal["entry_price"],
                                stop_loss=signal["stop_loss"],
                                take_profit=signal["take_profit"],
                                rr_ratio=signal["rr_ratio"],
                                signal_strength=signal.get("signal_strength"),
                                reasoning=signal.get("reasoning"),
                                status="pending",
                            )
                            session.add(signal_row)
                            await session.flush()  # populates signal_row.id with real UUID
                            signal["id"] = str(signal_row.id)  # dispatch.py uses signal["id"] in callback_data

                            message_id = await send_signal_message(
                                bot,
                                settings.allowed_chat_id,
                                signal,
                                chart_bytes,
                                position_size,
                                is_min_notional=is_min_notional,
                            )
                            if message_id != -1:
                                signal_row.telegram_message_id = message_id
                                # Save zones data for Pine Script generation (PINE-01)
                                if signal.get("zones"):
                                    from bot.reporting.pine_script import _zones_to_json_safe
                                    signal_row.zones_data = _zones_to_json_safe(signal["zones"])
                                await session.commit()
                                schedule_signal_expiry(
                                    scheduler,
                                    bot,
                                    settings.allowed_chat_id,
                                    message_id,
                                    str(signal_row.id),
                                    session_factory,
                                    timeout_minutes=getattr(
                                        settings, "signal_expiry_minutes", 15
                                    ),
                                )
                            else:
                                # Bot is paused — discard the Signal row, do not commit
                                await session.rollback()
                else:
                    await log_skipped_coin(session, symbol, strategy_data, filter_result)

            except (ClaudeTimeoutError, ClaudeRateLimitError) as e:
                logger.error(
                    f"Claude API error for {symbol}: {e}. "
                    f"Stopping scan cycle — will retry in next cycle."
                )
                if bot is not None:
                    from bot.telegram.notifications import send_error_alert
                    asyncio.create_task(
                        send_error_alert(
                            bot,
                            settings.allowed_chat_id,
                            "claude_api_error",
                            str(e),
                        )
                    )
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
