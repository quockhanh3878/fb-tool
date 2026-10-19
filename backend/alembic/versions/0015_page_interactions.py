"""Add durable PAGE_MONITOR interaction records.

# plan: docs/plans/community_job_runner_plan.md
Revision ID: 0015
Revises: 0014
"""

from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column("review_floor", sa.Float(), nullable=False, server_default="0.5"),
    )
    op.create_table(
        "page_interactions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("campaign_id", sa.String(length=32), sa.ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("post_publish_history_id", sa.String(length=32), sa.ForeignKey("post_publish_history.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("fb_comment_id", sa.String(length=128), nullable=False),
        sa.Column("parent_fb_comment_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("author_fb_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("author_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("comment_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("post_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("comment_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("commented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "fb_comment_id", name="uq_page_interaction_user_comment"),
    )
    op.create_index("ix_page_interactions_user_id", "page_interactions", ["user_id"])
    op.create_index("ix_page_interactions_campaign_id", "page_interactions", ["campaign_id"])
    op.create_index("ix_page_interactions_post_publish_history_id", "page_interactions", ["post_publish_history_id"])
    op.create_index("ix_page_interactions_event_type", "page_interactions", ["event_type"])
    op.create_index("ix_page_interactions_commented_at", "page_interactions", ["commented_at"])
    op.create_index("ix_page_interactions_discovered_at", "page_interactions", ["discovered_at"])


def downgrade() -> None:
    for name in (
        "ix_page_interactions_discovered_at",
        "ix_page_interactions_commented_at",
        "ix_page_interactions_event_type",
        "ix_page_interactions_post_publish_history_id",
        "ix_page_interactions_campaign_id",
        "ix_page_interactions_user_id",
    ):
        op.drop_index(name, table_name="page_interactions")
    op.drop_table("page_interactions")
    op.drop_column("campaigns", "review_floor")
