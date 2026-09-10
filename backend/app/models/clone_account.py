"""Bảng clone_accounts, account_health_logs, proxies (Phase 3)."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import AccountState, CloneRole, ProxyStatus


class CloneAccount(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clone_accounts"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(20), default=CloneRole.SHOOTER.value)
    status: Mapped[str] = mapped_column(String(20), default=AccountState.ONBOARDING.value)
    proxy_address: Mapped[str | None] = mapped_column(String(255))
    browser_profile_path: Mapped[str] = mapped_column(String(500), default="")
    # Cookie được mã hoá Fernet trước khi ghi xuống DB (xem services/crypto.py).
    cookie_data_encrypted: Mapped[str | None] = mapped_column(Text)
    daily_comment_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_comment_limit: Mapped[int] = mapped_column(Integer, default=20)
    daily_post_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_post_limit: Mapped[int] = mapped_column(Integer, default=5)
    daily_counter_date: Mapped[str] = mapped_column(String(10), default="")
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Phase 3: vòng đời & anti-ban ────────────────────────────────────
    warmup_day: Mapped[int] = mapped_column(Integer, default=0)
    warmup_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    is_backup: Mapped[bool] = mapped_column(Boolean, default=False)

    user = relationship("User", back_populates="clones")
    health_logs = relationship(
        "AccountHealthLog",
        back_populates="clone",
        cascade="all, delete-orphan",
        order_by="AccountHealthLog.created_at.desc()",
    )


class AccountHealthLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "account_health_logs"

    clone_account_id: Mapped[str] = mapped_column(
        ForeignKey("clone_accounts.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), index=True)
    details: Mapped[str] = mapped_column(Text, default="")
    from_state: Mapped[str | None] = mapped_column(String(20))
    to_state: Mapped[str | None] = mapped_column(String(20))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    clone = relationship("CloneAccount", back_populates="health_logs")


class Proxy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "proxies"

    address: Mapped[str] = mapped_column(String(255), unique=True)
    type: Mapped[str] = mapped_column(String(20), default="residential")
    country: Mapped[str] = mapped_column(String(8), default="VN")
    status: Mapped[str] = mapped_column(String(20), default=ProxyStatus.AVAILABLE.value)
    owner_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    assigned_to_clone_id: Mapped[str | None] = mapped_column(
        ForeignKey("clone_accounts.id", ondelete="SET NULL"), index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blacklisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blacklist_reason: Mapped[str | None] = mapped_column(Text)
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
