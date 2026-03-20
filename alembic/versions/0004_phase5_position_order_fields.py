"""Phase 5: add sl_order_id, tp_order_id, is_dry_run to positions; unique constraint on orders.signal_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("sl_order_id", sa.String(50), nullable=True))
    op.add_column("positions", sa.Column("tp_order_id", sa.String(50), nullable=True))
    op.add_column(
        "positions",
        sa.Column(
            "is_dry_run", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.create_unique_constraint(
        "uq_orders_signal_id", "orders", ["signal_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_orders_signal_id", "orders", type_="unique")
    op.drop_column("positions", "is_dry_run")
    op.drop_column("positions", "tp_order_id")
    op.drop_column("positions", "sl_order_id")
