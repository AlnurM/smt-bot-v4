"""Initial migration: create all 10 tables and seed risk_settings + strategy_criteria.

Revision ID: 0001
Revises:
Create Date: 2026-03-19
"""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as sa_pg

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Table creation in FK dependency order
    # ------------------------------------------------------------------

    # 1. strategies (no FK deps)
    op.create_table(
        "strategies",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(5), nullable=False),
        sa.Column("strategy_data", sa_pg.JSONB, nullable=False),
        sa.Column("backtest_score", sa.Float, nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean,
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("next_review_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "review_interval_days",
            sa.Integer,
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.String(20),
            server_default=sa.text("'claude_generated'"),
            nullable=False,
        ),
        sa.Column("criteria_snapshot", sa_pg.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 2. strategy_criteria (no FK deps, single row, seeded below)
    op.create_table(
        "strategy_criteria",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("backtest_period_months", sa.Integer, nullable=False),
        sa.Column("min_total_return_pct", sa.Float, nullable=False),
        sa.Column("max_drawdown_pct", sa.Float, nullable=False),
        sa.Column("min_win_rate_pct", sa.Float, nullable=False),
        sa.Column("min_profit_factor", sa.Float, nullable=False),
        sa.Column("min_trades", sa.Integer, nullable=False),
        sa.Column("min_avg_rr", sa.Float, nullable=False),
        sa.Column(
            "notify_on_skip",
            sa.Boolean,
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "strict_mode",
            sa.Boolean,
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 3. risk_settings (no FK deps, single row, seeded below)
    op.create_table(
        "risk_settings",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("base_stake_pct", sa.Float, nullable=False),
        sa.Column("current_stake_pct", sa.Float, nullable=False),
        sa.Column("max_stake_pct", sa.Float, nullable=False),
        sa.Column("progressive_stakes", sa_pg.JSONB, nullable=False),
        sa.Column("wins_to_increase", sa.Integer, nullable=False),
        sa.Column(
            "reset_on_loss",
            sa.Boolean,
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("min_rr_ratio", sa.Float, nullable=False),
        sa.Column("max_open_positions", sa.Integer, nullable=False),
        sa.Column("daily_loss_limit_pct", sa.Float, nullable=False),
        sa.Column("leverage", sa.Integer, nullable=False),
        sa.Column(
            "margin_type",
            sa.String(10),
            server_default=sa.text("'isolated'"),
            nullable=False,
        ),
        sa.Column(
            "win_streak_current",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 4. signals (FK -> strategies.id)
    op.create_table(
        "signals",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "strategy_id",
            sa_pg.UUID(as_uuid=False),
            sa.ForeignKey("strategies.id"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(5), nullable=False),
        sa.Column("direction", sa.String(5), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("stop_loss", sa.Float, nullable=False),
        sa.Column("take_profit", sa.Float, nullable=False),
        sa.Column("rr_ratio", sa.Float, nullable=False),
        sa.Column("signal_strength", sa.String(20), nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 5. skipped_coins (no FK deps)
    op.create_table(
        "skipped_coins",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("backtest_results", sa_pg.JSONB, nullable=True),
        sa.Column("failed_criteria", sa_pg.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 6. orders (FK -> signals.id)
    op.create_table(
        "orders",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "signal_id",
            sa_pg.UUID(as_uuid=False),
            sa.ForeignKey("signals.id"),
            nullable=True,
        ),
        sa.Column("binance_order_id", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("executed_price", sa.Float, nullable=True),
        sa.Column("filled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 7. positions (FK -> orders.id)
    op.create_table(
        "positions",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "order_id",
            sa_pg.UUID(as_uuid=False),
            sa.ForeignKey("orders.id"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("current_price", sa.Float, nullable=True),
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("unrealized_pnl", sa.Float, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            server_default=sa.text("'open'"),
            nullable=False,
        ),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 8. trades (FK -> positions.id)
    op.create_table(
        "trades",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "position_id",
            sa_pg.UUID(as_uuid=False),
            sa.ForeignKey("positions.id"),
            nullable=True,
        ),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("realized_pnl", sa.Float, nullable=True),
        sa.Column("close_reason", sa.String(20), nullable=True),
        sa.Column("opened_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # 9. daily_stats (no FK deps)
    op.create_table(
        "daily_stats",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column(
            "total_pnl",
            sa.Float,
            server_default=sa.text("0.0"),
            nullable=False,
        ),
        sa.Column(
            "trade_count",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "win_count",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("win_rate", sa.Float, nullable=True),
        sa.Column("starting_balance", sa.Float, nullable=True),
        sa.Column("ending_balance", sa.Float, nullable=True),
        sa.Column("current_stake_pct", sa.Float, nullable=True),
        sa.Column(
            "win_streak",
            sa.Integer,
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_unique_constraint("uq_daily_stats_date", "daily_stats", ["date"])

    # 10. logs (no FK deps)
    op.create_table(
        "logs",
        sa.Column(
            "id",
            sa_pg.UUID(as_uuid=False),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("module", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # Seed data
    # ------------------------------------------------------------------

    # Seed risk_settings (single canonical row)
    risk_settings_table = sa.table(
        "risk_settings",
        sa.column("id"),
        sa.column("base_stake_pct"),
        sa.column("current_stake_pct"),
        sa.column("max_stake_pct"),
        sa.column("progressive_stakes"),
        sa.column("wins_to_increase"),
        sa.column("reset_on_loss"),
        sa.column("min_rr_ratio"),
        sa.column("max_open_positions"),
        sa.column("daily_loss_limit_pct"),
        sa.column("leverage"),
        sa.column("margin_type"),
        sa.column("win_streak_current"),
    )
    op.bulk_insert(
        risk_settings_table,
        [
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "base_stake_pct": 3.0,
                "current_stake_pct": 3.0,
                "max_stake_pct": 8.0,
                "progressive_stakes": json.dumps([3.0, 5.0, 8.0]),
                "wins_to_increase": 1,
                "reset_on_loss": True,
                "min_rr_ratio": 3.0,
                "max_open_positions": 5,
                "daily_loss_limit_pct": 5.0,
                "leverage": 5,
                "margin_type": "isolated",
                "win_streak_current": 0,
            }
        ],
    )

    # Seed strategy_criteria (single canonical row)
    strategy_criteria_table = sa.table(
        "strategy_criteria",
        sa.column("id"),
        sa.column("backtest_period_months"),
        sa.column("min_total_return_pct"),
        sa.column("max_drawdown_pct"),
        sa.column("min_win_rate_pct"),
        sa.column("min_profit_factor"),
        sa.column("min_trades"),
        sa.column("min_avg_rr"),
        sa.column("notify_on_skip"),
        sa.column("strict_mode"),
    )
    op.bulk_insert(
        strategy_criteria_table,
        [
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "backtest_period_months": 6,
                "min_total_return_pct": 200.0,
                "max_drawdown_pct": -12.0,
                "min_win_rate_pct": 55.0,
                "min_profit_factor": 1.8,
                "min_trades": 30,
                "min_avg_rr": 2.0,
                "notify_on_skip": True,
                "strict_mode": False,
            }
        ],
    )


def downgrade() -> None:
    # Drop in reverse FK dependency order
    op.drop_table("trades")
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("signals")
    op.drop_table("strategies")
    op.drop_table("skipped_coins")
    op.drop_table("logs")
    op.drop_table("daily_stats")
    op.drop_table("strategy_criteria")
    op.drop_table("risk_settings")
