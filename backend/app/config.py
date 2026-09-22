"""
Cấu hình ứng dụng — đọc toàn bộ từ biến môi trường (.env).

Nguyên tắc: KHÔNG hardcode bí mật trong mã nguồn. Mọi giá trị nhạy cảm
(DB password, JWT secret, khoá mã hoá cookie, token Telegram/OpenAI) đều
đến từ env để container hoá và xoay khoá được mà không sửa code.
"""
import base64
import binascii
from functools import lru_cache
from typing import List, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    # ── Ứng dụng ────────────────────────────────────────────────────────
    app_name: str = "CommHunter AI API"
    app_version: str = "2.0.0"
    debug: bool = False
    app_env: Literal["development", "test", "production"] = "development"

    # "saas" (mặc định, hiện tại): Celery+Redis xử lý nền, nhiều tiến trình.
    # "desktop": APScheduler + SerialJobQueue chạy ngay trong tiến trình API
    # (xem app/workers/scheduler.py) — dùng cho app đóng gói chạy 1 máy/1 khách.
    run_mode: Literal["saas", "desktop"] = "saas"
    # Desktop local có thể tự seed principal duy nhất, không hiện màn login.
    # SaaS luôn giữ auth bắt buộc, kể cả khi biến này bị đặt sai.
    auth_required: bool = True

    # ── Database ────────────────────────────────────────────────────────
    # Dev/test dùng SQLite; production dùng PostgreSQL:
    #   postgresql+asyncpg://commhunter:pass@db:5432/commhunter
    database_url: str = "sqlite+aiosqlite:///./data/commhunter_api.db"

    # ── Redis / Celery ──────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Bảo mật ─────────────────────────────────────────────────────────
    jwt_secret: str = Field(default="", repr=False)
    jwt_algorithm: Literal["HS256"] = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Khoá Fernet để mã hoá cookie clone lưu trong DB.
    cookie_encryption_key: str = Field(default="", repr=False)
    desktop_instance_secret: str = Field(default="", repr=False)

    # ── Rate limit ──────────────────────────────────────────────────────
    auth_rate_limit_per_minute: int = 5

    # ── CORS ────────────────────────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # ── Tích hợp ngoài ──────────────────────────────────────────────────
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4o-mini"
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_webhook_secret: str = Field(default="", repr=False)
    max_request_bytes: int = Field(default=3 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    max_pending_per_user: int = Field(default=100, ge=1, le=1000)
    ai_calls_per_user_per_day: int = Field(default=200, ge=0, le=10000)
    browser_operation_timeout_seconds: int = Field(default=1200, ge=30, le=1800)
    job_lease_seconds: int = Field(default=2100, ge=1900, le=7200)

    # ── Runtime ─────────────────────────────────────────────────────────
    browser_profiles_root: str = "data/browser_profiles"
    publishing_media_root: str = "data/publishing_media"
    browser_automation_enabled: bool = False

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

    @model_validator(mode="after")
    def validate_security(self):
        weak_markers = ("dev-secret", "doi-khoa", "doi-truoc", "change-me", "changeme")
        if len(self.jwt_secret.encode()) < 32 or any(
            marker in self.jwt_secret.lower() for marker in weak_markers
        ):
            raise ValueError("JWT_SECRET must be a unique secret of at least 32 bytes")
        try:
            decoded = base64.b64decode(
                self.cookie_encryption_key.encode("ascii"), altchars=b"-_", validate=True
            )
        except (ValueError, UnicodeError, binascii.Error):
            decoded = b""
        if len(decoded) != 32:
            raise ValueError("COOKIE_ENCRYPTION_KEY must be a persistent Fernet key")
        if not self.auth_required and self.run_mode != "desktop":
            raise ValueError("AUTH_REQUIRED=false chỉ được phép ở chế độ desktop")
        if self.run_mode == "desktop" and self.auth_required and len(self.desktop_instance_secret.encode()) < 32:
            raise ValueError("Desktop mode requires DESKTOP_INSTANCE_SECRET (32+ bytes)")
        if self.run_mode == "saas" and self.browser_cdp_endpoint:
            raise ValueError("Shared CDP sessions are not allowed in SaaS mode")
        if self.run_mode == "saas" and self.telegram_bot_token and not self.telegram_webhook_secret:
            raise ValueError("Telegram webhook requires TELEGRAM_WEBHOOK_SECRET")
        if self.app_env == "production" and self.debug:
            raise ValueError("DEBUG must be disabled in production")
        if any(origin == "*" for origin in self.cors_origins):
            raise ValueError("CORS_ORIGINS must list explicit origins")
        return self


@lru_cache
def get_settings() -> Settings:
    """Settings là singleton — đọc env đúng 1 lần cho cả tiến trình."""
    return Settings()
