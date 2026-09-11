"""Bảng campaigns, campaign_groups, comment_scripts, bump_schedules."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import CampaignMode, GroupStatus, ScriptType


class Campaign(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "campaigns"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    mode: Mapped[str] = mapped_column(String(20), default=CampaignMode.SEMI_AUTO.value)

    # Thông tin dịch vụ để AI viết comment đúng giọng khách hàng.
    service_name: Mapped[str] = mapped_column(String(160), default="")
    service_specialties: Mapped[str] = mapped_column(Text, default="")
    service_strengths: Mapped[str] = mapped_column(Text, default="")
    landing_page_note: Mapped[str] = mapped_column(Text, default="")

    ai_filter_prompt: Mapped[str] = mapped_column(Text, default="")
    # Tuỳ chọn sinh comment bằng AI — mặc định tắt để tiết kiệm chi phí & ưu tiên Spintax.
    ai_comments_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Từ khoá thương hiệu cho hộp thư "Nhắc tới" — rỗng thì tính năng tắt.
    mention_keywords: Mapped[list] = mapped_column(JSON, default=list)
    whitelist_keywords: Mapped[list] = mapped_column(JSON, default=list)
    blacklist_keywords: Mapped[list] = mapped_column(JSON, default=list)
    min_relevance_score: Mapped[float] = mapped_column(Float, default=0.7)
    max_competitor_comments: Mapped[int] = mapped_column(Integer, default=8)

    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    max_comments_per_day: Mapped[int] = mapped_column(Integer, default=20)
    delay_min_seconds: Mapped[int] = mapped_column(Integer, default=300)
    delay_max_seconds: Mapped[int] = mapped_column(Integer, default=900)

    user = relationship("User", back_populates="campaigns")
    groups = relationship(
        "CampaignGroup",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    scripts = relationship(
        "CommentScript",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bump_schedules = relationship(
        "BumpSchedule",
        back_populates="campaign",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CampaignGroup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "campaign_groups"

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    group_url: Mapped[str] = mapped_column(String(500))
    group_key: Mapped[str] = mapped_column(String(120), index=True, default="")
    group_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default=GroupStatus.ACTIVE.value)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=10)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign = relationship("Campaign", back_populates="groups")
    posts = relationship(
        "DiscoveredPost", back_populates="group", cascade="all, delete-orphan"
    )


class CommentScript(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "comment_scripts"

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(20), default=ScriptType.SPINTAX.value)
    template_content: Mapped[str] = mapped_column(Text, default="")
    ai_system_prompt: Mapped[str] = mapped_column(Text, default="")
    attached_media_urls: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    # Tắt tạm một kịch bản mà không phải xoá — giữ lại thống kê đã dùng.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Hai cột dưới phục vụ XOAY VÒNG kịch bản: luôn chọn cái ít dùng nhất /
    # lâu chưa dùng nhất, thay vì bám mãi kịch bản mặc định.
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign = relationship("Campaign", back_populates="scripts")


class BumpSchedule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bump_schedules"

    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True
    )
    target_post_url: Mapped[str] = mapped_column(String(500))
    # Danh sách giờ trong ngày cần bump, ví dụ [8, 12, 20] (giờ địa phương VN).
    cron_schedule: Mapped[list] = mapped_column(JSON, default=list)
    bump_messages: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_bumped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    campaign = relationship("Campaign", back_populates="bump_schedules")
