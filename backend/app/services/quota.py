"""
Kiểm tra hạn mức theo gói cước trước khi cho tạo tài nguyên mới.

Mọi router thêm group/clone đều phải đi qua đây. Hết hạn thanh toán thì
tài nguyên hiện có vẫn giữ nguyên, nhưng không được thêm mới và chiến dịch
không được bật — mất dữ liệu khách hàng vì trễ hạn là điều tuyệt đối tránh.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import as_utc
from app.models.campaign import Campaign, CampaignGroup
from app.models.clone_account import CloneAccount
from app.models.enums import PaymentStatus
from app.models.user import Subscription, User
from app.services.plans import PlanSpec, get_plan


class QuotaExceeded(Exception):
    """Vượt hạn mức của gói cước hiện tại."""


class SubscriptionInactive(Exception):
    """Gói cước đã hết hạn hoặc bị huỷ."""


async def get_subscription(db: AsyncSession, user: User) -> Subscription | None:
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    return result.scalar_one_or_none()


def is_subscription_active(subscription: Subscription | None) -> bool:
    if subscription is None:
        return False
    if subscription.payment_status != PaymentStatus.ACTIVE.value:
        return False
    expires_at = as_utc(subscription.expires_at)
    if expires_at is not None and expires_at < datetime.now(timezone.utc):
        return False
    return True


async def require_active_subscription(db: AsyncSession, user: User) -> Subscription:
    subscription = await get_subscription(db, user)
    if not is_subscription_active(subscription):
        raise SubscriptionInactive(
            "Gói cước đã hết hạn hoặc chưa kích hoạt — vui lòng gia hạn để tiếp tục."
        )
    return subscription


async def _count(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar_one() or 0)


async def count_user_groups(db: AsyncSession, user_id: str) -> int:
    stmt = (
        select(func.count(CampaignGroup.id))
        .join(Campaign, Campaign.id == CampaignGroup.campaign_id)
        .where(Campaign.user_id == user_id)
    )
    return await _count(db, stmt)


async def count_user_clones(db: AsyncSession, user_id: str) -> int:
    stmt = select(func.count(CloneAccount.id)).where(CloneAccount.user_id == user_id)
    return await _count(db, stmt)


def _limit(subscription: Subscription | None, spec: PlanSpec, field: str) -> int:
    """Ưu tiên hạn mức ghi trong subscription (cho phép nâng riêng lẻ),
    rơi về hạn mức mặc định của gói nếu chưa đặt."""
    if subscription is not None:
        value = getattr(subscription, field, None)
        if value:
            return int(value)
    return int(getattr(spec, field))


async def ensure_can_add_group(db: AsyncSession, user: User, adding: int = 1) -> None:
    from app.services.execution_policy import lock_user

    await lock_user(db, user.id)
    subscription = await require_active_subscription(db, user)
    spec = get_plan(subscription.plan)
    limit = _limit(subscription, spec, "max_groups")
    current = await count_user_groups(db, user.id)
    if current + adding > limit:
        raise QuotaExceeded(
            f"Gói {spec.display_name} chỉ cho phép {limit} group "
            f"(đang dùng {current}). Nâng cấp gói để thêm."
        )


async def remaining_group_slots(db: AsyncSession, user: User) -> int:
    """Số group user còn được phép thêm theo gói cước hiện tại (>= 0).

    Ném SubscriptionInactive nếu gói hết hạn — luồng gọi phải bắt.
    """
    from app.services.execution_policy import lock_user

    await lock_user(db, user.id)
    subscription = await require_active_subscription(db, user)
    spec = get_plan(subscription.plan)
    limit = _limit(subscription, spec, "max_groups")
    current = await count_user_groups(db, user.id)
    return max(0, limit - current)


async def ensure_can_add_clone(db: AsyncSession, user: User, adding: int = 1) -> None:
    from app.services.execution_policy import lock_user

    await lock_user(db, user.id)
    subscription = await require_active_subscription(db, user)
    spec = get_plan(subscription.plan)
    limit = _limit(subscription, spec, "max_clones")
    current = await count_user_clones(db, user.id)
    if current + adding > limit:
        raise QuotaExceeded(
            f"Gói {spec.display_name} chỉ cho phép {limit} clone "
            f"(đang dùng {current}). Nâng cấp gói để thêm."
        )


async def ensure_bump_enabled(db: AsyncSession, user: User) -> None:
    subscription = await require_active_subscription(db, user)
    spec = get_plan(subscription.plan)
    enabled = spec.bump_enabled or bool(subscription.bump_enabled)
    if not enabled:
        raise QuotaExceeded(
            f"Gói {spec.display_name} chưa có tính năng Bump bài. Nâng lên Pro để dùng."
        )


async def max_comments_per_day(db: AsyncSession, user: User) -> int:
    subscription = await get_subscription(db, user)
    spec = get_plan(subscription.plan if subscription else "")
    return _limit(subscription, spec, "max_comments_per_day")
