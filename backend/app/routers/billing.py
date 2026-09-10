"""
Billing (Phase 4 — Task 4.1): bảng giá, gói hiện tại, nâng cấp/gia hạn.

Cổng thanh toán thật (VNPay/Momo) cắm vào `create_payment_intent`; ở đây
đã có sẵn vòng đời gói cước và hạn mức để phần còn lại chỉ là tích hợp API
của nhà cung cấp.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import as_utc, utcnow
from app.models.enums import PaymentStatus
from app.models.user import Subscription, User
from app.schemas import SubscriptionOut
from app.services.plans import PLANS, get_plan
from app.services.quota import (
    count_user_clones,
    count_user_groups,
    get_subscription,
    is_subscription_active,
)

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PlanOut(BaseModel):
    plan: str
    display_name: str
    price_vnd: int
    max_groups: int
    max_clones: int
    max_comments_per_day: int
    ai_comments_enabled: bool
    bump_enabled: bool


class UsageOut(BaseModel):
    plan: str
    is_active: bool
    expires_at: str | None
    groups_used: int
    groups_limit: int
    clones_used: int
    clones_limit: int


class SubscribeRequest(BaseModel):
    plan: str
    months: int = Field(default=1, ge=1, le=12)


class PaymentIntentOut(BaseModel):
    plan: str
    months: int
    amount_vnd: int
    # Cổng thanh toán thật sẽ trả URL redirect; hiện trả mã tham chiếu để
    # đối soát chuyển khoản thủ công.
    reference_code: str
    instructions: str


@router.get("/plans", response_model=list[PlanOut])
async def list_plans():
    return [PlanOut(**{**spec.__dict__, "plan": spec.plan.value}) for spec in PLANS.values()]


@router.get("/subscription", response_model=SubscriptionOut)
async def current_subscription(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    subscription = await get_subscription(db, user)
    if subscription is None:
        raise HTTPException(status_code=404, detail="Tài khoản chưa có gói cước")
    return subscription


@router.get("/usage", response_model=UsageOut)
async def usage(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    subscription = await get_subscription(db, user)
    spec = get_plan(subscription.plan if subscription else "")
    expires = as_utc(subscription.expires_at) if subscription else None
    return UsageOut(
        plan=subscription.plan if subscription else spec.plan.value,
        is_active=is_subscription_active(subscription),
        expires_at=expires.isoformat() if expires else None,
        groups_used=await count_user_groups(db, user.id),
        groups_limit=subscription.max_groups if subscription else spec.max_groups,
        clones_used=await count_user_clones(db, user.id),
        clones_limit=subscription.max_clones if subscription else spec.max_clones,
    )


@router.post("/subscribe", response_model=PaymentIntentOut)
async def subscribe(
    payload: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tạo yêu cầu thanh toán. Gói CHƯA đổi cho tới khi thanh toán xác nhận."""
    if payload.plan not in PLANS:
        raise HTTPException(status_code=422, detail=f"Gói không tồn tại: {payload.plan}")
    spec = get_plan(payload.plan)

    subscription = await get_subscription(db, user)
    if subscription is None:
        subscription = Subscription(user_id=user.id)
        db.add(subscription)
    subscription.payment_status = PaymentStatus.PENDING.value
    await db.commit()

    reference = f"CH{user.id[:6].upper()}{payload.plan[:2].upper()}{payload.months:02d}"
    return PaymentIntentOut(
        plan=spec.plan.value,
        months=payload.months,
        amount_vnd=spec.price_vnd * payload.months,
        reference_code=reference,
        instructions=(
            f"Chuyển khoản {spec.price_vnd * payload.months:,}đ với nội dung "
            f"'{reference}'. Gói sẽ được kích hoạt sau khi hệ thống đối soát."
        ),
    )


@router.post("/confirm", response_model=SubscriptionOut)
async def confirm_payment(
    payload: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Kích hoạt gói sau khi thanh toán được xác nhận.

    Gia hạn cộng dồn vào hạn cũ nếu gói còn hiệu lực, để khách không mất
    những ngày đã trả tiền khi nâng cấp sớm.
    """
    if payload.plan not in PLANS:
        raise HTTPException(status_code=422, detail=f"Gói không tồn tại: {payload.plan}")
    spec = get_plan(payload.plan)

    subscription = await get_subscription(db, user)
    if subscription is None:
        subscription = Subscription(user_id=user.id)
        db.add(subscription)

    now = utcnow()
    current_expiry = as_utc(subscription.expires_at)
    base = current_expiry if current_expiry and current_expiry > now else now

    subscription.plan = spec.plan.value
    subscription.max_groups = spec.max_groups
    subscription.max_clones = spec.max_clones
    subscription.max_comments_per_day = spec.max_comments_per_day
    subscription.ai_comments_enabled = spec.ai_comments_enabled
    subscription.bump_enabled = spec.bump_enabled
    subscription.started_at = subscription.started_at or now
    subscription.expires_at = base + timedelta(days=30 * payload.months)
    subscription.payment_status = PaymentStatus.ACTIVE.value

    user.tier = spec.plan.value
    await db.commit()
    await db.refresh(subscription)
    return subscription
