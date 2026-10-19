"""Add channel-aware notification delivery and recipients.

# plan: docs/plans/community_job_runner_plan.md
Revision ID: 0014
Revises: 0013
"""

from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_outbox", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("channel", sa.String(length=24), nullable=False, server_default="telegram")
        )

    op.create_table(
        "notification_recipients",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(length=24), nullable=False),
        sa.Column("recipient_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(length=24), nullable=False, server_default="manual"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "channel", "recipient_id", name="uq_notification_recipient_target"),
    )
    op.create_index("ix_notification_recipients_user_id", "notification_recipients", ["user_id"])
    op.create_index("ix_notification_recipients_is_active", "notification_recipients", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_notification_recipients_is_active", table_name="notification_recipients")
    op.drop_index("ix_notification_recipients_user_id", table_name="notification_recipients")
    op.drop_table("notification_recipients")
    with op.batch_alter_table("notification_outbox", schema=None) as batch_op:
        batch_op.drop_column("channel")
