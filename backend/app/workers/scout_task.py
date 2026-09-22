"""
Scout task — quét group theo tần suất riêng của từng group (multi-tenant).

Beat gọi `scan_all_active_campaigns` mỗi 60 giây; task này chỉ chọn ra
những group ĐẾN HẠN quét rồi giao việc cho từng task con, nhờ vậy hàng trăm
khách hàng không cùng đổ vào Facebook một lúc.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from fastapi import HTTPException
from app.services.execution_policy import require_entitlement

from app.config import get_settings
from app.database import get_session_factory
from app.models.base import as_utc
from app.models.campaign import Campaign, CampaignGroup
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, AccountTransition, CloneRole, GroupStatus
from app.models.user import User
from app.services.account_manager import AccountManager, InvalidTransitionError
from app.services.ai_service import AIService
from app.services.crypto import decrypt_cookies
from app.services.group_discovery_service import merge_discovered_groups
from app.services.mention_service import detect_mentions, notify_mentions
from app.services.notification_service import NotificationService, build_clone_notifier
from app.services.pipeline import ingest_raw_posts, process_campaign_posts
from app.services.quota import SubscriptionInactive
from app.workers.browser_runtime import (
    BrowserRuntimeUnavailable,
    ScoutCheckpoint,
    scan_group_raw,
    scrape_post_comments_raw,
    scrape_joined_groups_raw,
)
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


async def _flag_scout_checkpoint(db, clone: CloneAccount, detail: str) -> None:
    """Scout dính checkpoint khi treo máy -> dừng nick, báo chủ, nhường clone dự phòng."""
    manager = AccountManager(db, notifier=await build_clone_notifier(db))
    try:
        await manager.transition(
            clone, AccountTransition.CHECKPOINT_DETECTED, f"Quét nhóm: {detail}"
        )
    except InvalidTransitionError:
        # Đã ở CHECKPOINT/BANNED rồi -> không cần làm gì thêm.
        pass


async def _note_scout_failure(db, clone: CloneAccount, detail: str) -> None:
    """Lượt quét hỏng -> tăng bộ đếm; đủ ngưỡng thì AccountManager tự cho nghỉ."""
    manager = AccountManager(db, notifier=await build_clone_notifier(db))
    await manager.record_failure(clone, f"Quét nhóm hỏng: {detail}")


async def _scan_one(campaign_id: str, group_id: str) -> dict:
    settings = get_settings()
    async with get_session_factory()() as db:
        campaign = await db.get(Campaign, campaign_id)
        group = await db.get(CampaignGroup, group_id)
        if campaign is None or group is None or group.campaign_id != campaign.id or not campaign.is_active:
            return {"skipped": "campaign_or_group_missing"}
        if not is_due(group):
            return {"skipped": "not_due"}
        try:
            await require_entitlement(db, campaign.user_id, campaign)
        except HTTPException:
            return {"skipped": "policy_denied"}

        user = await db.get(User, campaign.user_id)
        clone = await _pick_scout_clone(db, campaign.user_id)
        if clone is None:
            return {"skipped": "no_active_scout_clone"}

        try:
            cookies = decrypt_cookies(clone.cookie_data_encrypted)
        except Exception:
            return {"error": "cookie_decryption_failed"}
        await db.commit()

        # Track D — preflight: xác nhận nick còn đăng nhập trước khi quét.
        if settings.preflight_before_run:
            from app.services.preflight_service import run_preflight

            pf = await run_preflight(db, clone, cookies=cookies)
            await db.commit()
            if not pf.get("ok"):
                return {
                    "error": "preflight_failed",
                    "reason": pf.get("reason"),
                    "clone": clone.display_name,
                }

        try:
            raw_posts = await scan_group_raw(clone, group, cookies)
        except BrowserRuntimeUnavailable as exc:
            return {"error": str(exc)}
        except ScoutCheckpoint as exc:
            # "Mode treo": nick Scout bị checkpoint -> dừng ngay, không quét lại.
            await _flag_scout_checkpoint(db, clone, str(exc))
            await db.commit()
            return {"error": "scout_checkpoint", "clone": clone.display_name}
        except Exception as exc:  # lỗi mạng/Facebook không được giết cả beat
            await _note_scout_failure(db, clone, str(exc))
            await db.commit()
            return {"error": f"scan_failed: {exc}"}

        # Lượt quét trót lọt -> reset bộ đếm hỏng liên tiếp của nick Scout.
        await AccountManager(db).note_ok(clone)

        fresh = await ingest_raw_posts(db, campaign, group, raw_posts)
        stats = await process_campaign_posts(
            db,
            campaign,
            fresh,
            AIService(settings.openai_api_key, settings.openai_model),
            notifier=NotificationService(),
            user=user,
        )

        mentions = await detect_mentions(db, campaign, group, fresh)
        await notify_mentions(user, campaign.name, mentions, db=db)
        leads = []
        if campaign.lead_keywords:
            # Chỉ quét permalink Scout vừa thấy; selector không khớp thì trả
            # rỗng, không tạo lead giả. Các lượt sau dedup theo comment ID.
            raw_comments = []
            for raw_post in raw_posts:
                post_url = str(raw_post.get("url") or "").strip()
                if not post_url:
                    continue
                try:
                    raw_comments.extend(
                        await scrape_post_comments_raw(clone, post_url, cookies, limit=100)
                    )
                except ScoutCheckpoint:
                    await _flag_scout_checkpoint(db, clone, "Đọc comment bị checkpoint")
                    break
                except BrowserRuntimeUnavailable:
                    break
                except Exception as exc:
                    # Comment scan bổ sung không làm mất kết quả scan bài.
                    raw_comments.append({"text": "", "_scan_error": str(exc)})
            for raw_comment in raw_comments:
                raw_comment.setdefault("post_url", raw_comment.get("url") or "")
            leads = await detect_leads(
                db,
                campaign,
                group,
                raw_comments,
                own_fb_id=clone.fb_user_id or "",
            )
            await notify_leads(user, campaign.name, leads, db=db)
        await db.commit()
        return {
            "group": group.group_name,
            "ingested": len(fresh),
            "mentions": len(mentions),
            "leads": len(leads),
            **stats,
        }


def _discovery_summary(campaign_name: str, result: dict) -> str:
    """Thẻ tóm tắt gửi Telegram sau khi cào nhóm (hàm thuần — test offline được)."""
    return (
        f"Cào nhóm đã tham gia — chiến dịch {campaign_name}\n"
        f"Tìm thấy {result['discovered']} nhóm, thêm mới {result['added']} "
        f"(trạng thái tạm dừng, chờ duyệt).\n"
        f"Bỏ qua: {result['skipped_duplicate']} đã có sẵn, "
        f"{result['skipped_quota']} vượt hạn mức gói, "
        f"{result['skipped_invalid']} link không hợp lệ."
    )


async def _discover_groups(campaign_id: str) -> dict:
    async with get_session_factory()() as db:
        campaign = await db.get(Campaign, campaign_id)
        if campaign is None:
            return {"skipped": "campaign_missing"}
        try:
            await require_entitlement(db, campaign.user_id)
        except HTTPException:
            return {"skipped": "policy_denied"}

        user = await db.get(User, campaign.user_id)
        clone = await _pick_scout_clone(db, campaign.user_id)
        if clone is None:
            return {"skipped": "no_active_scout_clone"}

        try:
            cookies = decrypt_cookies(clone.cookie_data_encrypted)
        except Exception:
            return {"error": "cookie_decryption_failed"}
        await db.commit()

        try:
            raw_groups = await scrape_joined_groups_raw(clone, cookies)
        except BrowserRuntimeUnavailable as exc:
            return {"error": str(exc)}
        except Exception as exc:  # lỗi mạng/Facebook không được giết cả beat
            return {"error": f"scrape_failed: {exc}"}

        try:
            result = await merge_discovered_groups(db, campaign, user, raw_groups)
        except SubscriptionInactive as exc:
            return {"error": str(exc)}
        if user is not None and user.telegram_chat_id:
            from app.services.outbox_service import queue_text

            await queue_text(
                db, user.telegram_chat_id, _discovery_summary(campaign.name, result)
            )
        await db.commit()
        return result


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


@celery_app.task(
    name="app.workers.scout_task.discover_joined_groups",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def discover_joined_groups(self, campaign_id: str) -> dict:
    """Cào hồ sơ clone Scout, nạp các nhóm đã tham gia vào chiến dịch (status paused)."""
    return run_async(_discover_groups(campaign_id))
