"""Luu lich su link publish, link comment va link den lead.

Revision ID: 0013
Revises: 0012
"""

# plan: docs/plans/phase2_dashboard_detail.md
from alembic import op
import sqlalchemy as sa


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("comment_actions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("fb_comment_id", sa.String(length=128), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("comment_url", sa.String(length=500), nullable=False, server_default=""))

    with op.batch_alter_table("comment_leads", schema=None) as batch_op:
        batch_op.add_column(sa.Column("comment_url", sa.String(length=500), nullable=False, server_default=""))

    op.create_table(
        "post_publish_history",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("post_publish_id", sa.String(length=32), sa.ForeignKey("post_publishes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("campaign_id", sa.String(length=32), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("clone_account_id", sa.String(length=32), sa.ForeignKey("clone_accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("group_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("group_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("group_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("post_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("content_snapshot", sa.Text(), nullable=False, server_default=""),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_post_publish_history_user_id", "post_publish_history", ["user_id"])
    op.create_index("ix_post_publish_history_post_publish_id", "post_publish_history", ["post_publish_id"])
    op.create_index("ix_post_publish_history_campaign_id", "post_publish_history", ["campaign_id"])
    op.create_index("ix_post_publish_history_clone_account_id", "post_publish_history", ["clone_account_id"])
    op.create_index("ix_post_publish_history_status", "post_publish_history", ["status"])
    op.create_index("ix_post_publish_history_published_at", "post_publish_history", ["published_at"])


def downgrade() -> None:
    for name in (
        "ix_post_publish_history_published_at",
        "ix_post_publish_history_status",
        "ix_post_publish_history_clone_account_id",
        "ix_post_publish_history_campaign_id",
        "ix_post_publish_history_post_publish_id",
        "ix_post_publish_history_user_id",
    ):
        op.drop_index(name, table_name="post_publish_history")
    op.drop_table("post_publish_history")

    with op.batch_alter_table("comment_leads", schema=None) as batch_op:
        batch_op.drop_column("comment_url")
    with op.batch_alter_table("comment_actions", schema=None) as batch_op:
        batch_op.drop_column("comment_url")
        batch_op.drop_column("fb_comment_id")
