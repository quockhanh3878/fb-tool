"""
Dependency injection cho FastAPI: xác thực người dùng, rate limit, tài nguyên.
"""
import time
import hashlib
import ipaddress
import secrets
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.campaign import Campaign, CampaignGroup, CommentScript
from app.models.clone_account import CloneAccount
from app.models.user import User
from app.security import ACCESS_TOKEN_TYPE, TokenError, decode_token

bearer_scheme = HTTPBearer(auto_error=False)


def require_desktop_client(request: Request) -> None:
    settings = get_settings()
    if settings.run_mode != "desktop":
        return
    try:
        local = bool(request.client and ipaddress.ip_address(request.client.host).is_loopback)
    except ValueError:
        local = False
    origin = request.headers.get("origin")
    if not local or (origin is not None and origin not in settings.cors_origins):
        raise HTTPException(status_code=403, detail="Desktop client authentication required")
    if settings.auth_required:
        supplied = request.headers.get("x-desktop-instance-secret", "")
        if (
            not settings.desktop_instance_secret
            or not secrets.compare_digest(supplied, settings.desktop_instance_secret)
        ):
            raise HTTPException(status_code=403, detail="Desktop client authentication required")


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    require_desktop_client(request)
    settings = get_settings()
    if not settings.auth_required:
        if settings.run_mode != "desktop":
            raise HTTPException(status_code=500, detail="Invalid unauthenticated runtime mode")
        from app.services.desktop_service import ensure_desktop_user

        return await ensure_desktop_user(db)
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_token(credentials.credentials, ACCESS_TOKEN_TYPE)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tài khoản không tồn tại hoặc đã bị khoá",
        )
    if settings.run_mode == "desktop":
        from app.services.desktop_service import DESKTOP_USER_EMAIL

        if user.email != DESKTOP_USER_EMAIL:
            raise HTTPException(status_code=403, detail="Desktop principal required")
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên mới được phép")
    return user


# ── Rate limit đơn giản trong RAM ──────────────────────────────────────────
# Đủ cho 1 tiến trình API. Khi chạy nhiều replica, thay bằng Redis
# (INCR + EXPIRE) — nhưng KHÔNG bỏ trống: /auth là cửa dễ bị dò mật khẩu nhất.
_hits: dict[str, deque] = defaultdict(deque)
_windows: dict[str, int] = {}


async def enforce_rate_limit(key: str, max_hits: int, window_seconds: int = 60) -> None:
    settings = get_settings()
    if settings.app_env == "production" and settings.run_mode == "saas":
        from redis.asyncio import Redis

        redis_key = "commhunter:limit:" + hashlib.sha256(key.encode()).hexdigest()
        script = (
            "local n = redis.call('INCR', KEYS[1]); "
            "if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end; return n"
        )
        try:
            async with Redis.from_url(settings.redis_url) as client:
                hits = await client.eval(script, 1, redis_key, window_seconds)
        except Exception:
            raise HTTPException(status_code=503, detail="Rate limiter unavailable") from None
        exceeded = hits > max_hits
    else:
        now = time.monotonic()
        for stale_key in list(_hits):
            if not _hits[stale_key] or now - _hits[stale_key][-1] > _windows.get(stale_key, 60):
                del _hits[stale_key]
                _windows.pop(stale_key, None)
        if key not in _hits and len(_hits) >= 10000:
            raise HTTPException(status_code=429, detail="Rate limiter capacity reached")
        history = _hits[key]
        _windows[key] = window_seconds
        while history and now - history[0] >= window_seconds:
            history.popleft()
        exceeded = len(history) >= max_hits
        if not exceeded:
            history.append(now)
    if exceeded:
        raise HTTPException(
            status_code=429, detail="Quá nhiều yêu cầu",
            headers={"Retry-After": str(window_seconds)},
        )


def rate_limit(bucket: str, limit: int | None = None, window_seconds: int = 60):
    async def dependency(request: Request) -> None:
        max_hits = limit or get_settings().auth_rate_limit_per_minute
        client = request.client.host if request.client else "unknown"
        key = f"{bucket}:{client}"
        await enforce_rate_limit(key, max_hits, window_seconds)

    return dependency


def reset_rate_limits() -> None:
    """Xoá bộ đếm (dùng trong test)."""
    _hits.clear()
    _windows.clear()


# ── Truy xuất tài nguyên có kiểm tra quyền sở hữu ──────────────────────────
async def owned_campaign(
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Campaign:
    campaign = await db.get(Campaign, campaign_id)
    # Trả 404 (không phải 403) cho tài nguyên của người khác: không tiết lộ
    # rằng id đó có tồn tại.
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    return campaign


async def owned_clone(
    clone_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CloneAccount:
    clone = await db.get(CloneAccount, clone_id)
    if clone is None or clone.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy clone")
    return clone


async def owned_group(
    group_id: str,
    campaign: Campaign = Depends(owned_campaign),
    db: AsyncSession = Depends(get_db),
) -> CampaignGroup:
    group = await db.get(CampaignGroup, group_id)
    if group is None or group.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy group")
    return group


async def owned_script(
    script_id: str,
    campaign: Campaign = Depends(owned_campaign),
    db: AsyncSession = Depends(get_db),
) -> CommentScript:
    script = await db.get(CommentScript, script_id)
    if script is None or script.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy kịch bản")
    return script
