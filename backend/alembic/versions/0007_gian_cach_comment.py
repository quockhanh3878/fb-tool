"""Gian cach giua 2 comment cua mot nick: cot clone_accounts.next_comment_at

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-11

# plan: docs/plans/phase3_antiban_detail.md
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("clone_accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("next_comment_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("clone_accounts", schema=None) as batch_op:
        batch_op.drop_column("next_comment_at")
