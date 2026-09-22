"""Durable comment admission, clone exclusion and conservative recovery."""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update

from app.config import get_settings
from app.database import get_session_factory
from app.models.base import as_utc, utcnow
from app.models.campaign import Campaign
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, AccountTransition, CloneRole, CommentStatus, PostStatus
from app.models.post import CommentAction, DiscoveredPost
from app.models.user import User
from app.services.account_manager import AccountManager
from app.services.anti_ban import AdaptiveRateLimiter
from app.services.crypto import CookieDecryptError, decrypt_cookies
from app.services.execution_policy import check_comment_capacity, lock_user, require_comment_policy, require_owned_clone
from app.services.leases import LeaseBusy, resource_lease
from app.services.outbox_service import queue_text
from app.workers.browser_runtime import BrowserRuntimeUnavailable, post_comment_real
from app.workers.celery_app import celery_app, run_async

BATCH_SIZE = 5


def clone_can_shoot(clone: CloneAccount, now: datetime | None = None) -> bool:
    if clone.status != AccountState.ACTIVE.value:
        return False
    now = now or utcnow()
    for deadline in (clone.cooldown_until, clone.next_comment_at):
        if as_utc(deadline) is not None and as_utc(deadline) > now:
            return False
    used = clone.daily_comment_count if clone.daily_counter_date == now.date().isoformat() else 0
    return used < (clone.daily_comment_limit or 20)


async def _pick_shooter(db, user_id: str) -> CloneAccount | None:
    result = await db.execute(select(CloneAccount).where(
        CloneAccount.user_id == user_id,
        CloneAccount.role.in_((CloneRole.SHOOTER.value, CloneRole.BOTH.value, CloneRole.ALL.value)),
    ).order_by(CloneAccount.last_activity_at.asc().nulls_first()))
    return next((clone for clone in result.scalars() if clone_can_shoot(clone)), None)


async def _comment_gap(limiter, clone, campaign) -> int:
    return await limiter.next_delay(
        clone.id, delay_min_seconds=campaign.delay_min_seconds,
        delay_max_seconds=campaign.delay_max_seconds,
    )


async def _due_actions() -> list[str]:
    now = utcnow()
    ranked = select(
        CommentAction.id,
        CommentAction.scheduled_at,
        func.row_number().over(
            partition_by=Campaign.user_id,
            order_by=(CommentAction.scheduled_at.asc(), CommentAction.id.asc()),
        ).label("tenant_rank"),
    ).join(DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id).join(
        Campaign, Campaign.id == DiscoveredPost.campaign_id,
    ).where(
        CommentAction.status == CommentStatus.QUEUED.value,
        or_(CommentAction.scheduled_at.is_(None), CommentAction.scheduled_at <= now),
    ).subquery()
    async with get_session_factory()() as db:
        return list((await db.scalars(select(ranked.c.id).where(
            ranked.c.tenant_rank == 1,
        ).order_by(ranked.c.scheduled_at.asc()).limit(BATCH_SIZE))).all())


async def _defer(db, action, reason, seconds=60):
    action.status = CommentStatus.QUEUED.value
    action.scheduled_at = utcnow() + timedelta(seconds=seconds)
    action.executed_at = None
    action.lease_expires_at = None
    action.error_message = reason
    await db.commit()
    return {"deferred": reason}


async def _execute(action_id: str) -> dict:
    async with get_session_factory()() as db:
        action = await db.get(CommentAction, action_id)
        if action is None or action.status != CommentStatus.QUEUED.value:
            return {"skipped": "action_not_queued"}
        post = await db.get(DiscoveredPost, action.discovered_post_id)
        campaign = await db.get(Campaign, post.campaign_id) if post else None
        if post is None or campaign is None:
            return {"skipped": "post_missing"}
        await lock_user(db, campaign.user_id)
        await db.refresh(action)
        if action.status != CommentStatus.QUEUED.value:
            return {"skipped": "already_claimed"}
        if as_utc(action.scheduled_at) is not None and as_utc(action.scheduled_at) > utcnow():
            return {"skipped": "not_due"}
        try:
            subscription = await require_comment_policy(
                db, campaign, post, action.clone_account_id,
                allow_completed=(action.idempotency_key or "").startswith("bump:"),
            )
            await check_comment_capacity(db, campaign, subscription, exclude_id=action.id, reserve=False)
            clone = (
                await require_owned_clone(db, action.clone_account_id, campaign.user_id)
                if action.clone_account_id else await _pick_shooter(db, campaign.user_id)
            )
        except HTTPException as exc:
            if exc.status_code == 429:
                return await _defer(db, action, "daily_quota", 3600)
            action.status = CommentStatus.CANCELLED.value
            action.error_message = str(exc.detail)
            await db.commit()
            return {"skipped": "policy_denied"}
        if clone is None or not clone_can_shoot(clone):
            return await _defer(db, action, "no_available_shooter")
        claimed = await db.execute(update(CommentAction).where(
            CommentAction.id == action.id, CommentAction.status == CommentStatus.QUEUED.value,
        ).values(
            status=CommentStatus.IN_PROGRESS.value, clone_account_id=clone.id,
            executed_at=utcnow(), lease_expires_at=utcnow() + timedelta(seconds=get_settings().job_lease_seconds),
        ))
        if claimed.rowcount != 1:
            await db.rollback()
            return {"skipped": "already_claimed"}
        await db.commit()
        try:
            async with resource_lease(f"clone:{clone.id}"):
                return await _run_claimed(db, action, post, campaign, clone)
        except LeaseBusy:
            return await _defer(db, action, "clone_busy")


