# plan: docs/plans/desktop_packaging.md
"""
Cấu hình desktop lưu trong DB (bảng app_settings) thay vì .env — khách chỉnh
qua màn "Cài đặt", không tự sửa file. CHỈ dùng khi RUN_MODE=desktop: settings
là singleton toàn tiến trình (get_settings()), an toàn để ghi đè trực tiếp vì
desktop chỉ có đúng 1 người dùng trên 1 máy — SaaS đa khách KHÔNG được dùng
module này để ghi đè settings (sẽ rò rỉ cấu hình giữa các khách).
"""
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.app_setting import AppSetting
from app.services.crypto import _fernet

OPENAI_API_KEY = "openai_api_key"
TELEGRAM_BOT_TOKEN = "telegram_bot_token"
DISCORD_WEBHOOK_URL = "discord_webhook_url"
DISCORD_BOT_TOKEN = "discord_bot_token"
COOKIE_ENCRYPTION_KEY = "cookie_encryption_key"

# Khoá cấu hình được phép sửa qua màn "Cài đặt" (không lộ cookie_encryption_key
# ra API — tự sinh + lưu ngầm, khách không cần thấy/đổi).
EDITABLE_KEYS = (OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, DISCORD_WEBHOOK_URL, DISCORD_BOT_TOKEN)


async def get_value(db: AsyncSession, key: str) -> str:
    if key == COOKIE_ENCRYPTION_KEY:
        return get_settings().cookie_encryption_key
    row = await db.get(AppSetting, key)
    if row is None or not row.value:
        return ""
    if not row.value.startswith("fernet:v1:"):
        raise ValueError("Legacy desktop credentials require startup migration")
    return _fernet().decrypt(row.value.removeprefix("fernet:v1:").encode()).decode()


async def set_value(db: AsyncSession, key: str, value: str) -> None:
    if key not in EDITABLE_KEYS:
        raise ValueError("This credential must be provisioned outside the database")
    encrypted = "fernet:v1:" + _fernet().encrypt(value.encode()).decode() if value else ""
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=encrypted))
    else:
        row.value = encrypted


async def ensure_cookie_key(db: AsyncSession) -> str:
    """Use the externally provisioned key without persisting it in the DB."""
    key = get_settings().cookie_encryption_key
    Fernet(key.encode())
    legacy = await db.get(AppSetting, COOKIE_ENCRYPTION_KEY)
    if legacy is not None:
        if legacy.value != key:
            raise ValueError("Migrate the legacy desktop key before changing COOKIE_ENCRYPTION_KEY")
        await db.delete(legacy)
    return key


async def apply_to_runtime_settings(db: AsyncSession) -> None:
    """Nạp cấu hình DB vào Settings singleton — gọi 1 lần lúc khởi động
    RUN_MODE=desktop (app/main.py lifespan), TRƯỚC khi có request/nghiệp vụ nào
    chạy (đặc biệt trước lần gọi services/crypto.py đầu tiên)."""
    settings = get_settings()
    settings.cookie_encryption_key = await ensure_cookie_key(db)

    for key in EDITABLE_KEYS:
        row = await db.get(AppSetting, key)
        if row is not None and row.value and not row.value.startswith("fernet:v1:"):
            await set_value(db, key, row.value)
    await db.commit()

    openai_key = await get_value(db, OPENAI_API_KEY)
    if openai_key:
        settings.openai_api_key = openai_key

    telegram_token = await get_value(db, TELEGRAM_BOT_TOKEN)
    if telegram_token:
        settings.telegram_bot_token = telegram_token

    discord_webhook_url = await get_value(db, DISCORD_WEBHOOK_URL)
    if discord_webhook_url:
        settings.discord_webhook_url = discord_webhook_url

    discord_bot_token = await get_value(db, DISCORD_BOT_TOKEN)
    if discord_bot_token:
        settings.discord_bot_token = discord_bot_token
