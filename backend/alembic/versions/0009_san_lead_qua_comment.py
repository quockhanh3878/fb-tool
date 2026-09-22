"""San lead qua comment: bang comment_leads + campaigns.lead_keywords +
clone_accounts.fb_user_id

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-12

# plan: docs/plans/phase2_dashboard_detail.md

Khac bang "mentions" (so khop tu khoa voi NOI DUNG BAI VIET): bang nay so
khop tu khoa voi NOI DUNG BINH LUAN duoi bai, giu lai danh tinh nguoi binh
luan (fb_comment_id/author_fb_id/commented_at) de anh Ber chu dong lien he.
clone_accounts.fb_user_id (rut tu cookie c_user) dung de loai tru chinh nick
dang quet khoi ket qua.

LUU Y: moi cot NOT NULL deu co server_default de migration khong vo tren
bang da co san du lieu cua khach.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("lead_keywords", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("clone_accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("fb_user_id", sa.String(length=32), nullable=False, server_default="")
        )

    op.create_table(
        "comment_leads",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("campaign_id", sa.String(length=32), nullable=False),
        sa.Column("campaign_group_id", sa.String(length=32), nullable=True),
        sa.Column(
            "fb_comment_id", sa.String(length=64), nullable=False, server_default=""
        ),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "matched_keywords", sa.JSON(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "author_fb_id", sa.String(length=32), nullable=False, server_default=""
        ),
        sa.Column(
            "author_name", sa.String(length=160), nullable=False, server_default=""
        ),
        sa.Column("comment_text", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "post_url", sa.String(length=500), nullable=False, server_default=""
        ),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="new"
        ),
        sa.Column("commented_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "campaign_id", "content_hash", name="uq_lead_campaign_hash"
        ),
    )
    op.create_index(
        "ix_comment_leads_campaign_id", "comment_leads", ["campaign_id"], unique=False
    )
    op.create_index(
        "ix_comment_leads_campaign_group_id",
        "comment_leads",
        ["campaign_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_comment_leads_content_hash", "comment_leads", ["content_hash"], unique=False
    )
    op.create_index(
        "ix_comment_leads_status", "comment_leads", ["status"], unique=False
    )
    op.create_index(
        "ix_comment_leads_discovered_at", "comment_leads", ["discovered_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_comment_leads_discovered_at", table_name="comment_leads")
    op.drop_index("ix_comment_leads_status", table_name="comment_leads")
    op.drop_index("ix_comment_leads_content_hash", table_name="comment_leads")
    op.drop_index("ix_comment_leads_campaign_group_id", table_name="comment_leads")
    op.drop_index("ix_comment_leads_campaign_id", table_name="comment_leads")
    op.drop_table("comment_leads")

    with op.batch_alter_table("clone_accounts", schema=None) as batch_op:
        batch_op.drop_column("fb_user_id")

    with op.batch_alter_table("campaigns", schema=None) as batch_op:
        batch_op.drop_column("lead_keywords")
