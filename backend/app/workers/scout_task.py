"""
Scout task — quét group theo tần suất riêng của từng group (multi-tenant).

Beat gọi `scan_all_active_campaigns` mỗi 60 giây; task này chỉ chọn ra
những group ĐẾN HẠN quét rồi giao việc cho từng task con, nhờ vậy hàng trăm
khách hàng không cùng đổ vào Facebook một lúc.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_factory
from app.models.base import as_utc
from app.models.campaign import Campaign, CampaignGroup
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, CloneRole, GroupStatus
from app.models.user import User
from app.services.ai_service import AIService
from app.services.crypto import decrypt_cookies
from app.services.notification_service import NotificationService
from app.services.pipeline import ingest_raw_posts, process_campaign_posts
from app.workers.browser_runtime import BrowserRuntimeUnavailable, scan_group_raw
from app.workers.celery_app import celery_app, run_async


def is_due(group: CampaignGroup, now: datetime | None = None) -> bool:
    """Group đến hạn quét chưa? (hàm thuần — test offline được)"""
    if group.status != GroupStatus.ACTIVE.value:
        return False
    last = as_utc(group.last_scanned_at)
    if last is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now - last >= timedelta(minutes=max(1, group.scan_interval_minutes))


async def _due_groups() -> list[tuple[str, str]]:
    """Trả về (campaign_id, group_id) của các group đến hạn quét."""
    async with get_session_factory()() as db:
        result = await db.execute(
            select(CampaignGroup)
            .join(Campaign, Campaign.id == CampaignGroup.campaign_id)
            .where(Campaign.is_active.is_(True))
        )
        return [
            (group.campaign_id, group.id)
            for group in result.scalars().all()
            if is_due(group)
        ]


async def _pick_scout_clone(db, user_id: str) -> CloneAccount | None:
    """Chọn clone Scout đang khoẻ của khách hàng."""
    result = await db.execute(
        select(CloneAccount).where(
            CloneAccount.user_id == user_id,
            CloneAccount.status == AccountState.ACTIVE.value,
            CloneAccount.role.in_((CloneRole.SCOUT.value, CloneRole.BOTH.value, CloneRole.ALL.value)),
        )
    )
    return result.scalars().first()


async def _scan_one(campaign_id: str, group_id: str) -> dict:
    settings = get_settings()
    async with get_session_factory()() as db:
        campaign = await db.get(Campaign, campaign_id)
        group = await db.get(CampaignGroup, group_id)
        if campaign is None or group is None or not campaign.is_active:
            return {"skipped": "campaign_or_group_missing"}

        user = await db.get(User, campaign.user_id)
        clone = await _pick_scout_clone(db, campaign.user_id)
        if clone is None:
            return {"skipped": "no_active_scout_clone"}

        try:
            cookies = decrypt_cookies(clone.cookie_data_encrypted)
        except Exception:
            cookies = None

        try:
            raw_posts = await scan_group_raw(clone, group, cookies)
        except BrowserRuntimeUnavailable as exc:
            return {"error": str(exc)}
        except Exception as exc:  # lỗi mạng/Facebook không được giết cả beat
            return {"error": f"scan_failed: {exc}"}

        fresh = await ingest_raw_posts(db, campaign, group, raw_posts)
        stats = await process_campaign_posts(
            db,
            campaign,
            fresh,
            AIService(settings.openai_api_key, settings.openai_model),
            notifier=NotificationService(),
            user=user,
        )
        await db.commit()
        return {"group": group.group_name, "ingested": len(fresh), **stats}


@celery_app.task(name="app.workers.scout_task.scan_all_active_campaigns")
def scan_all_active_campaigns() -> dict:
    pairs = run_async(_due_groups())
    for campaign_id, group_id in pairs:
        scan_group.delay(campaign_id, group_id)
    return {"dispatched": len(pairs)}


@celery_app.task(
    name="app.workers.scout_task.scan_group", bind=True, max_retries=2, default_retry_delay=120
)
def scan_group(self, campaign_id: str, group_id: str) -> dict:
    return run_async(_scan_one(campaign_id, group_id))
