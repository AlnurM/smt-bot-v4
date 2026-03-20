import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Alembic Config object — access values from alembic.ini
config = context.config

# Set up loggers from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Wire in ORM models so autogenerate can detect schema changes
from bot.db.models import Base  # noqa: E402
target_metadata = Base.metadata

# Inject the real DB URL from pydantic-settings (overrides alembic.ini placeholder)
from bot.config import settings  # noqa: E402
from bot.db.session import _ensure_asyncpg_url  # noqa: E402
config.set_main_option(
    "sqlalchemy.url",
    _ensure_asyncpg_url(settings.database_url.get_secret_value()),
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live DB)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # detect JSONB vs JSON drift
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create async engine and run migrations online."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
