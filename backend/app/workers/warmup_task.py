"""
Warm-up task — chạy 1 bước ủ ấm mỗi ngày cho mỗi clone đang WARMING_UP.

Hành vi trên trình duyệt do `browser_executor` đảm nhiệm; khi chưa cài
Playwright, task vẫn tiến hành lịch (dry-run) để dashboard phản ánh đúng
tiến trình thay vì đứng im mãi ở ngày 0.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.database import get_session_factory
from app.models.base import as_utc
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState
from app.models.user import User
from app.services.crypto import decrypt_cookies
from app.services.notification_service import NotificationService
from app.services.warmup_service import WarmupService
from app.workers.browser_runtime import (
    BrowserRuntimeUnavailable,
    _maybe_write_cookies,
    build_runtime_config,
    load_phase1_modules,
)
from app.workers.celery_app import celery_app, run_async


def needs_step_today(clone: CloneAccount, now: datetime | None = None) -> bool:
    """Mỗi clone chỉ ủ ấm 1 bước / 24 giờ (hàm thuần — test offline được)."""
    if clone.status != AccountState.WARMING_UP.value:
        return False
    last = as_utc(clone.last_activity_at)
    if last is None:
        return True
    return (now or datetime.now(timezone.utc)) - last >= timedelta(hours=20)


async def browser_executor(clone: CloneAccount, step) -> bool:
    """Thực thi hành vi ủ ấm thật trên Playwright.

    Returns:
        True nếu hoàn tất (và với ngày health-check là 'clone khoẻ'),
        False khi phát hiện checkpoint.
    """
    BrowserManager, _, _ = load_phase1_modules()
    from human_emulator import random_scroll, safe_hover, warmup_session  # type: ignore

    try:
        cookies = decrypt_cookies(clone.cookie_data_encrypted)
    except Exception:
        cookies = None

    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)
    manager = BrowserManager(config)
    account = config.accounts["scout"]
    try:
        context = await manager.create_stealth_context(
            profile_dir=account.profile_dir, proxy=account.proxy, headless=True
        )
        page = context.pages[0] if context.pages else await context.new_page()

        if await BrowserManager.detect_checkpoint_page(page):
            return False

        seconds = max(60, step.duration_minutes * 60)
        await warmup_session(page, duration_min=seconds * 0.8, duration_max=seconds)

        if "browse" in step.actions:
            await random_scroll(page)
        if "like" in step.actions or "reels" in step.actions:
            # Like/Reels dùng chung thao tác an toàn: chỉ rê chuột, không click bừa.
            await safe_hover(page)

        return not await BrowserManager.detect_checkpoint_page(page)
    finally:
        await manager.close_all()


async def _run_step(clone_id: str) -> dict:
    async with get_session_factory()() as db:
        clone = await db.get(CloneAccount, clone_id)
        if clone is None:
            return {"skipped": "clone_missing"}

        notifier = NotificationService()

        async def notify(user_id: str, message: str) -> None:
            user = await db.get(User, user_id)
            if user and user.telegram_chat_id:
                await notifier.send_text(user.telegram_chat_id, message)

        try:
            load_phase1_modules()
            executor = browser_executor
        except BrowserRuntimeUnavailable:
            executor = None  # dry-run: vẫn tiến lịch, không mở browser

        service = WarmupService(db, notifier=notify, executor=executor)
        result = await service.run_daily_step(clone)
        await db.commit()
        return result


async def _clones_needing_warmup() -> list[str]:
    async with get_session_factory()() as db:
        result = await db.execute(
            select(CloneAccount).where(
                CloneAccount.status == AccountState.WARMING_UP.value
            )
        )
        return [c.id for c in result.scalars().all() if needs_step_today(c)]


@celery_app.task(name="app.workers.warmup_task.run_warmup_cycle")
def run_warmup_cycle() -> dict:
    ids = run_async(_clones_needing_warmup())
    for clone_id in ids:
        warmup_daily_step.delay(clone_id)
    return {"dispatched": len(ids)}


@celery_app.task(
    name="app.workers.warmup_task.warmup_daily_step", bind=True, max_retries=3
)
def warmup_daily_step(self, clone_id: str) -> dict:
    return run_async(_run_step(clone_id))
