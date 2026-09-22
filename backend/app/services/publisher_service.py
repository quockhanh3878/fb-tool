"""
Dịch vụ Quản lý & Thực thi Đăng bài tự động (Post Publisher Service).

Chịu trách nhiệm:
  1. Phân bổ và lựa chọn nick clone chuyên trách (vai trò 'poster' hoặc 'all').
  2. Kiểm tra hạn mức đăng bài (daily_post_limit) để chống checkpoint.
  3. Render Spintax nội dung bài viết trước khi xuất bản vào từng group.
  4. Lưu vết lịch sử và link bài viết đã đăng thành công.
"""
from datetime import datetime, timedelta, timezone
import asyncio
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import BumpSchedule, Campaign, CommentScript
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, AccountTransition, CloneRole, PublishStatus
from app.models.post import PostPublish, PostPublishHistory, PublishingMedia
from app.services.account_manager import AccountManager, InvalidTransitionError
from app.services.anti_ban import schedule_jitter_seconds
from app.services.crypto import decrypt_cookies
from app.services.notification_service import build_clone_notifier
from app.services.script_engine import ScriptError, render_spintax
from app.workers.browser_runtime import BrowserRuntimeUnavailable, publish_post_real
from app.config import get_settings
from app.services.execution_policy import lock_user, require_entitlement, require_owned_clone
from app.services.leases import LeaseBusy, resource_lease
from app.services.url_policy import facebook_url
from app.services.publishing_defaults import DEFAULT_BUMP_HOURS
from app.services.publishing_media import parse_media_reference

# Trạng thái đăng vào 1 group được coi là "đã ghi lên Facebook" (tính quota).
_POSTED_STATUSES = {"published", "published_no_url"}


def _save_publish_history(db, post_pub, clone, target: dict, result: dict, content: str) -> None:
    """Queue one durable per-group result alongside the response snapshot."""
    db.add(
        PostPublishHistory(
            user_id=post_pub.user_id,
            post_publish_id=post_pub.id,
            campaign_id=post_pub.campaign_id,
            clone_account_id=clone.id if clone is not None else post_pub.clone_account_id,
            group_id=str(target.get("group_id") or ""),
            group_name=str(target.get("group_name") or ""),
            group_url=str(target.get("group_url") or ""),
            post_url=str(result.get("post_url") or ""),
            status=str(result.get("status") or "unknown_outcome"),
            error_message=result.get("error"),
            content_snapshot=content or "",
            published_at=as_utc(datetime.fromisoformat(result["published_at"]))
            if result.get("published_at")
            else None,
        )
    )


def as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def clone_can_post(clone: CloneAccount, now: datetime | None = None) -> bool:
    """Kiểm tra clone có đủ điều kiện đăng bài không (active, hết cooldown, còn quota post)."""
    if clone.status != AccountState.ACTIVE.value:
        return False
    now = now or datetime.now(timezone.utc)
    cooldown = as_utc(clone.cooldown_until)
    if cooldown is not None and cooldown > now:
        return False
    today = now.date().isoformat()
    used = clone.daily_post_count if clone.daily_counter_date == today else 0
    return used < (clone.daily_post_limit or 5)


async def pick_poster_clone(
    db: AsyncSession, user_id: str, preferred_clone_id: str | None = None
) -> CloneAccount | None:
    """
    Chọn clone chuyên trách đăng bài:
      - Ưu tiên clone được người dùng chỉ định (nếu hợp lệ và còn quota).
      - Nếu không, tự động tìm clone có vai trò 'poster' hoặc 'all' đang active và còn quota.
    """
    valid_roles = (CloneRole.POSTER.value, CloneRole.ALL.value)

    if preferred_clone_id:
        clone = await require_owned_clone(db, preferred_clone_id, user_id, valid_roles)
        if clone_can_post(clone):
            return clone
        return None

    result = await db.execute(
        select(CloneAccount).where(
            CloneAccount.user_id == user_id,
            CloneAccount.role.in_(valid_roles),
        )
    )
    for clone in result.scalars().all():
        if clone_can_post(clone):
            return clone
    return None


