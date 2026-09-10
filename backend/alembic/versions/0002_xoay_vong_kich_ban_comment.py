"""Xoay vong kich ban comment: is_active, usage_count, last_used_at

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08

Ba cot moi tren comment_scripts phuc vu tinh nang "comment xoay":
  - is_active   : tat tam mot kich ban ma khong phai xoa
  - usage_count : dem so lan da dung, de xoay vong deu tay
  - last_used_at: moc thoi gian dung gan nhat, de uu tien cai lau chua dung

LUU Y: hai cot NOT NULL phai co server_default, neu khong migration se vo
tren bang da co san du lieu cua khach.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("comment_scripts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "usage_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("comment_scripts", schema=None) as batch_op:
        batch_op.drop_column("last_used_at")
        batch_op.drop_column("usage_count")
        batch_op.drop_column("is_active")
