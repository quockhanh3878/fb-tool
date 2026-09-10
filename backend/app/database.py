"""
Lớp Database — SQLAlchemy 2.0 async.

Hỗ trợ đồng thời:
  • PostgreSQL (production, qua asyncpg)
  • SQLite   (dev/test, qua aiosqlite) — nhờ vậy bộ test chạy offline
    không cần dựng Docker.
"""
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class cho toàn bộ ORM models."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _ensure_sqlite_dir(url: str) -> None:
    """SQLite không tự tạo thư mục cha — tạo trước để tránh lỗi 'unable to open'."""
    if "sqlite" not in url:
        return
    raw = url.split("///")[-1]
    if raw in ("", ":memory:") or raw.startswith(":memory:"):
        return
    Path(raw).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        _ensure_sqlite_dir(url)
        kwargs: dict = {"echo": settings.debug, "future": True}
        if "sqlite" not in url:
            # Pool chỉ có ý nghĩa với PostgreSQL; SQLite dùng pool mặc định.
            kwargs.update(pool_size=10, max_overflow=20, pool_pre_ping=True)
        _engine = create_async_engine(url, **kwargs)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: mở session cho mỗi request, tự đóng khi xong."""
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_models() -> None:
    """Tạo bảng theo metadata (dùng cho dev/test; production dùng Alembic)."""
    from app import models  # noqa: F401  — nạp toàn bộ model vào metadata

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_engine() -> None:
    """Đóng engine (gọi khi shutdown app hoặc kết thúc test)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def reset_engine_cache() -> None:
    """Xoá engine đã cache mà không cần await — dùng trong test setup."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
