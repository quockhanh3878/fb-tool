"""
Bump task — tự thả comment "up" bài của chính khách để bài nổi lại trong group.

Quy tắc chống lộ: mỗi khung giờ chỉ bump 1 lần, nội dung xoay vòng ngẫu nhiên
trong danh sách khách soạn sẵn, và bump vẫn tính vào quota comment/ngày.
"""
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from fastapi import HTTPException

from app.database import get_session_factory
from app.models.base import as_utc, utcnow
from app.models.campaign import BumpSchedule, Campaign
from app.models.enums import AccountState, CloneRole, CommentStatus, PostStatus
from app.models.post import CommentAction, DiscoveredPost, PostPublishHistory
from app.services.pipeline import compute_content_hash, count_today_actions, queue_comment
from app.services.execution_policy import lock_user, require_entitlement
from app.services.notification_service import notify_error
from app.services.script_engine import ScriptError, render_spintax, validate_comment
from app.services.crypto import decrypt_cookies
from app.workers.browser_runtime import BrowserRuntimeUnavailable, check_post_alive_real
from app.workers.celery_app import celery_app, run_async

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def resolve_schedule_timezone(name: str | None) -> ZoneInfo:
    """Resolve campaign timezone; invalid legacy data falls back safely."""
    try:
        return ZoneInfo(str(name or LOCAL_TZ.key))
    except (TypeError, ValueError):
        return LOCAL_TZ


def bump_jitter_seconds(
    bump_id: str,
    date_key: str,
    hour: int,
    *,
    enabled: bool = True,
    min_minutes: int = 5,
    max_minutes: int = 10,
) -> int:
    """Lệch mốc bump 5-10 phút, ổn định trong ngày đó (seed theo bump/ngày/giờ).

    Đúng đầu giờ mỗi lần là hành vi máy móc dễ bị soi — hàm này dịch mốc kích
    hoạt sớm/trễ một khoảng cố định trong ngày (không đổi giữa các lần Beat
    kiểm tra lại) để tránh phát hiện lặp bằng cách đối chiếu timeline.
    """
    if not enabled:
        return 0
    from app.services.anti_ban import schedule_jitter_seconds

    min_minutes = max(0, int(min_minutes))
    max_minutes = max(min_minutes, int(max_minutes))

    seeded_rng = random.Random(f"{bump_id}:{date_key}:{hour}")
    return schedule_jitter_seconds(
        seeded_rng, min_minutes=min_minutes, max_minutes=max_minutes
    )


