"""Add durable job registry and health-check history.

# plan: docs/plans/community_job_runner_plan.md
Revision ID: 0016
Revises: 0015
"""

from alembic import op
import sqlalchemy as sa


revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("user_id", sa.String(length=32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("job_name", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False),
        sa.Column("counts", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_runs_user_id", "job_runs", ["user_id"])
    op.create_index("ix_job_runs_job_name", "job_runs", ["job_name"])
    op.create_index("ix_job_runs_status", "job_runs", ["status"])
    op.create_index("ix_job_runs_name_started", "job_runs", ["job_name", "started_at"])
    op.create_index("ix_job_runs_user_name_started", "job_runs", ["user_id", "job_name", "started_at"])


def downgrade() -> None:
    for name in (
        "ix_job_runs_user_name_started",
        "ix_job_runs_name_started",
        "ix_job_runs_status",
        "ix_job_runs_job_name",
        "ix_job_runs_user_id",
    ):
        op.drop_index(name, table_name="job_runs")
    op.drop_table("job_runs")
