# plan: docs/plans/phase2_dashboard_detail.md
"""Bảng mentions: hộp thư "Nhắc tới".

Bài Scout quét được mà có nhắc tên thương hiệu / dịch vụ của khách (khớp
``campaigns.mention_keywords``) được gom vào đây để anh Ber theo dõi và trả
lời tay — tách hẳn khỏi luồng ứng tuyển comment ở ``discovered_posts``.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.models.enums import MentionStatus


class Mention(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "mentions"
    # Dedup theo từng chiến dịch: cùng công thức content_hash với discovered_posts.
    __table_args__ = (
        UniqueConstraint("campaign_id", "content_hash", name="uq_mention_campaign_hash"),
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    # Group/post có thể bị xoá trước lượt nhắc — giữ lại nội dung, chỉ mất liên kết.
    campaign_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_groups.id", ondelete="SET NULL"), index=True
    )
    discovered_post_id: Mapped[str | None] = mapped_column(
        ForeignKey("discovered_posts.id", ondelete="SET NULL"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    matched_keywords: Mapped[list] = mapped_column(JSON, default=list)
    author_name: Mapped[str] = mapped_column(String(160), default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    post_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(
        String(20), default=MentionStatus.NEW.value, index=True
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign = relationship("Campaign")
