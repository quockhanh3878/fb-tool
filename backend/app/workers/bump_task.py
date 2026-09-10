"""
Bump task — tự thả comment "up" bài của chính khách để bài nổi lại trong group.

Quy tắc chống lộ: mỗi khung giờ chỉ bump 1 lần, nội dung xoay vòng ngẫu nhiên
trong danh sách khách soạn sẵn, và bump vẫn tính vào quota comment/ngày.
"""
import random
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.database import get_session_factory
from app.models.base import as_utc, utcnow
from app.models.campaign import BumpSchedule, Campaign
from app.models.enums import CommentStatus, PostStatus
from app.models.post import CommentAction, DiscoveredPost
from app.services.pipeline import compute_content_hash, count_today_actions
from app.services.script_engine import ScriptError, render_spintax, validate_comment
from app.workers.celery_app import celery_app, run_async

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def is_bump_due(bump: BumpSchedule, now: datetime | None = None) -> bool:
    """Đến giờ bump chưa? (hàm thuần — test offline được)

    Đúng giờ trong `cron_schedule` và chưa bump trong CHÍNH giờ đó.
    """
    if not bump.is_active or not bump.cron_schedule:
        return False

    now = (now or datetime.now(timezone.utc)).astimezone(LOCAL_TZ)
    if now.hour not in [int(h) for h in bump.cron_schedule]:
        return False

    last = as_utc(bump.last_bumped_at)
    if last is None:
        return True
    last_local = last.astimezone(LOCAL_TZ)
    return (last_local.date(), last_local.hour) != (now.date(), now.hour)


def pick_message(bump: BumpSchedule, rng: random.Random | None = None) -> str:
    """Chọn 1 nội dung bump; hỗ trợ spintax để mỗi lần một khác."""
    messages = [m for m in (bump.bump_messages or []) if str(m).strip()]
    if not messages:
        return ""
    rng = rng or random
    chosen = str(rng.choice(messages))
    try:
        return render_spintax(chosen, rng) if "{" in chosen else chosen
    except ScriptError:
        return chosen


async def _bump_one(bump_id: str) -> dict:
    async with get_session_factory()() as db:
        bump = await db.get(BumpSchedule, bump_id)
        if bump is None or not is_bump_due(bump):
            return {"skipped": "not_due"}

        campaign = await db.get(Campaign, bump.campaign_id)
        if campaign is None or not campaign.is_active:
            return {"skipped": "campaign_inactive"}

        used = await count_today_actions(db, campaign.id)
        if used >= int(campaign.max_comments_per_day or 20):
            return {"skipped": f"quota:{used}"}

        message = pick_message(bump)
        if not message:
            return {"skipped": "no_bump_message"}
        try:
            message = validate_comment(message, min_words=1)
        except ScriptError as exc:
            return {"skipped": f"invalid_message: {exc}"}

        # Bài bump là bài của chính khách nên không đi qua Scout; tạo bản ghi
        # DiscoveredPost tối thiểu để hàng đợi comment có chỗ móc vào.
        content_hash = compute_content_hash("bump", bump.target_post_url)
        existing = await db.execute(
            select(DiscoveredPost).where(
                DiscoveredPost.campaign_id == campaign.id,
                DiscoveredPost.content_hash == content_hash,
            )
        )
        post = existing.scalar_one_or_none()
        if post is None:
            post = DiscoveredPost(
                campaign_id=campaign.id,
                content_hash=content_hash,
                post_url=bump.target_post_url,
                author_name="(bump)",
                content_text=f"Bump bài: {bump.target_post_url}",
                status=PostStatus.NOTIFIED.value,
            )
            db.add(post)
            await db.flush()

        db.add(
            CommentAction(
                discovered_post_id=post.id,
                comment_content=message,
                status=CommentStatus.QUEUED.value,
                scheduled_at=utcnow(),
            )
        )
        bump.last_bumped_at = utcnow()
        await db.commit()
        return {"bump": bump_id, "message": message}


async def _due_bumps() -> list[str]:
    async with get_session_factory()() as db:
        result = await db.execute(
            select(BumpSchedule)
            .join(Campaign, Campaign.id == BumpSchedule.campaign_id)
            .where(BumpSchedule.is_active.is_(True), Campaign.is_active.is_(True))
        )
        return [b.id for b in result.scalars().all() if is_bump_due(b)]


@celery_app.task(name="app.workers.bump_task.check_bump_schedules")
def check_bump_schedules() -> dict:
    ids = run_async(_due_bumps())
    for bump_id in ids:
        run_bump.delay(bump_id)
    return {"dispatched": len(ids)}


@celery_app.task(name="app.workers.bump_task.run_bump")
def run_bump(bump_id: str) -> dict:
    return run_async(_bump_one(bump_id))
