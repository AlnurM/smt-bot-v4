"""Phase 6: add zones_data JSONB column to signals table for Pine Script generation

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signals",
        sa.Column("zones_data", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("signals", "zones_data")
