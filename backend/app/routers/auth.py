"""Đăng ký / đăng nhập / refresh / hồ sơ người dùng."""
import secrets
import asyncio
import hashlib
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import enforce_rate_limit, get_current_user, rate_limit, require_desktop_client
from app.models.base import as_utc, new_uuid, utcnow
from app.models.enums import PaymentStatus
from app.models.user import Subscription, User
from app.models.operations import RefreshSession
from app.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TelegramLinkOut,
    TokenPair,
    UserOut,
    UserUpdate,
)
from app.security import (
    REFRESH_TOKEN_TYPE,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.services.desktop_service import ensure_desktop_user
from app.services.plans import DEFAULT_PLAN, get_plan

router = APIRouter(prefix="/api/auth", tags=["auth"])

TRIAL_DAYS = 7


async def _token_pair(user: User, db: AsyncSession, family_id: str | None = None) -> TokenPair:
    settings = get_settings()
    refresh_token = create_refresh_token(user.id)
    db.add(RefreshSession(
        token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
        user_id=user.id,
        family_id=family_id or new_uuid(),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
    ))
    await db.commit()
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
    )


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register"))],
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Tạo tài khoản mới kèm gói dùng thử Starter 7 ngày."""
    if get_settings().run_mode == "desktop":
        raise HTTPException(status_code=404, detail="Not Found")
    email = payload.email.lower().strip()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email đã được đăng ký")

    user = User(
        email=email,
        hashed_password=await asyncio.to_thread(hash_password, payload.password),
        display_name=payload.display_name or email.split("@")[0],
        tier=DEFAULT_PLAN,
    )
    db.add(user)
    await db.flush()

    spec = get_plan(DEFAULT_PLAN)
    db.add(
        Subscription(
            user_id=user.id,
            plan=spec.plan.value,
            max_groups=spec.max_groups,
            max_clones=spec.max_clones,
            max_comments_per_day=spec.max_comments_per_day,
            ai_comments_enabled=spec.ai_comments_enabled,
            bump_enabled=spec.bump_enabled,
            started_at=utcnow(),
            expires_at=utcnow() + timedelta(days=TRIAL_DAYS),
            payment_status=PaymentStatus.ACTIVE.value,
        )
    )
    await db.commit()
    return await _token_pair(user, db)


@router.post(
    "/login", response_model=TokenPair, dependencies=[Depends(rate_limit("login"))]
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    if get_settings().run_mode == "desktop":
        raise HTTPException(status_code=404, detail="Not Found")
    await enforce_rate_limit(
        "login-account:" + hashlib.sha256(payload.email.lower().strip().encode()).hexdigest(),
        get_settings().auth_rate_limit_per_minute,
    )
    result = await db.execute(select(User).where(User.email == payload.email.lower().strip()))
    user = result.scalar_one_or_none()
    # Cùng một thông báo cho email sai lẫn mật khẩu sai: không giúp kẻ dò
    # biết email nào có thật.
    if user is None or not await asyncio.to_thread(verify_password, payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khoá")
    return await _token_pair(user, db)


@router.post("/desktop-session", response_model=TokenPair)
async def desktop_session(request: Request, db: AsyncSession = Depends(get_db)):
    """Auto-login cho chế độ desktop (RUN_MODE=desktop): 1 máy = 1 user, khách
    không cần màn đăng nhập. Ở chế độ SaaS endpoint này không tồn tại (404)."""
    if get_settings().run_mode != "desktop":
        raise HTTPException(status_code=404, detail="Not Found")
    require_desktop_client(request)
    user = await ensure_desktop_user(db)
    return await _token_pair(user, db)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(rate_limit("refresh"))])
async def refresh(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    require_desktop_client(request)
    try:
        user_id = decode_token(payload.refresh_token, REFRESH_TOKEN_TYPE)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Tài khoản không hợp lệ")
    await db.execute(update(User).where(User.id == user_id).values(updated_at=User.updated_at))
    token_hash = hashlib.sha256(payload.refresh_token.encode()).hexdigest()
    session = await db.get(RefreshSession, token_hash, populate_existing=True)
    if session is None or session.user_id != user_id or as_utc(session.expires_at) <= utcnow():
        raise HTTPException(status_code=401, detail="Session expired or revoked")
    if session.used_at or session.revoked_at:
        await db.execute(update(RefreshSession).where(
            RefreshSession.family_id == session.family_id,
        ).values(revoked_at=utcnow()))
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; sign in again")
    session.used_at = utcnow()
    return await _token_pair(user, db, session.family_id)


@router.post("/logout", status_code=204)
async def logout(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await db.execute(update(User).where(User.id == user.id).values(updated_at=User.updated_at))
    await db.execute(update(RefreshSession).where(
        RefreshSession.user_id == user.id,
    ).values(revoked_at=utcnow()))
    await db.commit()


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.put("/me", response_model=UserOut)
async def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "display_name" and value is None:
            raise HTTPException(status_code=422, detail="display_name cannot be null")
        if field == "telegram_chat_id":
            user.telegram_link_code = None
            user.telegram_link_expires_at = None
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/connect-telegram", response_model=TelegramLinkOut, dependencies=[Depends(rate_limit("telegram-link"))])
async def connect_telegram(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Sinh mã liên kết; người dùng gửi `/start <mã>` cho bot để gắn chat_id."""
    code = secrets.token_hex(8).upper()
    user.telegram_link_code = code
    user.telegram_link_expires_at = utcnow() + timedelta(minutes=10)
    await db.commit()
    return TelegramLinkOut(
        link_code=code,
        instructions=(
            "Mở Telegram, chat với bot CommHunter và gửi lệnh: "
            f"/start {code} — hệ thống sẽ tự gắn tài khoản của bạn."
        ),
    )
