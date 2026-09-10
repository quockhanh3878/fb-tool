"""Bảng users + subscriptions."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import PaymentStatus, SubscriptionPlan, UserTier


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # Mã dùng 1 lần để người dùng gõ trong Telegram nhằm liên kết chat_id.
    telegram_link_code: Mapped[str | None] = mapped_column(String(16), index=True)
    tier: Mapped[str] = mapped_column(String(20), default=UserTier.STARTER.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)

    campaigns = relationship(
        "Campaign", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    clones = relationship(
        "CloneAccount", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    subscription = relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class Subscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "subscriptions"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    plan: Mapped[str] = mapped_column(String(20), default=SubscriptionPlan.STARTER.value)
    max_groups: Mapped[int] = mapped_column(Integer, default=5)
    max_clones: Mapped[int] = mapped_column(Integer, default=1)
    max_comments_per_day: Mapped[int] = mapped_column(Integer, default=20)
    ai_comments_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    bump_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_status: Mapped[str] = mapped_column(
        String(20), default=PaymentStatus.ACTIVE.value
    )

    user = relationship("User", back_populates="subscription")
