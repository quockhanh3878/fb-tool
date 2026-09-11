"""Cho phep tinh nang AI comment la tuy chon: cot campaigns.ai_comments_enabled

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-11

# plan: docs/plans/phase2_dashboard_detail.md
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "ai_comments_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_column("ai_comments_enabled")
