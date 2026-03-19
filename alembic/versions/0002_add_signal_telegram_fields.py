"""Add telegram_message_id and caption to signals table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("telegram_message_id", sa.Integer(), nullable=True))
    op.add_column("signals", sa.Column("caption", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "caption")
    op.drop_column("signals", "telegram_message_id")
