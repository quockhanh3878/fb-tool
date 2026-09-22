"""
Mã hoá cookie clone trước khi ghi xuống database.

Cookie Facebook tương đương mật khẩu: lộ DB là mất tài khoản khách hàng.
Dùng Fernet (AES-128-CBC + HMAC) với khoá lấy từ env COOKIE_ENCRYPTION_KEY.
Khóa phải bền vững và được cấp từ bên ngoài database cho mọi tiến trình.
"""
import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CookieDecryptError(Exception):
    """Không giải mã được cookie (sai khoá hoặc dữ liệu hỏng)."""


@lru_cache
def _fernet() -> Fernet:
    settings = get_settings()
    key = settings.cookie_encryption_key.strip()
    if not key:
        raise ValueError("COOKIE_ENCRYPTION_KEY is required")
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_cookies(cookies: list | dict) -> str:
    """Serialise + mã hoá cookie thành chuỗi lưu được trong cột Text."""
    raw = json.dumps(cookies, ensure_ascii=False).encode("utf-8")
    return _fernet().encrypt(raw).decode("utf-8")


def decrypt_cookies(blob: str | None) -> list | dict | None:
    """Giải mã cookie. Trả về None nếu chưa có, ném CookieDecryptError nếu hỏng."""
    if not blob:
        return None
    try:
        raw = _fernet().decrypt(blob.encode("utf-8"))
    except InvalidToken as exc:
        raise CookieDecryptError(
            "Không giải mã được cookie — COOKIE_ENCRYPTION_KEY có thể đã đổi"
        ) from exc
    return json.loads(raw.decode("utf-8"))
