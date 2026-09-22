"""Bảng discovered_posts + comment_actions."""
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from app.services.publishing_defaults import (
    DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS,
    default_bump_hours,
)


class PublishingMedia(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tệp ảnh đã nạp cho bài đăng; không lưu bytes trong JSON của PostPublish."""

    __tablename__ = "publishing_media"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    storage_path: Mapped[str] = mapped_column(String(1024))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)


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
    # Facebook comment locator returned after a verified successful submit.
    fb_comment_id: Mapped[str] = mapped_column(String(128), default="")
    comment_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(
        String(20), default=CommentStatus.QUEUED.value, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(64), unique=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    post = relationship("DiscoveredPost", back_populates="actions")


class PostPublishHistory(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable per-group result of a publishing attempt.

    ``PostPublish.publish_results`` remains the response snapshot for backwards
    compatibility; this table is the queryable audit trail and survives deletion
    of the editable publish job.
    """

    __tablename__ = "post_publish_history"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    post_publish_id: Mapped[str | None] = mapped_column(
        ForeignKey("post_publishes.id", ondelete="SET NULL"), index=True
    )
    campaign_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    clone_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("clone_accounts.id", ondelete="SET NULL"), index=True
    )
    group_id: Mapped[str] = mapped_column(String(64), default="")
    group_name: Mapped[str] = mapped_column(String(200), default="")
    group_url: Mapped[str] = mapped_column(String(500), default="")
    post_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    content_snapshot: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    publish = relationship("PostPublish")


class PostPublish(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Bảng post_publishes: Quản lý bài viết đăng mới / lên lịch đăng bài vào các group."""
    __tablename__ = "post_publishes"
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # Tần suất lặp lại (ngày). Campaign có thể cung cấp giá trị mặc định.
    repeat_interval_days: Mapped[int | None] = mapped_column(
        Integer, default=DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS, nullable=True
    )
    # Tự động tạo cmt đẩy bài dưới link đã đăng thành công
    auto_bump: Mapped[bool] = mapped_column(Boolean, default=True)
    # Khung giờ đẩy bài trong ngày; campaign có thể cung cấp giá trị mặc định.
    bump_hours: Mapped[list] = mapped_column(JSON, default=default_bump_hours)

    clone = relationship("CloneAccount")
