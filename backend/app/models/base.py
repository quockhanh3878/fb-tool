"""
Kiểu cột và mixin dùng chung cho mọi ORM model.

Khoá chính là UUID lưu dạng chuỗi 32 ký tự hex: chạy giống hệt nhau trên
PostgreSQL lẫn SQLite, nên bộ test offline phản ánh đúng hành vi production.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


def new_uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    """Thời điểm hiện tại theo UTC, luôn có tzinfo."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Gắn UTC cho datetime naive đọc từ SQLite để so sánh không nổ TypeError."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class UUIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
