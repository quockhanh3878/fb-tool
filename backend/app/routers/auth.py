"""Đăng ký / đăng nhập / refresh / hồ sơ người dùng."""
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, rate_limit
from app.models.base import utcnow
from app.models.enums import PaymentStatus
from app.models.user import Subscription, User
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
from app.services.plans import DEFAULT_PLAN, get_plan

router = APIRouter(prefix="/api/auth", tags=["auth"])

TRIAL_DAYS = 7


def _token_pair(user: User) -> TokenPair:
    settings = get_settings()
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
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
    email = payload.email.lower().strip()
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email đã được đăng ký")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
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
    return _token_pair(user)


@router.post(
    "/login", response_model=TokenPair, dependencies=[Depends(rate_limit("login"))]
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email.lower().strip()))
    user = result.scalar_one_or_none()
    # Cùng một thông báo cho email sai lẫn mật khẩu sai: không giúp kẻ dò
    # biết email nào có thật.
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Email hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khoá")
    return _token_pair(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        user_id = decode_token(payload.refresh_token, REFRESH_TOKEN_TYPE)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Tài khoản không hợp lệ")
    return _token_pair(user)


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
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/connect-telegram", response_model=TelegramLinkOut)
async def connect_telegram(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Sinh mã liên kết; người dùng gửi `/start <mã>` cho bot để gắn chat_id."""
    code = secrets.token_hex(4).upper()
    user.telegram_link_code = code
    await db.commit()
    return TelegramLinkOut(
        link_code=code,
        instructions=(
            "Mở Telegram, chat với bot CommHunter và gửi lệnh: "
            f"/start {code} — hệ thống sẽ tự gắn tài khoản của bạn."
        ),
    )
