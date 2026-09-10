"""
Health check task — kiểm tra session clone, đánh thức cooldown, soi proxy.

Chạy định kỳ nên đây là nơi hệ thống "tự phục hồi": clone hết hạn nghỉ tự
quay lại làm việc, clone mất cookie bị chuyển sang CHECKPOINT và tự nhường
việc cho clone dự phòng, proxy chết bị xoay.
"""
from sqlalchemy import select

from app.database import get_session_factory
from app.models.clone_account import CloneAccount, Proxy
from app.models.enums import AccountState, AccountTransition, HealthEventType, ProxyStatus
from app.models.user import User
from app.services.account_check import read_cookie_health
from app.services.account_manager import AccountManager
from app.services.facebook_utils import EXPIRY_WARNING_DAYS
from app.services.notification_service import NotificationService
from app.services.proxy_manager import ProxyManager, check_proxy_health
from app.workers.celery_app import celery_app, run_async

REQUIRED_COOKIES = {"c_user", "xs"}


def cookies_look_valid(cookies) -> bool:
    """Có đủ cookie phiên không? (hàm thuần — test offline được)"""
    names = {c.get("name") for c in (cookies or []) if isinstance(c, dict)}
    return REQUIRED_COOKIES.issubset(names)


async def _notifier(db):
    service = NotificationService()

    async def send(user_id: str, message: str) -> None:
        user = await db.get(User, user_id)
        if user and user.telegram_chat_id:
            await service.send_text(user.telegram_chat_id, message)

    return send


async def _check_all() -> dict:
    """Soi cookie của mọi clone đang chạy: hỏng thì hạ trạng thái, sắp hết hạn thì báo trước.

    Cảnh báo TRƯỚC khi cookie hết hạn là điểm khác biệt so với bản cũ — cũ chỉ
    biết cookie thiếu, tức là chỉ phát hiện sau khi clone đã chết.
    """
    async with get_session_factory()() as db:
        notify = await _notifier(db)
        manager = AccountManager(db, notifier=notify)
        result = await db.execute(
            select(CloneAccount).where(
                CloneAccount.status.in_(
                    (AccountState.ACTIVE.value, AccountState.WARMING_UP.value)
                )
            )
        )
        checked = flagged = expiring = 0
        for clone in result.scalars().all():
            checked += 1
            cookie = read_cookie_health(clone)

            if not cookie["ok"]:
                flagged += 1
                await manager.transition(
                    clone,
                    AccountTransition.CHECKPOINT_DETECTED,
                    "Health check: " + (cookie["reason"] or "cookie không dùng được"),
                )
                continue

            days = cookie["days_left"]
            if days is not None and days <= EXPIRY_WARNING_DAYS:
                expiring += 1
                await manager.log_event(
                    clone,
                    HealthEventType.LOGIN_OK,
                    f"Cookie sắp hết hạn — còn {days:g} ngày",
                )
                await notify(
                    clone.user_id,
                    f"Cookie của clone '{clone.display_name}' còn {days:g} ngày là hết hạn. "
                    "Hãy xuất cookie mới trước khi clone bị đá về trang đăng nhập.",
                )
            else:
                await manager.log_event(clone, HealthEventType.LOGIN_OK, "Cookie còn đủ")
        await db.commit()
        return {"checked": checked, "flagged": flagged, "expiring": expiring}


async def _wake() -> dict:
    async with get_session_factory()() as db:
        manager = AccountManager(db, notifier=await _notifier(db))
        woken = await manager.wake_expired_cooldowns()
        await db.commit()
        return {"woken": len(woken)}


async def _check_proxies() -> dict:
    async with get_session_factory()() as db:
        result = await db.execute(
            select(Proxy).where(
                Proxy.status.in_((ProxyStatus.AVAILABLE.value, ProxyStatus.ASSIGNED.value))
            )
        )
        manager = ProxyManager(db)
        checked = dead = 0
        for proxy in result.scalars().all():
            checked += 1
            healthy = await check_proxy_health(proxy.address)
            await manager.record_health(proxy, healthy)
            if not healthy:
                dead += 1
                clone_id = proxy.assigned_to_clone_id
                if clone_id:
                    clone = await db.get(CloneAccount, clone_id)
                    if clone is not None:
                        try:
                            await manager.rotate_proxy(clone, "proxy_health_check_failed")
                        except Exception:
                            # Hết proxy dự phòng: clone giữ nguyên IP cũ còn hơn
                            # là mất khả năng chạy.
                            pass
        await db.commit()
        return {"checked": checked, "dead": dead}


@celery_app.task(name="app.workers.health_check_task.check_all_clones")
def check_all_clones() -> dict:
    return run_async(_check_all())


@celery_app.task(name="app.workers.health_check_task.wake_cooldowns")
def wake_cooldowns() -> dict:
    return run_async(_wake())


@celery_app.task(name="app.workers.health_check_task.check_proxy_pool")
def check_proxy_pool() -> dict:
    return run_async(_check_proxies())
