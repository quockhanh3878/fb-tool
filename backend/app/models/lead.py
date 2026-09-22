# plan: docs/plans/phase2_dashboard_detail.md
"""Bảng comment_leads: "Săn lead qua comment".

Khác bảng ``mentions`` (so khớp từ khoá với NỘI DUNG BÀI VIẾT): bảng này so
khớp từ khoá với NỘI DUNG BÌNH LUẬN dưới bài, giữ lại danh tính người bình
luận (``author_fb_id`` + thời điểm ``commented_at``) để anh Ber chủ động
liên hệ — tách hẳn khỏi luồng "Nhắc tới" thương hiệu.
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.models.enums import LeadStatus


class CommentLead(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "comment_leads"
    # content_hash ưu tiên fb_comment_id (ổn định hơn) — xem lead_service.lead_content_hash.
    __table_args__ = (
        UniqueConstraint("campaign_id", "content_hash", name="uq_lead_campaign_hash"),
    )

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    # Group có thể bị xoá trước lượt quét — giữ lại nội dung, chỉ mất liên kết.
    campaign_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("campaign_groups.id", ondelete="SET NULL"), index=True
    )
    # ID comment thật của Facebook khi bóc được — rỗng thì dedup rơi về content_hash.
    fb_comment_id: Mapped[str] = mapped_column(String(64), default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    matched_keywords: Mapped[list] = mapped_column(JSON, default=list)
    # ID Facebook của người bình luận — dùng để loại trừ chính nick đang quét.
    author_fb_id: Mapped[str] = mapped_column(String(32), default="")
    author_name: Mapped[str] = mapped_column(String(160), default="")
    comment_text: Mapped[str] = mapped_column(Text, default="")
    post_url: Mapped[str] = mapped_column(String(500), default="")
    comment_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default=LeadStatus.NEW.value, index=True)
    # Thời điểm người dùng ĐĂNG comment trên Facebook (khác discovered_at — lúc app bắt được).
    commented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign = relationship("Campaign")