async def execute_publish(db: AsyncSession, publish_id: str) -> dict:
    """Thực thi xuất bản bài viết vào danh sách group mục tiêu."""
    now = datetime.now(timezone.utc)
    post_pub = await db.get(PostPublish, publish_id)
    if post_pub is None:
        return {"error": "publish_item_not_found"}

    await lock_user(db, post_pub.user_id)
    await db.refresh(post_pub)
    if post_pub.status not in (PublishStatus.SCHEDULED.value, PublishStatus.DRAFT.value):
        return {"skipped": f"status_is_{post_pub.status}"}
    if as_utc(post_pub.scheduled_at) is not None and as_utc(post_pub.scheduled_at) > now:
        return {"skipped": "not_due"}

    campaign = await db.get(Campaign, post_pub.campaign_id) if post_pub.campaign_id else None
    try:
        subscription = await require_entitlement(db, post_pub.user_id, campaign)
        if post_pub.campaign_id and campaign is None:
            raise HTTPException(status_code=409, detail="Campaign missing")
        if post_pub.auto_bump and not subscription.bump_enabled:
            raise HTTPException(status_code=403, detail="Bump entitlement required")
        if not post_pub.target_groups:
            raise HTTPException(status_code=422, detail="No target groups")
        for target in post_pub.target_groups:
            facebook_url(target.get("group_url", ""), group=True)
        clone = await pick_poster_clone(db, post_pub.user_id, post_pub.clone_account_id)
    except (HTTPException, ValueError):
        post_pub.status = PublishStatus.CANCELLED.value
        post_pub.error_message = "publish_policy_denied"
        await db.commit()
        return {"skipped": "policy_denied"}
    if clone is None:
        post_pub.status = PublishStatus.SCHEDULED.value
        post_pub.scheduled_at = now + timedelta(minutes=5)
        post_pub.error_message = "Không tìm thấy nick clone nào có vai trò Đăng bài (Poster) đang hoạt động và còn quota hôm nay."
        await db.commit()
        return {"error": "no_available_poster_clone"}

    post_pub.status = PublishStatus.PUBLISHING.value
    post_pub.clone_account_id = clone.id
    post_pub.lease_expires_at = now + timedelta(seconds=get_settings().job_lease_seconds)
    await db.commit()
    try:
        async with resource_lease(f"clone:{clone.id}"):
            await db.refresh(clone)
            if not clone_can_post(clone):
                raise LeaseBusy("Clone is not ready")
            async with asyncio.timeout(1700):
                return await _publish_claimed(db, post_pub, clone, now)
    except LeaseBusy:
        post_pub.status = PublishStatus.SCHEDULED.value
        post_pub.scheduled_at = now + timedelta(minutes=5)
        post_pub.lease_expires_at = None
        await db.commit()
        return {"deferred": "clone_busy"}
    except asyncio.CancelledError:
        await db.rollback()
        interrupted = await db.get(PostPublish, publish_id, populate_existing=True)
        if interrupted is not None and interrupted.status == PublishStatus.PUBLISHING.value:
            interrupted.status = PublishStatus.UNKNOWN_OUTCOME.value
            interrupted.lease_expires_at = None
            interrupted.error_message = "Worker cancelled; review before retry"
            await db.commit()
        raise
    except Exception:
        await db.rollback()
        post_pub = await db.get(PostPublish, publish_id, populate_existing=True)
        post_pub.status = PublishStatus.UNKNOWN_OUTCOME.value
        post_pub.error_message = "Outcome unknown; review saved target results before retry"
        post_pub.lease_expires_at = None
        await db.commit()
        return {"error": "unknown_outcome"}


