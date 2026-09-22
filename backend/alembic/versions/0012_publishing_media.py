"""Kho ảnh đính kèm bài đăng theo từng khách.

Revision ID: 0012
Revises: 0011
"""

# plan: docs/plans/phase2_dashboard_detail.md
from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publishing_media",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publishing_media_user_id", "publishing_media", ["user_id"])
    op.create_index("ix_publishing_media_sha256", "publishing_media", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_publishing_media_sha256", table_name="publishing_media")
    op.drop_index("ix_publishing_media_user_id", table_name="publishing_media")
    op.drop_table("publishing_media")
