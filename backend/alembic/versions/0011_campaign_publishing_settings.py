"""Cấu hình lịch đăng/bump theo campaign.

Revision ID: 0011
Revises: 0010
"""

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("publish_repeat_interval_days", sa.Integer(), nullable=False, server_default="14")
        )
        batch_op.add_column(
            sa.Column("publish_auto_bump", sa.Boolean(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("publish_bump_hours", sa.JSON(), nullable=True, server_default="[10, 17, 19, 21]")
        )
        batch_op.add_column(
            sa.Column(
                "schedule_timezone",
                sa.String(length=64),
                nullable=False,
                server_default="Asia/Ho_Chi_Minh",
            )
        )
        batch_op.add_column(
            sa.Column("bump_jitter_enabled", sa.Boolean(), nullable=False, server_default="1")
        )
        batch_op.add_column(
            sa.Column("bump_jitter_min_minutes", sa.Integer(), nullable=False, server_default="5")
        )
        batch_op.add_column(
            sa.Column("bump_jitter_max_minutes", sa.Integer(), nullable=False, server_default="10")
        )


def downgrade() -> None:
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_column("bump_jitter_max_minutes")
        batch_op.drop_column("bump_jitter_min_minutes")
        batch_op.drop_column("bump_jitter_enabled")
        batch_op.drop_column("schedule_timezone")
        batch_op.drop_column("publish_bump_hours")
        batch_op.drop_column("publish_auto_bump")
        batch_op.drop_column("publish_repeat_interval_days")
