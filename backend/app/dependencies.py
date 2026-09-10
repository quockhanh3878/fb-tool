"""
Dependency injection cho FastAPI: xác thực người dùng, rate limit, tài nguyên.
"""
import time
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
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
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Chỉ quản trị viên mới được phép")
    return user


# ── Rate limit đơn giản trong RAM ──────────────────────────────────────────
# Đủ cho 1 tiến trình API. Khi chạy nhiều replica, thay bằng Redis
# (INCR + EXPIRE) — nhưng KHÔNG bỏ trống: /auth là cửa dễ bị dò mật khẩu nhất.
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(bucket: str, limit: int | None = None, window_seconds: int = 60):
    async def dependency(request: Request) -> None:
        max_hits = limit or get_settings().auth_rate_limit_per_minute
        client = request.client.host if request.client else "unknown"
        key = f"{bucket}:{client}"
        now = time.monotonic()
        history = _hits[key]
        while history and now - history[0] > window_seconds:
            history.popleft()
        if len(history) >= max_hits:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Quá nhiều yêu cầu — thử lại sau {window_seconds} giây",
            )
        history.append(now)

    return dependency


def reset_rate_limits() -> None:
    """Xoá bộ đếm (dùng trong test)."""
    _hits.clear()


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
