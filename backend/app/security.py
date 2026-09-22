"""
Bảo mật: băm mật khẩu (bcrypt) + phát/kiểm JWT (access & refresh).

Access token sống 15 phút, refresh token 7 ngày. Mỗi token mang claim
`type` để refresh token không thể dùng thay access token và ngược lại.
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import bcrypt
import jwt

from app.config import get_settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

# bcrypt chỉ dùng 72 byte đầu và ném lỗi nếu dài hơn ở một số phiên bản.
_BCRYPT_MAX_BYTES = 72


class TokenError(Exception):
    """Token sai chữ ký, hết hạn, hoặc sai loại."""


def hash_password(password: str) -> str:
    payload = password.encode("utf-8")
    if len(payload) > _BCRYPT_MAX_BYTES:
        raise ValueError("Password must not exceed 72 UTF-8 bytes")
    return bcrypt.hashpw(payload, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), hashed.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def _create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        ACCESS_TOKEN_TYPE,
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    return _create_token(
        user_id,
        REFRESH_TOKEN_TYPE,
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str = ACCESS_TOKEN_TYPE) -> str:
    """Giải mã token và trả về user_id. Ném TokenError nếu không hợp lệ."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "type", "iat", "exp", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token đã hết hạn") from exc
    except jwt.PyJWTError as exc:
        raise TokenError("Token không hợp lệ") from exc

    if payload.get("type") != expected_type:
        raise TokenError(
            f"Sai loại token: cần '{expected_type}', nhận '{payload.get('type')}'"
        )

    subject = payload.get("sub")
    if not subject:
        raise TokenError("Token thiếu claim 'sub'")
    return str(subject)
