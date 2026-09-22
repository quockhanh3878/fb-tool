"""Dang bai dinh ky 2 tuan 1 lan va auto bump 4 lan 1 ngay (10h, 14h, 18h, 21h)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("post_publishes", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("repeat_interval_days", sa.Integer(), nullable=True, server_default="14")
        )
        batch_op.add_column(
            sa.Column("auto_bump", sa.Boolean(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("bump_hours", sa.JSON(), nullable=True, server_default="[10, 14, 18, 21]")
        )


def downgrade() -> None:
    with op.batch_alter_table("post_publishes", schema=None) as batch_op:
        batch_op.drop_column("bump_hours")
        batch_op.drop_column("auto_bump")
        batch_op.drop_column("repeat_interval_days")
