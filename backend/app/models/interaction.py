# plan: docs/plans/community_job_runner_plan.md
"""Durable read-only interactions found on the operator's published posts."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class PageInteraction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Một comment mới trên bài PR của chính khách hàng."""

    __tablename__ = "page_interactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "fb_comment_id",
            name="uq_page_interaction_user_comment",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    post_publish_history_id: Mapped[str | None] = mapped_column(
        ForeignKey("post_publish_history.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    fb_comment_id: Mapped[str] = mapped_column(String(128))
    parent_fb_comment_id: Mapped[str] = mapped_column(String(128), default="")
    author_fb_id: Mapped[str] = mapped_column(String(32), default="")
    author_name: Mapped[str] = mapped_column(String(160), default="")
    comment_text: Mapped[str] = mapped_column(Text, default="")
    post_url: Mapped[str] = mapped_column(String(500), default="")
    comment_url: Mapped[str] = mapped_column(String(500), default="")
    commented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
