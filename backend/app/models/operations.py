"""Durable records for authorization, payments and delivery."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class PaymentOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payment_orders"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    months: Mapped[int] = mapped_column(Integer)
    amount_vnd: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    transaction_reference: Mapped[str | None] = mapped_column(String(160), unique=True)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ResourceLease(Base):
    __tablename__ = "resource_leases"

    resource: Mapped[str] = mapped_column(String(160), primary_key=True)
    owner: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class NotificationOutbox(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notification_outbox"

    dedup_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    channel: Mapped[str] = mapped_column(String(24), default="telegram", server_default="telegram")
    chat_id: Mapped[str] = mapped_column(String(64))
    bot_scope: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    post_id: Mapped[str | None] = mapped_column(ForeignKey("discovered_posts.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class NotificationRecipient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Người nhận thông báo theo từng khách hàng và kênh."""

    __tablename__ = "notification_recipients"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "channel", "recipient_id",
            name="uq_notification_recipient_target",
        ),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(24))
    recipient_id: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(120), default="")
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(24), default="manual")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