async def _run_claimed(db, action, post, campaign, clone):
    await db.refresh(clone)
    if not clone_can_shoot(clone):
        return await _defer(db, action, "clone_not_ready")
    try:
        await lock_user(db, campaign.user_id)
        await require_comment_policy(
            db, campaign, post, clone.id,
            allow_completed=(action.idempotency_key or "").startswith("bump:"),
        )
    except HTTPException as exc:
        action.status = CommentStatus.CANCELLED.value
        action.error_message = str(exc.detail)
        action.executed_at = None
        action.lease_expires_at = None
        await db.commit()
        return {"skipped": "policy_denied"}
    limiter = AdaptiveRateLimiter(db)
    clone.next_comment_at = utcnow() + timedelta(seconds=await _comment_gap(limiter, clone, campaign))
    await db.commit()
    try:
        cookies = decrypt_cookies(clone.cookie_data_encrypted)
    except CookieDecryptError:
        action.status = CommentStatus.FAILED.value
        action.error_message = "cookie_decryption_failed"
        action.lease_expires_at = None
        await db.commit()
        return {"error": "cookie_decryption_failed"}
    try:
        outcome = await post_comment_real(clone, post.post_url, action.comment_content, cookies)
    except BrowserRuntimeUnavailable:
        return await _defer(db, action, "browser_unavailable", 300)
    except Exception:
        outcome = CommentStatus.UNKNOWN_OUTCOME.value
        action.error_message = "browser_outcome_unknown; review before retry"
    # Runtime cũ trả về chuỗi; runtime mới có thể trả thêm locator Facebook.
    details = outcome if isinstance(outcome, dict) else {}
    outcome = details.get("status") if details else outcome
    if outcome not in {member.value for member in CommentStatus}:
        outcome = CommentStatus.UNKNOWN_OUTCOME.value
    action.fb_comment_id = str(details.get("fb_comment_id") or "")
    action.comment_url = str(details.get("comment_url") or "")
    action.status = outcome
    action.executed_at = utcnow()
    action.lease_expires_at = None
    manager = AccountManager(db)
    if outcome == CommentStatus.SUCCESS.value:
        post.status = PostStatus.COMMENTED.value
        post.commented_at = utcnow()
        await manager.record_success(clone)
    else:
        await manager.record_failure(clone, "Comment did not complete", shadowban=(outcome == CommentStatus.SHADOWBANNED.value))
    delay = await _comment_gap(limiter, clone, campaign)
    clone.next_comment_at = utcnow() + timedelta(seconds=delay)
    user = await db.get(User, campaign.user_id)
    if user and user.telegram_chat_id:
        await queue_text(db, user.telegram_chat_id, f"Kết quả comment: {outcome}", key=f"comment-result:{action.id}")
    await db.commit()
    return {"action": action.id, "status": outcome, "next_delay": delay}


async def _wake_quota_exhausted() -> int:
    async with get_session_factory()() as db:
        result = await db.execute(select(CloneAccount).where(CloneAccount.status == AccountState.ACTIVE.value))
        manager = AccountManager(db)
        count = 0
        today = utcnow().date().isoformat()
        for clone in result.scalars():
            if clone.daily_counter_date == today and clone.daily_comment_count >= (clone.daily_comment_limit or 20):
                await manager.transition(clone, AccountTransition.QUOTA_REACHED, "Đạt trần comment/ngày")
                count += 1
        await db.commit()
        return count


@celery_app.task(name="app.workers.shooter_task.process_comment_queue")
def process_comment_queue() -> dict:
    action_ids = run_async(_due_actions())
    for action_id in action_ids:
        execute_comment.delay(action_id)
    return {"dispatched": len(action_ids), "cooled_down": run_async(_wake_quota_exhausted())}


@celery_app.task(name="app.workers.shooter_task.execute_comment")
def execute_comment(action_id: str) -> dict:
    return run_async(_execute(action_id))
