"""
Dịch vụ Quản lý & Thực thi Đăng bài tự động (Post Publisher Service).

Chịu trách nhiệm:
  1. Phân bổ và lựa chọn nick clone chuyên trách (vai trò 'poster' hoặc 'all').
  2. Kiểm tra hạn mức đăng bài (daily_post_limit) để chống checkpoint.
  3. Render Spintax nội dung bài viết trước khi xuất bản vào từng group.
  4. Lưu vết lịch sử và link bài viết đã đăng thành công.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, AccountTransition, CloneRole, PublishStatus
from app.models.post import PostPublish
from app.services.account_manager import AccountManager, InvalidTransitionError
from app.services.crypto import decrypt_cookies
from app.services.notification_service import build_clone_notifier
from app.services.script_engine import ScriptError, render_spintax
from app.workers.browser_runtime import BrowserRuntimeUnavailable, publish_post_real

# Trạng thái đăng vào 1 group được coi là "đã ghi lên Facebook" (tính quota).
_POSTED_STATUSES = {"published", "published_no_url"}


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
        clone = await db.get(CloneAccount, preferred_clone_id)
        if clone and clone.user_id == user_id and clone.role in valid_roles and clone_can_post(clone):
            return clone

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

    if post_pub.status not in (PublishStatus.SCHEDULED.value, PublishStatus.DRAFT.value, PublishStatus.FAILED.value):
        return {"skipped": f"status_is_{post_pub.status}"}

    # Chọn clone đăng bài
    clone = await pick_poster_clone(db, post_pub.user_id, post_pub.clone_account_id)
    if clone is None:
        post_pub.status = PublishStatus.FAILED.value
        post_pub.error_message = "Không tìm thấy nick clone nào có vai trò Đăng bài (Poster) đang hoạt động và còn quota hôm nay."
        await db.commit()
        return {"error": "no_available_poster_clone"}

    post_pub.status = PublishStatus.PUBLISHING.value
    post_pub.clone_account_id = clone.id
    await db.commit()

    raw_template = post_pub.content_template or ""

    try:
        cookies = decrypt_cookies(clone.cookie_data_encrypted)
    except Exception:
        cookies = None

    # Track D — preflight: xác nhận nick Poster còn đăng nhập trước khi đăng.
    from app.config import get_settings

    if get_settings().preflight_before_run:
        from app.services.preflight_service import run_preflight

        pf = await run_preflight(db, clone, cookies=cookies)
        if not pf.get("ok"):
            post_pub.status = PublishStatus.FAILED.value
            post_pub.error_message = (
                f"Preflight nick Poster không đạt ({pf.get('reason')}) — chưa đăng bài."
            )
            await db.commit()
            return {"error": "preflight_failed", "reason": pf.get("reason")}

    targets = list(post_pub.target_groups or [])
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

        # Hết quota post trong ngày -> dừng, các nhóm còn lại báo skipped.
        if used_today + posted_count >= limit:
            results.append({
                "group_id": group_id, "group_name": group_name, "group_url": group_url,
                "clone_id": clone.id, "clone_name": clone.display_name,
                "post_url": None, "status": "skipped_quota",
                "error": "Đã đạt hạn mức đăng bài trong ngày của nick.",
            })
            continue

        # Mỗi nhóm một bản render spintax riêng — đăng y hệt vào mọi nhóm là
        # dấu hiệu spam rõ nhất.
        try:
            content_to_post = render_spintax(raw_template) if "{" in raw_template else raw_template
        except ScriptError:
            content_to_post = raw_template

        try:
            outcome = await publish_post_real(clone, group_url, content_to_post, cookies)
        except BrowserRuntimeUnavailable as exc:
            runtime_missing = str(exc)
            break
        except Exception as exc:  # noqa: BLE001 - ghi lỗi, không bịa link
            results.append({
                "group_id": group_id, "group_name": group_name, "group_url": group_url,
                "clone_id": clone.id, "clone_name": clone.display_name,
                "post_url": None, "status": "failed", "error": str(exc),
            })
            continue

        status = outcome.get("status", "failed")
        results.append({
            "group_id": group_id, "group_name": group_name, "group_url": group_url,
            "clone_id": clone.id, "clone_name": clone.display_name,
            "post_url": outcome.get("post_url"),
            "status": status,
            "error": outcome.get("error"),
            "published_at": now.isoformat() if status in _POSTED_STATUSES else None,
        })
        if status in _POSTED_STATUSES:
            posted_count += 1
        if status == "published":
            full_ok_count += 1

    # Runtime browser không sẵn sàng.
    #   - Chưa đăng được nhóm nào -> FAILED, KHÔNG rơi về giả lập.
    #   - Đã đăng xong vài nhóm trước khi trình duyệt chết -> GIỮ lại kết quả
    #     (trước đây gán publish_results = [] làm mất permalink đã ghi thật lên
    #     Facebook, không còn đường dọn). Đi tiếp xuống nhánh partial bên dưới.
    if runtime_missing is not None and posted_count == 0:
        post_pub.publish_results = []
        post_pub.published_at = None
        post_pub.status = PublishStatus.FAILED.value
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
    await db.commit()
    return {
        "status": post_pub.status,
        "clone_id": clone.id,
        "published_count": posted_count,
        "results": results,
    }
