# plan: docs/plans/community_job_runner_plan.md
"""Durable execution history for the eight community jobs."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow


class JobRun(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_name_started", "job_name", "started_at"),
        Index("ix_job_runs_user_name_started", "user_id", "job_name", "started_at"),
    )

    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_name: Mapped[str] = mapped_column(String(32), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