def is_bump_due(
    bump: BumpSchedule,
    now: datetime | None = None,
    *,
    jitter_enabled: bool = True,
    jitter_min_minutes: int = 5,
    jitter_max_minutes: int = 10,
    timezone_name: str = "Asia/Ho_Chi_Minh",
) -> bool:
    """Đến giờ bump chưa? (hàm thuần — test offline được)

    Mốc kích hoạt lệch 5-10 phút so với giờ tròn trong `cron_schedule` (xem
    `bump_jitter_seconds`), và chưa bump trong CHÍNH khung giờ đó. Mỗi giờ
    trong lịch được quy về lần xảy ra GẦN NHẤT so với `now` (trong vòng 12
    giờ) — giờ đã qua xa trong ngày hoặc chưa tới không bị coi là "đến hạn".
    """
    if not bump.is_active or not bump.cron_schedule:
        return False

    schedule_tz = resolve_schedule_timezone(timezone_name)
    now = (now or datetime.now(timezone.utc)).astimezone(schedule_tz)
    last = as_utc(bump.last_bumped_at)
    last_local = last.astimezone(schedule_tz) if last is not None else None

    for hour in (int(h) for h in bump.cron_schedule):
        candidate = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        delta_hours = (now - candidate).total_seconds() / 3600
        if delta_hours > 12:
            candidate += timedelta(days=1)
        elif delta_hours < -12:
            candidate -= timedelta(days=1)

        if last_local is not None and (last_local.date(), last_local.hour) == (candidate.date(), hour):
            continue
        target = candidate + timedelta(
            seconds=bump_jitter_seconds(
                bump.id,
                candidate.date().isoformat(),
                hour,
                enabled=jitter_enabled,
                min_minutes=jitter_min_minutes,
                max_minutes=jitter_max_minutes,
            )
        )
        if now >= target:
            return True
    return False


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
        if bump is None:
            return {"skipped": "not_due"}

        campaign = await db.get(Campaign, bump.campaign_id)
        if campaign is None or not campaign.is_active:
            return {"skipped": "campaign_inactive"}
        if not is_bump_due(
            bump,
            jitter_enabled=campaign.bump_jitter_enabled,
            jitter_min_minutes=campaign.bump_jitter_min_minutes,
            jitter_max_minutes=campaign.bump_jitter_max_minutes,
            timezone_name=campaign.schedule_timezone,
        ):
            return {"skipped": "not_due"}
        await lock_user(db, campaign.user_id)
        await db.refresh(bump)
        if not is_bump_due(
            bump,
            jitter_enabled=campaign.bump_jitter_enabled,
            jitter_min_minutes=campaign.bump_jitter_min_minutes,
            jitter_max_minutes=campaign.bump_jitter_max_minutes,
            timezone_name=campaign.schedule_timezone,
        ):
            return {"skipped": "not_due"}
        try:
            subscription = await require_entitlement(db, campaign.user_id, campaign)
        except HTTPException:
            return {"skipped": "policy_denied"}
        if not subscription.bump_enabled:
            return {"skipped": "bump_not_enabled"}

        latest_history = await db.scalar(
            select(PostPublishHistory)
            .where(
                PostPublishHistory.user_id == campaign.user_id,
                PostPublishHistory.campaign_id == campaign.id,
                PostPublishHistory.status.in_(("published", "published_no_url")),
                PostPublishHistory.post_url != "",
            )
            .order_by(PostPublishHistory.published_at.desc())
            .limit(1)
        )
        target_post_url = str(
            (latest_history.post_url if latest_history is not None else bump.target_post_url)
            or ""
        ).strip()
        if not target_post_url:
            return {"skipped": "no_target_post"}
        # A successful publish becomes the canonical bump target; a manually
        # entered URL remains the fallback for legacy schedules.
        bump.target_post_url = target_post_url

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

        # Bump là hành động ghi lên Facebook: nếu không xác nhận được bài còn
        # sống thì dừng an toàn, không xếp comment mù.
        try:
            from app.models.clone_account import CloneAccount
            scout_result = await db.execute(
                select(CloneAccount).where(
                    CloneAccount.user_id == campaign.user_id,
                    CloneAccount.status == AccountState.ACTIVE.value,
                    CloneAccount.role.in_(
                        (
                            CloneRole.SCOUT.value,
                            CloneRole.POSTER.value,
                            CloneRole.BOTH.value,
                            CloneRole.ALL.value,
                        )
                    ),
                ).limit(1)
            )
            probe_clone = scout_result.scalars().first()
            if probe_clone is None:
                return {"error": "no_active_clone_for_post_probe"}
            cookies = decrypt_cookies(probe_clone.cookie_data_encrypted)
            probe = await check_post_alive_real(probe_clone, target_post_url, cookies)
        except BrowserRuntimeUnavailable as exc:
            await notify_error(
                db,
                user_id=campaign.user_id,
                summary=f"Không xác nhận được bài bump còn sống: {exc}",
                source="PR_BUMP",
                occurred_at=utcnow(),
                link=target_post_url,
                dedup_key=f"bump-probe:{bump.id}:{utcnow().date().isoformat()}",
            )
            await db.commit()
            return {"error": "post_probe_unavailable"}
        except Exception:
            await notify_error(
                db,
                user_id=campaign.user_id,
                summary="Không xác nhận được bài bump còn sống; đã dừng để tránh comment nhầm.",
                source="PR_BUMP",
                occurred_at=utcnow(),
                link=target_post_url,
                dedup_key=f"bump-probe:{bump.id}:{utcnow().date().isoformat()}",
            )
            await db.commit()
            return {"error": "post_probe_failed"}
        if probe.get("status") == "gone":
            bump.is_active = False
            await notify_error(
                db,
                user_id=campaign.user_id,
                summary="Bài PR đã biến mất hoặc bị khóa; lịch bump đã tạm dừng.",
                source="PR_BUMP",
                occurred_at=utcnow(),
                link=target_post_url,
                dedup_key=f"bump-gone:{bump.id}",
            )
            await db.commit()
            return {"skipped": "inactive_post"}
        if probe.get("status") != "alive":
            await db.commit()
            return {"error": "post_probe_unrecognized_dom"}

        # Bài bump là bài của chính khách nên không đi qua Scout; tạo bản ghi
        # DiscoveredPost tối thiểu để hàng đợi comment có chỗ móc vào.
        content_hash = compute_content_hash("bump", target_post_url)
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
                post_url=target_post_url,
                author_name="(bump)",
                content_text=f"Bump bài: {target_post_url}",
                status=PostStatus.NOTIFIED.value,
            )
            db.add(post)
            await db.flush()

        await queue_comment(
            db, campaign, post, message,
            idempotency_key=f"bump:{bump.id}:{utcnow().strftime('%Y%m%d%H')}",
        )
        bump.last_bumped_at = utcnow()
        await db.commit()
        return {"bump": bump_id, "message": message}


async def _due_bumps() -> list[str]:
    async with get_session_factory()() as db:
        result = await db.execute(
            select(BumpSchedule, Campaign)
            .join(Campaign, Campaign.id == BumpSchedule.campaign_id)
            .where(BumpSchedule.is_active.is_(True), Campaign.is_active.is_(True))
        )
        return [
            bump.id
            for bump, campaign in result.all()
            if is_bump_due(
                bump,
                jitter_enabled=campaign.bump_jitter_enabled,
                jitter_min_minutes=campaign.bump_jitter_min_minutes,
                jitter_max_minutes=campaign.bump_jitter_max_minutes,
                timezone_name=campaign.schedule_timezone,
            )
        ]


@celery_app.task(name="app.workers.bump_task.check_bump_schedules")
def check_bump_schedules() -> dict:
    ids = run_async(_due_bumps())
    for bump_id in ids:
        run_bump.delay(bump_id)
    return {"dispatched": len(ids)}


@celery_app.task(name="app.workers.bump_task.run_bump")
def run_bump(bump_id: str) -> dict:
    return run_async(_bump_one(bump_id))
