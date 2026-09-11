# plan: docs/plans/desktop_packaging.md
"""Bảng app_settings — key/value cho chế độ desktop (OpenAI key, Telegram token,
cookie encryption key nhập/qua UI thay vì .env). Chỉ áp dụng khi RUN_MODE=desktop;
chế độ SaaS vẫn đọc thẳng biến môi trường qua Settings."""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
