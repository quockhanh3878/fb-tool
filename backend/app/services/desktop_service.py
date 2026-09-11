# plan: docs/plans/desktop_packaging.md
"""
Seed user mặc định + auto-login cho chế độ desktop (RUN_MODE=desktop).

Máy khách chỉ có 1 người dùng — không bắt khách đăng ký/gõ email-password.
Lần đầu chạy: tạo sẵn 1 user + subscription hạn mức rộng (Studio, hết hạn xa)
để không bao giờ chặn quota; các lần sau tái dùng đúng user đó.
"""
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.enums import PaymentStatus, SubscriptionPlan
from app.models.user import Subscription, User
from app.security import hash_password
from app.services.plans import get_plan

DESKTOP_USER_EMAIL = "khach@local.commhunter"
DESKTOP_SUBSCRIPTION_YEARS = 100


async def ensure_desktop_user(db: AsyncSession) -> User:
    """Trả về user desktop duy nhất, tạo mới nếu DB rỗng (idempotent)."""
    result = await db.execute(select(User).where(User.email == DESKTOP_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        email=DESKTOP_USER_EMAIL,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        display_name="Khách",
        tier=SubscriptionPlan.STUDIO.value,
    )
    db.add(user)
    await db.flush()

    spec = get_plan(SubscriptionPlan.STUDIO.value)
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
            expires_at=utcnow() + timedelta(days=365 * DESKTOP_SUBSCRIPTION_YEARS),
            payment_status=PaymentStatus.ACTIVE.value,
        )
    )
    await db.commit()
    await db.refresh(user)
    return user
