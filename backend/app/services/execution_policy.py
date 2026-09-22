"""Shared authorization and quota admission for API and workers."""
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update

from app.config import get_settings
from app.models.base import utcnow
from app.models.campaign import Campaign
from app.models.clone_account import CloneAccount
from app.models.enums import CloneRole, CommentStatus, PostStatus
from app.models.post import CommentAction, DiscoveredPost
from app.models.user import User
from app.services.quota import get_subscription, is_subscription_active


async def lock_user(db, user_id: str) -> User:
    result = await db.execute(update(User).where(User.id == user_id).values(updated_at=User.updated_at))
    if result.rowcount != 1:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    return await db.get(User, user_id, populate_existing=True)


async def require_entitlement(db, user_id: str, campaign: Campaign | None = None):
    user = await db.get(User, user_id, populate_existing=True)
    if user is None or not user.is_active:
        raise HTTPException(status_code=403, detail="Tài khoản không hoạt động")
    subscription = await get_subscription(db, user)
    if not is_subscription_active(subscription):
        raise HTTPException(status_code=403, detail="Gói cước hết hạn hoặc chưa kích hoạt")
    if campaign is not None:
        if campaign.user_id != user.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
        await db.refresh(campaign)
        if not campaign.is_active:
            raise HTTPException(status_code=409, detail="Chiến dịch đã tạm dừng")
    return subscription


async def require_owned_clone(db, clone_id: str, user_id: str, roles=None):
    clone = await db.get(CloneAccount, clone_id, populate_existing=True)
    if clone is None or clone.user_id != user_id:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản clone")
    allowed = roles or (CloneRole.SHOOTER.value, CloneRole.BOTH.value, CloneRole.ALL.value)
    if clone.role not in allowed:
        raise HTTPException(status_code=422, detail="Vai trò clone không phù hợp")
    return clone


async def require_comment_policy(db, campaign, post, clone_id=None, *, allow_completed=False):
    subscription = await require_entitlement(db, campaign.user_id, campaign)
    await db.refresh(post)
    if post.campaign_id != campaign.id or post.status in (
        PostStatus.SKIPPED.value, PostStatus.EXPIRED.value,
    ) or (post.status == PostStatus.COMMENTED.value and not allow_completed):
        raise HTTPException(status_code=409, detail="Bài viết không còn cho phép comment")
    if clone_id:
        await require_owned_clone(db, clone_id, campaign.user_id)
    return subscription


async def cancel_campaign_jobs(db, campaign):
    from app.models.enums import PublishStatus
    from app.models.post import PostPublish

    await lock_user(db, campaign.user_id)
    post_ids = select(DiscoveredPost.id).where(DiscoveredPost.campaign_id == campaign.id)
    await db.execute(update(CommentAction).where(
        CommentAction.discovered_post_id.in_(post_ids),
        CommentAction.status == CommentStatus.QUEUED.value,
    ).values(status=CommentStatus.CANCELLED.value, error_message="campaign_paused"))
    await db.execute(update(PostPublish).where(
        PostPublish.campaign_id == campaign.id, PostPublish.status == PublishStatus.SCHEDULED.value,
    ).values(status=PublishStatus.CANCELLED.value, error_message="campaign_paused"))


async def check_comment_capacity(db, campaign, subscription, exclude_id=None, reserve=True):
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    pending = CommentAction.status.in_((CommentStatus.QUEUED.value, CommentStatus.IN_PROGRESS.value))
    today = (CommentAction.executed_at >= start) & (CommentAction.executed_at < end)
    counted = or_(today, pending) if reserve else today
    base = select(func.count(CommentAction.id)).join(
        DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id,
    ).join(Campaign, Campaign.id == DiscoveredPost.campaign_id).where(
        Campaign.user_id == campaign.user_id, counted,
    )
    if exclude_id:
        base = base.where(CommentAction.id != exclude_id)
    total = int(await db.scalar(base) or 0)
    campaign_total = int(await db.scalar(base.where(Campaign.id == campaign.id)) or 0)
    if total >= subscription.max_comments_per_day or campaign_total >= campaign.max_comments_per_day:
        raise HTTPException(status_code=429, detail="Đã đạt hạn mức comment; tính cả lượt giữ chỗ")
    if reserve:
        queued = int(await db.scalar(select(func.count(CommentAction.id)).join(
            DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id,
        ).join(Campaign, Campaign.id == DiscoveredPost.campaign_id).where(
            Campaign.user_id == campaign.user_id, pending,
        )) or 0)
        if queued >= get_settings().max_pending_per_user:
            raise HTTPException(status_code=429, detail="Hàng đợi của tài khoản đã đầy")