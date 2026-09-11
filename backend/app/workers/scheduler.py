# plan: docs/plans/desktop_packaging.md
"""
Scheduler in-process cho che do desktop (RUN_MODE=desktop, xem app/main.py).

Thay Celery Beat + worker: dung APScheduler AsyncIOScheduler chay chung
event loop voi uvicorn, goi thang cac ham async noi bo da co san trong
tung *_task.py (khong doi logic nghiep vu). Job con duoc xep qua
SerialJobQueue (job_queue.py) thay cho `.delay()` + `worker_prefetch=1`
cua Celery, dam bao khong co 2 hanh dong Facebook chay song song.

Lich 7 job COPY 1:1 chu ky tu `celery_app.conf.beat_schedule`
(app/workers/celery_app.py) — doi lich thi sua ca hai noi.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.workers.job_queue import job_queue

logger = logging.getLogger("commhunter.scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")


async def _dispatch_scout() -> None:
    from app.workers.scout_task import _due_groups, _scan_one

    pairs = await _due_groups()
    for campaign_id, group_id in pairs:
        await job_queue.enqueue(
            lambda c=campaign_id, g=group_id: _scan_one(c, g)
        )


async def _dispatch_shooter() -> None:
    from app.workers.shooter_task import _due_actions, _execute, _wake_quota_exhausted

    action_ids = await _due_actions()
    for action_id in action_ids:
        await job_queue.enqueue(lambda a=action_id: _execute(a))
    await _wake_quota_exhausted()


async def _dispatch_bump() -> None:
    from app.workers.bump_task import _bump_one, _due_bumps

    bump_ids = await _due_bumps()
    for bump_id in bump_ids:
        await job_queue.enqueue(lambda b=bump_id: _bump_one(b))


async def _dispatch_warmup() -> None:
    from app.workers.warmup_task import _clones_needing_warmup, _run_step

    clone_ids = await _clones_needing_warmup()
    for clone_id in clone_ids:
        await job_queue.enqueue(lambda c=clone_id: _run_step(c))


async def _dispatch_health_check() -> None:
    from app.workers.health_check_task import _check_all

    await job_queue.enqueue(_check_all)


async def _dispatch_wake_cooldowns() -> None:
    from app.workers.health_check_task import _wake

    await job_queue.enqueue(_wake)


async def _dispatch_publisher() -> None:
    from app.workers.publisher_task import _due_publishes, _execute_one

    pub_ids = await _due_publishes()
    for pub_id in pub_ids:
        await job_queue.enqueue(lambda p=pub_id: _execute_one(p))


def start_scheduler() -> None:
    """Goi 1 lan trong lifespan khi RUN_MODE=desktop."""
    job_queue.start()
    scheduler.add_job(_dispatch_scout, "interval", seconds=60, id="scout-scan-all")
    scheduler.add_job(_dispatch_shooter, "interval", seconds=30, id="shooter-process-queue")
    scheduler.add_job(_dispatch_bump, "interval", seconds=300, id="bump-check-schedule")
    scheduler.add_job(
        _dispatch_warmup, CronTrigger(hour=9, minute=0), id="warmup-daily-step"
    )
    scheduler.add_job(
        _dispatch_health_check, "interval", seconds=1800, id="health-check-clones"
    )
    scheduler.add_job(
        _dispatch_wake_cooldowns, "interval", seconds=600, id="wake-cooldowns"
    )
    scheduler.add_job(
        _dispatch_publisher, "interval", seconds=60, id="publisher-process-queue"
    )
    scheduler.start()
    logger.info("Scheduler desktop da khoi dong: 7 job dang ky")


async def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    await job_queue.stop()
