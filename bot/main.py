"""Main entrypoint — startup sequence, signal handlers, graceful shutdown."""
import asyncio
import signal
import sys

from loguru import logger
from aiogram import Bot, Dispatcher
from sqlalchemy import text, select, func

from bot.config import settings, configure_logging
from bot.db.session import engine, SessionLocal, _ensure_asyncpg_url
from bot.db.models import Position
from bot.exchange.client import create_binance_client
from bot.scheduler.setup import create_scheduler
from bot.strategy.manager import run_strategy_scan, run_expiry_check
from bot.monitor.position import monitor_positions
from bot.reporting.daily_summary import send_daily_summary
from bot.telegram.middleware import AllowedChatMiddleware
from bot.telegram.handlers.commands import router as commands_router
from bot.telegram.handlers.callbacks import router as callbacks_router
from bot.telegram.handlers.settings import router as settings_router
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger


async def startup_position_sync(binance_client, session_factory) -> None:
    """
    Fetch open positions from Binance API and reconcile with DB positions table.
    Called on every restart to catch positions that may have changed while bot was offline.

    - Binance positions not in DB → create new Position row (warning logged)
    - DB positions not on Binance → log warning for manual review (do NOT auto-close)
    """
    logger.info("Starting position sync...")

    # Fetch from Binance: GET /fapi/v2/positionRisk — returns all positions
    # Filter: only positions where positionAmt != 0.0 (these are truly open)
    positions = await binance_client.futures_position_information()
    open_binance = [p for p in positions if float(p["positionAmt"]) != 0.0]

    async with session_factory() as session:
        for bp in open_binance:
            symbol = bp["symbol"]
            side = "long" if float(bp["positionAmt"]) > 0 else "short"
            result = await session.execute(
                select(Position).where(
                    Position.symbol == symbol,
                    Position.side == side,
                    Position.status == "open",
                )
            )
            existing = result.scalars().first()
            if not existing:
                logger.warning(
                    f"Position sync: found open position on Binance not in DB — "
                    f"{symbol} {side}. Creating record."
                )
                new_pos = Position(
                    symbol=symbol,
                    side=side,
                    entry_price=float(bp["entryPrice"]),
                    current_price=float(bp["markPrice"]),
                    quantity=abs(float(bp["positionAmt"])),
                    unrealized_pnl=float(bp["unRealizedProfit"]),
                    status="open",
                    environment=settings.binance_env,
                )
                session.add(new_pos)
        await session.commit()

    # Log positions in DB that are open but NOT on Binance (discrepancy warning)
    async with session_factory() as session:
        result = await session.execute(
            select(Position).where(Position.status == "open")
        )
        db_open = result.scalars().all()

    binance_symbols = {
        (p["symbol"], "long" if float(p["positionAmt"]) > 0 else "short")
        for p in open_binance
    }
    for dp in db_open:
        if (dp.symbol, dp.side) not in binance_symbols:
            logger.warning(
                f"Position sync: DB has open position {dp.symbol} {dp.side} "
                f"not found on Binance. Manual review needed."
            )

    logger.info(
        f"Position sync complete. "
        f"Binance open: {len(open_binance)}, DB open: {len(db_open)}"
    )


