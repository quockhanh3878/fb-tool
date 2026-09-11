"""Track A - dang bai that: bang post_publishes + clone_accounts.daily_post_*

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-10

# plan: docs/plans/phase2_dashboard_detail.md

Track A them model `PostPublish` va 2 cot dem bai/ngay cho clone nhung chua co
file migration -> `alembic check` bao drift. File nay khop lai model voi schema.

LUU Y: `daily_post_count` / `daily_post_limit` la cot NOT NULL them vao bang
`clone_accounts` DA CO du lieu khach -> bat buoc co server_default de migration
khong vo. Cac cot JSON cua `post_publishes` cung co server_default cho dong bo.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "post_publishes",
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("campaign_id", sa.String(length=32), nullable=True),
        sa.Column("clone_account_id", sa.String(length=32), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("content_template", sa.Text(), nullable=False),
        sa.Column("media_urls", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("target_groups", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="scheduled"
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_results", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["clone_account_id"], ["clone_accounts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("post_publishes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_post_publishes_campaign_id"), ["campaign_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_post_publishes_clone_account_id"),
            ["clone_account_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_post_publishes_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_post_publishes_user_id"), ["user_id"], unique=False
        )

    with op.batch_alter_table("clone_accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "daily_post_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "daily_post_limit",
                sa.Integer(),
                nullable=False,
                server_default="5",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("clone_accounts", schema=None) as batch_op:
        batch_op.drop_column("daily_post_limit")
        batch_op.drop_column("daily_post_count")

    with op.batch_alter_table("post_publishes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_post_publishes_user_id"))
        batch_op.drop_index(batch_op.f("ix_post_publishes_status"))
        batch_op.drop_index(batch_op.f("ix_post_publishes_clone_account_id"))
        batch_op.drop_index(batch_op.f("ix_post_publishes_campaign_id"))

    op.drop_table("post_publishes")
