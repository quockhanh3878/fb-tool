"""Add one-time Discord registration codes to users.

# plan: docs/plans/community_job_runner_plan.md
Revision ID: 0017
Revises: 0016
"""

from alembic import op
import sqlalchemy as sa


revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("discord_link_code", sa.String(length=16), nullable=True))
    op.add_column("users", sa.Column("discord_link_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_discord_link_code", "users", ["discord_link_code"])


def downgrade() -> None:
    op.drop_index("ix_users_discord_link_code", table_name="users")
    op.drop_column("users", "discord_link_expires_at")
    op.drop_column("users", "discord_link_code")
