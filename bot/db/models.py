"""All 10 SQLAlchemy ORM models for the trading bot."""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import ForeignKey, MetaData, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTIONS = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTIONS)


# ---------------------------------------------------------------------------
# strategies
# ---------------------------------------------------------------------------

class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    strategy_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    backtest_score: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("false"), nullable=False
    )
    next_review_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    review_interval_days: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("30"), nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(20), server_default=text("'claude_generated'"), nullable=False
    )
    criteria_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# strategy_criteria  (single row, seeded in migration)
# ---------------------------------------------------------------------------

class StrategyCriteria(Base):
    __tablename__ = "strategy_criteria"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    backtest_period_months: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    min_total_return_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    max_drawdown_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    min_win_rate_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    min_profit_factor: Mapped[float] = mapped_column(sa.Float, nullable=False)
    min_trades: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    min_avg_rr: Mapped[float] = mapped_column(sa.Float, nullable=False)
    notify_on_skip: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("true"), nullable=False
    )
    strict_mode: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("false"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# risk_settings  (single row, seeded in migration)
# ---------------------------------------------------------------------------

class RiskSettings(Base):
    __tablename__ = "risk_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    base_stake_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    current_stake_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    max_stake_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    progressive_stakes: Mapped[list] = mapped_column(JSONB, nullable=False)
    wins_to_increase: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reset_on_loss: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("true"), nullable=False
    )
    min_rr_ratio: Mapped[float] = mapped_column(sa.Float, nullable=False)
    max_open_positions: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    daily_loss_limit_pct: Mapped[float] = mapped_column(sa.Float, nullable=False)
    leverage: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    margin_type: Mapped[str] = mapped_column(
        String(10), server_default=text("'isolated'"), nullable=False
    )
    win_streak_current: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# signals  (FK -> strategies.id)
# ---------------------------------------------------------------------------

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    strategy_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("strategies.id"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)
    direction: Mapped[str] = mapped_column(String(5), nullable=False)
    entry_price: Mapped[float] = mapped_column(sa.Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(sa.Float, nullable=False)
    take_profit: Mapped[float] = mapped_column(sa.Float, nullable=False)
    rr_ratio: Mapped[float] = mapped_column(sa.Float, nullable=False)
    signal_strength: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# skipped_coins
# ---------------------------------------------------------------------------

class SkippedCoin(Base):
    __tablename__ = "skipped_coins"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    backtest_results: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    failed_criteria: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# orders  (FK -> signals.id)
# ---------------------------------------------------------------------------

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    signal_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("signals.id"),
        nullable=True,
    )
    binance_order_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    quantity: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    executed_price: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    filled_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# positions  (FK -> orders.id)
# ---------------------------------------------------------------------------

class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    entry_price: Mapped[float] = mapped_column(sa.Float, nullable=False)
    current_price: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    quantity: Mapped[float] = mapped_column(sa.Float, nullable=False)
    unrealized_pnl: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'open'"), nullable=False
    )
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# trades  (FK -> positions.id)
# ---------------------------------------------------------------------------

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    position_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("positions.id"),
        nullable=True,
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(5), nullable=False)
    entry_price: Mapped[float] = mapped_column(sa.Float, nullable=False)
    exit_price: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    realized_pnl: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    close_reason: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# daily_stats
# ---------------------------------------------------------------------------

class DailyStats(Base):
    __tablename__ = "daily_stats"
    __table_args__ = (sa.UniqueConstraint("date", name="uq_daily_stats_date"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    date: Mapped[datetime] = mapped_column(sa.Date, nullable=False)
    total_pnl: Mapped[float] = mapped_column(
        sa.Float, server_default=text("0.0"), nullable=False
    )
    trade_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    win_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    win_rate: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    starting_balance: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    ending_balance: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    current_stake_pct: Mapped[Optional[float]] = mapped_column(sa.Float, nullable=True)
    win_streak: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

class Log(Base):
    __tablename__ = "logs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), nullable=False
    )