async def verify_migrations_current() -> None:
    """
    Compare current DB migration revision to Alembic head.
    Raises RuntimeError if not at head — main() will catch and exit.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from alembic.runtime.migration import MigrationContext

    alembic_cfg = Config("alembic.ini")
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    head_revision = script_dir.get_current_head()

    async with engine.connect() as conn:
        def get_current(sync_conn):
            ctx = MigrationContext.configure(sync_conn)
            return ctx.get_current_revision()

        current_revision = await conn.run_sync(get_current)

    if current_revision != head_revision:
        raise RuntimeError(
            f"DB migration mismatch: current={current_revision}, head={head_revision}. "
            "Run `alembic upgrade head` before starting the bot."
        )
    logger.info(f"DB migrations current: {current_revision}")


async def main() -> None:
    """
    Application entrypoint — runs startup checks, starts scheduler and Telegram polling.

    Startup order:
      1. DB connection + migrations check  (fail-fast)
      2. Binance API check                 (fail-fast)
      3. Telegram check                    (fail-fast)
      4. Position sync on restart          (non-fatal warning on failure)
      5. Start APScheduler
      6. Send startup notification
      7. Start Telegram polling (blocks until SIGTERM/SIGINT via aiogram)
    """
    configure_logging(settings)
    logger.info("Bot starting...")

    # --- Step 1: DB check + auto-migrate ---
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("DB connection OK")

        # Auto-run migrations on startup (safe for fresh DBs like Railway)
        from alembic.runtime.migration import MigrationContext
        from alembic.operations import Operations
        from bot.db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("DB tables ensured (create_all)")

        # Now run Alembic stamp so it knows we're at head
        from alembic.config import Config as AlembicConfig
        from alembic.script import ScriptDirectory
        alembic_cfg = AlembicConfig("alembic.ini")
        script_dir = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script_dir.get_current_head()

        async with engine.begin() as conn:
            def stamp_head(sync_conn):
                ctx = MigrationContext.configure(sync_conn)
                if ctx.get_current_revision() is None:
                    ctx._ensure_version_table()
                    sync_conn.execute(
                        ctx._version.insert().values(version_num=head_rev)
                    )
            await conn.run_sync(stamp_head)
        logger.info(f"DB migrations stamped at head: {head_rev}")

        await verify_migrations_current()
    except Exception as e:
        logger.error(f"DB check failed: {e}")
        sys.exit(1)

    # --- Step 2: Binance check ---
    try:
        binance_client = await create_binance_client(settings)
        await binance_client.futures_ping()
        account = await binance_client.futures_account()
        balance = float(account["totalWalletBalance"])
        logger.info(
            f"Binance connected | env={settings.binance_env} | balance=${balance:.2f}"
        )
    except Exception as e:
        logger.error(f"Binance check failed: {e}")
        sys.exit(1)

    # --- Step 3: Telegram check ---
    try:
        bot = Bot(token=settings.telegram_bot_token.get_secret_value())
        bot_info = await bot.get_me()
        logger.info(f"Telegram bot connected: @{bot_info.username}")
    except Exception as e:
        logger.error(f"Telegram check failed: {e}")
        sys.exit(1)

    # --- Step 4: Position sync on restart (non-fatal) ---
    try:
        await startup_position_sync(binance_client, SessionLocal)
    except Exception as e:
        logger.warning(f"Position sync failed (non-fatal): {e}")

    # --- Step 5: Start scheduler ---
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")

    # Register hourly market scan job (SCAN-02)
    scheduler.add_job(
        run_strategy_scan,
        trigger=CronTrigger(hour="*", minute="5", timezone="UTC"),
        id="strategy_scan",
        replace_existing=True,
        args=[SessionLocal, binance_client, settings, bot, scheduler],
    )
    # Register daily expiry check job (LIFE-02)
    scheduler.add_job(
        run_expiry_check,
        trigger=CronTrigger(hour="2", minute="0", timezone="UTC"),
        id="expiry_check",
        replace_existing=True,
        args=[SessionLocal],
    )
    # Register position monitoring job (MON-01 through MON-05)
    scheduler.add_job(
        monitor_positions,
        trigger=IntervalTrigger(seconds=60),
        id="position_monitor",
        replace_existing=True,
        args=[SessionLocal, binance_client, settings, bot],
    )
    # Register daily summary job (TG-19)
    scheduler.add_job(
        send_daily_summary,
        trigger=CronTrigger(hour=21, minute=0, timezone="Etc/GMT-5"),
        id="daily_summary",
        replace_existing=True,
        args=[SessionLocal, binance_client, settings, bot],
    )
    logger.info(
        "APScheduler jobs registered: "
        "strategy_scan (hourly :05) + expiry_check (02:00 UTC) + "
        "position_monitor (every 60s) + daily_summary (21:00 UTC+5)"
    )

    # --- Step 6: Startup notification ---
    try:
        async with SessionLocal() as session:
            result = await session.execute(
                select(func.count()).select_from(Position).where(
                    Position.status == "open"
                )
            )
            open_count = result.scalar()
        startup_msg = (
            f"✅ Бот активен\n\n"
            f"💰 Баланс: ${balance:.2f}\n"
            f"📊 Открытых позиций: {open_count}\n"
            f"💪 Текущая ставка: {settings.base_stake_pct}%\n"
            f"🌐 Среда: {settings.binance_env}"
        )
        await bot.send_message(settings.allowed_chat_id, startup_msg)
    except Exception as e:
        logger.warning(f"Startup notification failed (non-fatal): {e}")

    # --- Step 7: Signal handlers + Telegram polling (blocks until shutdown) ---
    dp = Dispatcher()

    # Wire AllowedChatMiddleware (TG-01) — drop all non-allowed chat_ids before any handler fires
    dp.update.middleware(AllowedChatMiddleware(settings.allowed_chat_id))
    # Register command router
    dp.include_router(commands_router)
    # Register callback router (TG-03, TG-04: Confirm, Reject, Pine Script inline buttons)
    dp.include_router(callbacks_router)
    # Register settings router (TG-07, TG-08, TG-16: /risk, /criteria, /settings)
    dp.include_router(settings_router)
    # Inject workflow data — available in all handlers via data["key"]
    dp["bot"] = bot
    dp["session_factory"] = SessionLocal
    dp["scheduler"] = scheduler
    dp["binance_client"] = binance_client
    dp["settings"] = settings

    shutdown_event = asyncio.Event()

    async def on_shutdown():
        logger.info("Shutdown initiated")
        scheduler.shutdown(wait=False)
        await binance_client.close_connection()
        logger.info("Shutdown complete")
        shutdown_event.set()

    dp.shutdown.register(on_shutdown)

    logger.info("Starting Telegram polling...")
    await dp.start_polling(bot, handle_signals=True)


if __name__ == "__main__":
    asyncio.run(main())
