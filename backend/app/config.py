"""
Cấu hình ứng dụng — đọc toàn bộ từ biến môi trường (.env).

Nguyên tắc: KHÔNG hardcode bí mật trong mã nguồn. Mọi giá trị nhạy cảm
(DB password, JWT secret, khoá mã hoá cookie, token Telegram/OpenAI) đều
đến từ env để container hoá và xoay khoá được mà không sửa code.
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Ứng dụng ────────────────────────────────────────────────────────
    app_name: str = "CommHunter AI API"
    app_version: str = "2.0.0"
    debug: bool = False

    # ── Database ────────────────────────────────────────────────────────
    # Dev/test dùng SQLite; production dùng PostgreSQL:
    #   postgresql+asyncpg://commhunter:pass@db:5432/commhunter
    database_url: str = "sqlite+aiosqlite:///./data/commhunter_api.db"

    # ── Redis / Celery ──────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Bảo mật ─────────────────────────────────────────────────────────
    jwt_secret: str = "dev-secret-doi-truoc-khi-len-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Khoá Fernet để mã hoá cookie clone lưu trong DB.
    # Rỗng => tự sinh khoá tạm trong RAM (chỉ hợp lệ cho dev/test).
    cookie_encryption_key: str = ""

    # ── Rate limit ──────────────────────────────────────────────────────
    auth_rate_limit_per_minute: int = 5

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ── Tích hợp ngoài ──────────────────────────────────────────────────
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # ── Runtime ─────────────────────────────────────────────────────────
    browser_profiles_root: str = "data/browser_profiles"

    # Địa chỉ CDP để worker attach vào một Chrome đang mở sẵn (ví dụ
    # "http://localhost:9222") thay vì tự mở profile persistent cho từng clone.
    # Chỉ dùng cho dev/test trên máy anh Ber — production để rỗng, mỗi clone
    # chạy profile + vân tay riêng như thiết kế đã chốt.
    browser_cdp_endpoint: str = ""

    # Track D — preflight: khi bật, Scout/Poster mở browser kiểm tra nick còn
    # đăng nhập + không checkpoint TRƯỚC mỗi lượt quét/đăng. Mặc định tắt: thêm
    # một lần mở browser cho mỗi lượt (chậm ~30-60s), chỉ bật khi chạy dài không
    # người trực. Nick không đạt preflight bị dừng qua state machine.
    preflight_before_run: bool = False


@lru_cache
def get_settings() -> Settings:
    """Settings là singleton — đọc env đúng 1 lần cho cả tiến trình."""
    return Settings()
