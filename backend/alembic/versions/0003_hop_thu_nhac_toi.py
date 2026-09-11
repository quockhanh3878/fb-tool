"""Hop thu "Nhac toi": bang mentions + campaigns.mention_keywords

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-10

# plan: docs/plans/phase2_dashboard_detail.md

Track B — trong luc Scout quet nhom, bat luon cac bai nhac ten thuong hieu
cua khach va gom vao mot hop thu rieng.

LUU Y: moi cot NOT NULL deu co server_default de migration khong vo tren
bang campaigns da co san du lieu cua khach.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mention_keywords",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )

    op.create_table(
        "mentions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("campaign_id", sa.String(length=32), nullable=False),
        sa.Column("campaign_group_id", sa.String(length=32), nullable=True),
        sa.Column("discovered_post_id", sa.String(length=32), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "matched_keywords", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "author_name", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "post_url", sa.String(length=500), nullable=False, server_default=""
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="new"
        ),
        sa.Column(
            "discovered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_group_id"], ["campaign_groups.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["discovered_post_id"], ["discovered_posts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "content_hash", name="uq_mention_campaign_hash"
        ),
    )
    op.create_index(
        "ix_mentions_campaign_id", "mentions", ["campaign_id"], unique=False
    )
    op.create_index(
        "ix_mentions_campaign_group_id",
        "mentions",
        ["campaign_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_mentions_discovered_post_id",
        "mentions",
        ["discovered_post_id"],
        unique=False,
    )
    op.create_index(
        "ix_mentions_content_hash", "mentions", ["content_hash"], unique=False
    )
    op.create_index("ix_mentions_status", "mentions", ["status"], unique=False)
    op.create_index(
        "ix_mentions_discovered_at", "mentions", ["discovered_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_mentions_discovered_at", table_name="mentions")
    op.drop_index("ix_mentions_status", table_name="mentions")
    op.drop_index("ix_mentions_content_hash", table_name="mentions")
    op.drop_index("ix_mentions_discovered_post_id", table_name="mentions")
    op.drop_index("ix_mentions_campaign_group_id", table_name="mentions")
    op.drop_index("ix_mentions_campaign_id", table_name="mentions")
    op.drop_table("mentions")

    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_column("mention_keywords")
