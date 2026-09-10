"""Bảng discovered_posts + comment_actions."""
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import CommentStatus, PostStatus, PublishStatus


class DiscoveredPost(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "discovered_posts"
    # Dedup theo từng chiến dịch: hai khách khác nhau vẫn được thấy cùng 1 bài,
    # nhưng trong CÙNG một chiến dịch thì bài chỉ vào feed đúng một lần.
    __table_args__ = (
        UniqueConstraint("campaign_id", "content_hash", name="uq_post_campaign_hash"),
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    campaign_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_groups.id", ondelete="CASCADE"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    post_id_fb: Mapped[str] = mapped_column(String(64), default="")
    post_url: Mapped[str] = mapped_column(String(500), default="")
    author_name: Mapped[str] = mapped_column(String(160), default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    existing_comment_count: Mapped[int] = mapped_column(Integer, default=0)
    ai_relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_reason: Mapped[str] = mapped_column(Text, default="")
    ai_extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(
        String(20), default=PostStatus.NEW.value, index=True
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    commented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    group = relationship("CampaignGroup", back_populates="posts")
    actions = relationship(
        "CommentAction", back_populates="post", cascade="all, delete-orphan"
    )


class CommentAction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "comment_actions"

    discovered_post_id: Mapped[str] = mapped_column(
        ForeignKey("discovered_posts.id", ondelete="CASCADE"), index=True
    )
    clone_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("clone_accounts.id", ondelete="SET NULL"), index=True
    )
    comment_script_id: Mapped[str | None] = mapped_column(
        ForeignKey("comment_scripts.id", ondelete="SET NULL")
    )
    comment_content: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(20), default=CommentStatus.QUEUED.value, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )

    post = relationship("DiscoveredPost", back_populates="actions")


class PostPublish(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Bảng post_publishes: Quản lý bài viết đăng mới / lên lịch đăng bài vào các group."""
    __tablename__ = "post_publishes"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    # Clone được giao nhiệm vụ đăng bài (vai trò 'poster' hoặc 'all')
    clone_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("clone_accounts.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="")
    content_template: Mapped[str] = mapped_column(Text)
    media_urls: Mapped[list] = mapped_column(JSON, default=list)
    # Danh sách group đích: [{"group_id": "...", "group_url": "...", "group_name": "..."}]
    target_groups: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String(20), default=PublishStatus.SCHEDULED.value, index=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Kết quả từng group: [{"group_url": "...", "post_url": "...", "status": "...", "error": "...", "published_at": "..."}]
    publish_results: Mapped[list] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)

    clone = relationship("CloneAccount")