async def _publish_claimed(db, post_pub, clone, now):

    raw_template = post_pub.content_template or ""

    try:
        cookies = decrypt_cookies(clone.cookie_data_encrypted)
    except Exception:
        post_pub.status = PublishStatus.FAILED.value
        post_pub.error_message = "cookie_decryption_failed"
        post_pub.lease_expires_at = None
        await db.commit()
        return {"error": "cookie_decryption_failed"}

    # Track D — preflight: xác nhận nick Poster còn đăng nhập trước khi đăng.
    from app.config import get_settings

    if get_settings().preflight_before_run:
        from app.services.preflight_service import run_preflight

        pf = await run_preflight(db, clone, cookies=cookies)
        await db.commit()
        if not pf.get("ok"):
            post_pub.status = PublishStatus.FAILED.value
            post_pub.lease_expires_at = None
            post_pub.error_message = (
                f"Preflight nick Poster không đạt ({pf.get('reason')}) — chưa đăng bài."
            )
            await db.commit()
            return {"error": "preflight_failed", "reason": pf.get("reason")}

    targets = list(post_pub.target_groups or [])
    media_paths: list[str] = []
    for reference in list(post_pub.media_urls or []):
        media_id = parse_media_reference(reference)
        media = await db.get(PublishingMedia, media_id) if media_id else None
        if media is None or media.user_id != post_pub.user_id or not Path(media.storage_path).is_file():
            post_pub.status = PublishStatus.FAILED.value
            post_pub.error_message = "media_asset_not_found"
            post_pub.lease_expires_at = None
            await db.commit()
            return {"error": "media_asset_not_found"}
        media_paths.append(media.storage_path)
    results: list[dict] = []
    posted_count = 0        # số nhóm đã ghi lên Facebook (tính quota)
    full_ok_count = 0       # số nhóm đăng xong VÀ xác minh được permalink
    today = now.date().isoformat()
    used_today = clone.daily_post_count if clone.daily_counter_date == today else 0
    limit = clone.daily_post_limit or 5
    runtime_missing: str | None = None

    for target in targets:
        group_url = target.get("group_url", "")
        group_name = target.get("group_name", "")
        group_id = target.get("group_id", "")
        campaign = await db.get(Campaign, post_pub.campaign_id) if post_pub.campaign_id else None
        try:
            await require_entitlement(db, post_pub.user_id, campaign)
        except HTTPException:
            result = {"group_id": group_id, "group_name": group_name, "group_url": group_url, "status": "cancelled", "error": "policy_changed"}
            results.append(result)
            _save_publish_history(db, post_pub, clone, target, result, raw_template)
            break
        await db.commit()

        # Hết quota post trong ngày -> dừng, các nhóm còn lại báo skipped.
        if used_today + posted_count >= limit:
            result = {
                "group_id": group_id, "group_name": group_name, "group_url": group_url,
                "clone_id": clone.id, "clone_name": clone.display_name,
                "post_url": None, "status": "skipped_quota",
                "error": "Đã đạt hạn mức đăng bài trong ngày của nick.",
            }
            results.append(result)
            _save_publish_history(db, post_pub, clone, target, result, raw_template)
            continue

        # Mỗi nhóm một bản render spintax riêng — đăng y hệt vào mọi nhóm là
        # dấu hiệu spam rõ nhất.
        try:
            content_to_post = render_spintax(raw_template) if "{" in raw_template else raw_template
        except ScriptError:
            content_to_post = raw_template

        try:
            outcome = await publish_post_real(
                clone, group_url, content_to_post, cookies, media_paths=media_paths
            )
        except BrowserRuntimeUnavailable as exc:
            runtime_missing = str(exc)
            result = {
                "group_id": group_id, "group_name": group_name, "group_url": group_url,
                "clone_id": clone.id, "clone_name": clone.display_name,
                "post_url": None, "status": "unknown_outcome",
                "error": "browser_runtime_unavailable",
            }
            results.append(result)
            _save_publish_history(db, post_pub, clone, target, result, content_to_post)
            await db.commit()
            break
        except Exception:
            result = {
                "group_id": group_id, "group_name": group_name, "group_url": group_url,
                "clone_id": clone.id, "clone_name": clone.display_name,
                "post_url": None, "status": "unknown_outcome", "error": "browser_outcome_unknown",
            }
            results.append(result)
            _save_publish_history(db, post_pub, clone, target, result, content_to_post)
            break

        status = outcome.get("status", "failed")
        result = {
            "group_id": group_id, "group_name": group_name, "group_url": group_url,
            "clone_id": clone.id, "clone_name": clone.display_name,
            "post_url": outcome.get("post_url"),
            "status": status,
            "error": outcome.get("error"),
            "published_at": now.isoformat() if status in _POSTED_STATUSES else None,
        }
        results.append(result)
        _save_publish_history(db, post_pub, clone, target, result, content_to_post)
        if status in _POSTED_STATUSES:
            posted_count += 1
        if status == "published":
            full_ok_count += 1
        post_pub.publish_results = list(results)
        if posted_count:
            clone.daily_post_count = used_today + posted_count
            clone.daily_counter_date = today
        await db.commit()

    # Runtime browser không sẵn sàng.
    #   - Chưa đăng được nhóm nào -> FAILED, KHÔNG rơi về giả lập.
    #   - Đã đăng xong vài nhóm trước khi trình duyệt chết -> GIỮ lại kết quả
    #     (trước đây gán publish_results = [] làm mất permalink đã ghi thật lên
    #     Facebook, không còn đường dọn). Đi tiếp xuống nhánh partial bên dưới.
    if runtime_missing is not None and posted_count == 0:
        post_pub.publish_results = []
        post_pub.published_at = None
        post_pub.status = PublishStatus.FAILED.value
        post_pub.lease_expires_at = None
        post_pub.error_message = (
            f"Không chạy được trình duyệt để đăng bài: {runtime_missing}"
        )
        await db.commit()
        return {"error": "browser_runtime_unavailable", "detail": runtime_missing}

    # Cập nhật quota clone theo SỐ NHÓM đã đăng (mỗi nhóm là một hành vi ghi).
    if posted_count:
        if clone.daily_counter_date != today:
            clone.daily_counter_date = today
            clone.daily_post_count = posted_count
        else:
            clone.daily_post_count = used_today + posted_count
        clone.last_activity_at = now

    if posted_count == 0:
        post_pub.status = PublishStatus.FAILED.value
        post_pub.error_message = "Đăng bài thất bại vào toàn bộ nhóm mục tiêu."
        post_pub.published_at = None
    elif full_ok_count == len(targets):
        post_pub.status = PublishStatus.PUBLISHED.value
        post_pub.error_message = None
        post_pub.published_at = now
    else:
        post_pub.status = PublishStatus.PARTIALLY_PUBLISHED.value
        msg = (
            f"Đăng được {posted_count}/{len(targets)} nhóm; "
            f"{full_ok_count} nhóm xác minh được link."
        )
        if runtime_missing is not None:
            msg += f" Trình duyệt dừng giữa chừng: {runtime_missing}."
        # Đường rollback: liệt kê permalink đã ghi thật để dọn tay khi cần
        # (KHÔNG tự xoá — bài đã lên là nội dung khách muốn giữ; xoá là một
        # thao tác ghi có rủi ro riêng, cần người quyết).
        posted_urls = [
            r["post_url"] for r in results
            if r.get("status") in _POSTED_STATUSES and r.get("post_url")
        ]
        if posted_urls:
            msg += " Link đã đăng để rà soát: " + ", ".join(posted_urls)
        post_pub.error_message = msg
        post_pub.published_at = now

    # "Mode treo": nick Poster dính checkpoint / hỏng toàn bộ khi chạy không
    # người trực -> dừng nick, đừng để publisher_task chọn lại mỗi 60s.
    saw_checkpoint = any(r.get("error") == "checkpoint" for r in results)
    mgr = AccountManager(db, notifier=await build_clone_notifier(db))
    if saw_checkpoint:
        try:
            await mgr.transition(
                clone, AccountTransition.CHECKPOINT_DETECTED, "Đăng bài: phát hiện checkpoint"
            )
        except InvalidTransitionError:
            pass
    elif posted_count == 0 and results:
        await mgr.record_failure(clone, "Đăng bài hỏng toàn bộ nhóm mục tiêu")
    elif posted_count:
        await mgr.note_ok(clone)

    post_pub.publish_results = results
    uncertain = any(result.get("status") == "unknown_outcome" for result in results)
    if uncertain:
        post_pub.status = PublishStatus.UNKNOWN_OUTCOME.value
        post_pub.error_message = "Có kết quả chưa xác định; cần đối soát trước khi gửi lại"
    post_pub.lease_expires_at = None

    # Tự động tạo BumpSchedule cho các post_url đăng thành công nếu auto_bump bật
    if post_pub.auto_bump and post_pub.campaign_id and posted_count > 0:
        posted_urls = [
            r["post_url"]
            for r in results
            if r.get("status") in _POSTED_STATUSES and r.get("post_url")
        ]
        if posted_urls:
            script_res = await db.execute(
                select(CommentScript).where(
                    CommentScript.campaign_id == post_pub.campaign_id,
                    CommentScript.is_active.is_(True),
                )
            )
            scripts = script_res.scalars().all()
            bump_msgs = [s.template_content for s in scripts if s.template_content]
            if not bump_msgs:
                posted_urls = []
                post_pub.error_message = "Không tạo bump: chưa có kịch bản đang bật"

            bump_hrs = post_pub.bump_hours or (
                campaign.publish_bump_hours if campaign else list(DEFAULT_BUMP_HOURS)
            )

            for purl in posted_urls:
                existing_bump = await db.execute(
                    select(BumpSchedule).where(
                        BumpSchedule.campaign_id == post_pub.campaign_id,
                        BumpSchedule.target_post_url == purl,
                    )
                )
                if existing_bump.scalars().first() is None:
                    new_bump = BumpSchedule(
                        campaign_id=post_pub.campaign_id,
                        target_post_url=purl,
                        cron_schedule=bump_hrs,
                        bump_messages=bump_msgs,
                        is_active=True,
                    )
                    db.add(new_bump)

    # Tự động lên lịch bài đăng cho chu kỳ tiếp theo nếu repeat_interval_days được thiết lập
    if post_pub.repeat_interval_days and post_pub.repeat_interval_days > 0 and full_ok_count == len(targets) and not uncertain:
        next_schedule = now + timedelta(
            days=post_pub.repeat_interval_days, seconds=schedule_jitter_seconds()
        )
        next_pub = PostPublish(
            user_id=post_pub.user_id,
            campaign_id=post_pub.campaign_id,
            clone_account_id=post_pub.clone_account_id,
            title=post_pub.title,
            content_template=post_pub.content_template,
            media_urls=post_pub.media_urls,
            target_groups=post_pub.target_groups,
            repeat_interval_days=post_pub.repeat_interval_days,
            auto_bump=post_pub.auto_bump,
            bump_hours=post_pub.bump_hours,
            status=PublishStatus.SCHEDULED.value,
            scheduled_at=next_schedule,
        )
        db.add(next_pub)

    await db.commit()
    return {
        "status": post_pub.status,
        "clone_id": clone.id,
        "published_count": posted_count,
        "results": results,
    }
