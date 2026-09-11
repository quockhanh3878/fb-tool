"""
Shooter task — lấy lượt comment trong hàng đợi và đăng lên Facebook.

Ba lớp phanh trước khi bắn:
  1. quota ngày của chiến dịch (đếm theo LƯỢT, kể cả lượt hỏng)
  2. trạng thái clone (chỉ ACTIVE mới được bắn) + hạn mức riêng của clone
  3. giãn cách `clone.next_comment_at` — AdaptiveRateLimiter tính theo khoảng
     delay của chiến dịch, giãn thêm khi tỉ lệ thành công tụt
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import get_session_factory
from app.models.base import as_utc, utcnow
from app.models.campaign import Campaign
from app.models.clone_account import CloneAccount
from app.models.enums import (
    AccountState,
    AccountTransition,
    CloneRole,
    CommentStatus,
    PostStatus,
)
from app.models.post import CommentAction, DiscoveredPost
from app.models.user import User
from app.services.account_manager import AccountManager
from app.services.anti_ban import AdaptiveRateLimiter
from app.services.crypto import decrypt_cookies
from app.services.notification_service import NotificationService
from app.services.pipeline import count_today_actions
from app.workers.browser_runtime import BrowserRuntimeUnavailable, post_comment_real
from app.workers.celery_app import celery_app, run_async

BATCH_SIZE = 5


def clone_can_shoot(clone: CloneAccount, now: datetime | None = None) -> bool:
    """Clone có đủ điều kiện bắn không? (hàm thuần — test offline được)"""
    if clone.status != AccountState.ACTIVE.value:
        return False
    now = now or datetime.now(timezone.utc)
    cooldown = as_utc(clone.cooldown_until)
    if cooldown is not None and cooldown > now:
        return False
    next_comment_at = as_utc(clone.next_comment_at)
    if next_comment_at is not None and next_comment_at > now:
        return False
    today = now.date().isoformat()
    used = clone.daily_comment_count if clone.daily_counter_date == today else 0
    return used < (clone.daily_comment_limit or 20)


async def _pick_shooter(db, user_id: str) -> CloneAccount | None:
    result = await db.execute(
        select(CloneAccount).where(
            CloneAccount.user_id == user_id,
            CloneAccount.role.in_((CloneRole.SHOOTER.value, CloneRole.BOTH.value, CloneRole.ALL.value)),
        )
    )
    for clone in result.scalars().all():
        if clone_can_shoot(clone):
            return clone
    return None


async def _comment_gap(
    limiter: AdaptiveRateLimiter, clone: CloneAccount, campaign: Campaign
) -> int:
    return await limiter.next_delay(
        clone.id,
        delay_min_seconds=campaign.delay_min_seconds,
        delay_max_seconds=campaign.delay_max_seconds,
    )


async def _due_actions() -> list[str]:
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        result = await db.execute(
            select(CommentAction)
            .where(CommentAction.status == CommentStatus.QUEUED.value)
            .order_by(CommentAction.scheduled_at.asc())
            .limit(BATCH_SIZE)
        )
        return [
            action.id
            for action in result.scalars().all()
            if as_utc(action.scheduled_at) is None or as_utc(action.scheduled_at) <= now
        ]


async def _execute(action_id: str) -> dict:
    notifier = NotificationService()
    async with get_session_factory()() as db:
        action = await db.get(CommentAction, action_id)
        if action is None or action.status != CommentStatus.QUEUED.value:
            return {"skipped": "action_not_queued"}

        post = await db.get(DiscoveredPost, action.discovered_post_id)
        campaign = await db.get(Campaign, post.campaign_id) if post else None
        if post is None or campaign is None:
            return {"skipped": "post_missing"}
        user = await db.get(User, campaign.user_id)

        used = await count_today_actions(db, campaign.id)
        if used >= int(campaign.max_comments_per_day or 20):
            return {"skipped": f"campaign_quota:{used}"}

        clone = await db.get(CloneAccount, action.clone_account_id) if action.clone_account_id else None
        if clone is None or not clone_can_shoot(clone):
            clone = await _pick_shooter(db, campaign.user_id)
        if clone is None:
            return {"skipped": "no_available_shooter_clone"}

        manager = AccountManager(db)
        limiter = AdaptiveRateLimiter(db)
        previous_next_comment_at = clone.next_comment_at
        # Giữ chỗ giãn cách NGAY lúc nhận việc: lượt khác chạy song song hay tiến
        # trình chết giữa chừng cũng không bắn tiếp bằng nick này trước hạn.
        clone.next_comment_at = utcnow() + timedelta(
            seconds=await _comment_gap(limiter, clone, campaign)
        )
        action.clone_account_id = clone.id
        action.status = CommentStatus.IN_PROGRESS.value
        action.executed_at = utcnow()
        await db.commit()

        try:
            cookies = decrypt_cookies(clone.cookie_data_encrypted)
        except Exception:
            cookies = None

        try:
            status = await post_comment_real(clone, post.post_url, action.comment_content, cookies)
        except BrowserRuntimeUnavailable as exc:
            action.status = CommentStatus.QUEUED.value  # trả về hàng đợi, không mất việc
            action.error_message = str(exc)
            # Chưa chạm tới Facebook -> trả lại lịch giãn cách cũ của nick.
            clone.next_comment_at = previous_next_comment_at
            await db.commit()
            return {"error": str(exc)}
        except Exception as exc:
            status = CommentStatus.FAILED.value
            action.error_message = str(exc)

        action.status = status
        action.executed_at = utcnow()

        if status == CommentStatus.SUCCESS.value:
            post.status = PostStatus.COMMENTED.value
            post.commented_at = utcnow()
            await manager.record_success(clone)
        else:
            await manager.record_failure(
                clone,
                f"comment {status}: {action.error_message or ''}",
                shadowban=(status == CommentStatus.SHADOWBANNED.value),
            )
            if status == CommentStatus.SHADOWBANNED.value:
                post.status = PostStatus.SKIPPED.value

        # Nhịp bắn kế tiếp do lịch sử thành công quyết định, tính từ lúc comment xong.
        delay = await _comment_gap(limiter, clone, campaign)
        clone.next_comment_at = utcnow() + timedelta(seconds=delay)
        await db.commit()

        if user and user.telegram_chat_id:
            await notifier.send_result_notification(
                user.telegram_chat_id,
                post,
                success=(status == CommentStatus.SUCCESS.value),
                comment_text=action.comment_content,
                error=status,
            )
        return {"action": action_id, "status": status, "next_delay": delay}


async def _wake_quota_exhausted() -> int:
    """Đưa clone đã chạm trần ngày vào cooldown thay vì để nó thử tiếp."""
    async with get_session_factory()() as db:
        result = await db.execute(
            select(CloneAccount).where(CloneAccount.status == AccountState.ACTIVE.value)
        )
        manager = AccountManager(db)
        count = 0
        today = datetime.now(timezone.utc).date().isoformat()
        for clone in result.scalars().all():
            if (
                clone.daily_counter_date == today
                and clone.daily_comment_count >= (clone.daily_comment_limit or 20)
            ):
                await manager.transition(
                    clone, AccountTransition.QUOTA_REACHED, "Đạt trần comment/ngày"
                )
                count += 1
        await db.commit()
        return count


@celery_app.task(name="app.workers.shooter_task.process_comment_queue")
def process_comment_queue() -> dict:
    action_ids = run_async(_due_actions())
    for action_id in action_ids:
        execute_comment.delay(action_id)
    cooled = run_async(_wake_quota_exhausted())
    return {"dispatched": len(action_ids), "cooled_down": cooled}


@celery_app.task(
    name="app.workers.shooter_task.execute_comment",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def execute_comment(self, action_id: str) -> dict:
    return run_async(_execute(action_id))
