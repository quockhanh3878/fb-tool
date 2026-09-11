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

OPENAI_API_KEY = "openai_api_key"
TELEGRAM_BOT_TOKEN = "telegram_bot_token"
COOKIE_ENCRYPTION_KEY = "cookie_encryption_key"

# Khoá cấu hình được phép sửa qua màn "Cài đặt" (không lộ cookie_encryption_key
# ra API — tự sinh + lưu ngầm, khách không cần thấy/đổi).
EDITABLE_KEYS = (OPENAI_API_KEY, TELEGRAM_BOT_TOKEN)


async def get_value(db: AsyncSession, key: str) -> str:
    row = await db.get(AppSetting, key)
    return row.value if row else ""


async def set_value(db: AsyncSession, key: str, value: str) -> None:
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value


async def ensure_cookie_key(db: AsyncSession) -> str:
    """Sinh 1 lần + lưu bền khoá Fernet cho desktop — khác RAM tạm của SaaS dev.
    Không sinh lại nếu đã có, nếu không cookie cũ đã mã hoá sẽ không giải được."""
    existing = await get_value(db, COOKIE_ENCRYPTION_KEY)
    if existing:
        return existing
    key = Fernet.generate_key().decode()
    await set_value(db, COOKIE_ENCRYPTION_KEY, key)
    await db.commit()
    return key


async def apply_to_runtime_settings(db: AsyncSession) -> None:
    """Nạp cấu hình DB vào Settings singleton — gọi 1 lần lúc khởi động
    RUN_MODE=desktop (app/main.py lifespan), TRƯỚC khi có request/nghiệp vụ nào
    chạy (đặc biệt trước lần gọi services/crypto.py đầu tiên)."""
    settings = get_settings()
    settings.cookie_encryption_key = await ensure_cookie_key(db)

    openai_key = await get_value(db, OPENAI_API_KEY)
    if openai_key:
        settings.openai_api_key = openai_key

    telegram_token = await get_value(db, TELEGRAM_BOT_TOKEN)
    if telegram_token:
        settings.telegram_bot_token = telegram_token
