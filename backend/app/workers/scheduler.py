# plan: docs/plans/desktop_packaging.md
"""
Scheduler in-process cho che do desktop (RUN_MODE=desktop, xem app/main.py).

Thay Celery Beat + worker: dung APScheduler AsyncIOScheduler chay chung
event loop voi uvicorn, goi thang cac ham async noi bo da co san trong
tung *_task.py (khong doi logic nghiep vu). Job con duoc xep qua
SerialJobQueue (job_queue.py) thay cho `.delay()` + `worker_prefetch=1`
cua Celery, dam bao khong co 2 hanh dong Facebook chay song song.

Lich 8 job COPY 1:1 chu ky tu `celery_app.conf.beat_schedule`
(app/workers/celery_app.py) — doi lich thi sua ca hai noi.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_factory
from app.models.job import JobRun
from app.services.job_registry import JobName, fail_job, finish_job, start_job
from app.workers.job_queue import job_queue

logger = logging.getLogger("commhunter.scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")


async def _is_paused(job_name: JobName) -> bool:
    """Respect the last operator pause before dispatching a desktop job."""
    async with get_session_factory()() as db:
        latest = await db.scalar(
            select(JobRun)
            .where(JobRun.user_id.is_(None), JobRun.job_name == job_name.value)
            .order_by(JobRun.started_at.desc())
            .limit(1)
        )
        return latest is not None and latest.status == "paused"


async def _run_tracked(job_name: JobName, action):
    """Record one queued desktop execution without sharing its DB session."""
    async with get_session_factory()() as db:
        run = await start_job(db, job_name)
        await db.commit()
        run_id = run.id
    try:
        result = await action()
    except Exception as exc:
        async with get_session_factory()() as db:
            failed = await db.get(JobRun, run_id)
            if failed is not None:
                await fail_job(db, failed, str(exc))
                await db.commit()
        raise
    async with get_session_factory()() as db:
        completed = await db.get(JobRun, run_id)
        if completed is not None:
            await finish_job(db, completed, counts=result if isinstance(result, dict) else {})
            await db.commit()
    return result


async def _dispatch_scout() -> None:
    from app.workers.scout_task import _due_groups, _scan_one

    if await _is_paused(JobName.LEAD_SCAN):
        return
    pairs = await _due_groups()
    for campaign_id, group_id in pairs:
        await job_queue.enqueue(
            lambda campaign=campaign_id, group=group_id: _run_tracked(
                JobName.LEAD_SCAN, lambda: _scan_one(campaign, group)
            ),
            key=f"scout:{campaign_id}:{group_id}",
        )


async def _dispatch_shooter() -> None:
    from app.workers.shooter_task import _due_actions, _execute, _wake_quota_exhausted

    if await _is_paused(JobName.LEAD_REPLY):
        return
    action_ids = await _due_actions()
    for action_id in action_ids:
        await job_queue.enqueue(
            lambda action=action_id: _run_tracked(
                JobName.LEAD_REPLY, lambda: _execute(action)
            ),
            key=f"comment:{action_id}",
        )
    await _wake_quota_exhausted()


async def _dispatch_bump() -> None:
    from app.workers.bump_task import _bump_one, _due_bumps

    if await _is_paused(JobName.PR_BUMP):
        return
    bump_ids = await _due_bumps()
    for bump_id in bump_ids:
        await job_queue.enqueue(
            lambda bump=bump_id: _run_tracked(JobName.PR_BUMP, lambda: _bump_one(bump)),
            key=f"bump:{bump_id}",
        )


async def _dispatch_warmup() -> None:
    from app.workers.warmup_task import _clones_needing_warmup, _run_step

    clone_ids = await _clones_needing_warmup()
    for clone_id in clone_ids:
        await job_queue.enqueue(lambda clone=clone_id: _run_step(clone), key=f"warmup:{clone_id}")


async def _dispatch_health_check() -> None:
    from app.workers.health_check_task import _check_all

    if await _is_paused(JobName.HEALTH_CHECK):
        return
    await job_queue.enqueue(
        lambda: _run_tracked(JobName.HEALTH_CHECK, _check_all), key="health-check"
    )


async def _dispatch_job_health() -> None:
    from app.workers.health_check_task import _check_jobs

    if await _is_paused(JobName.HEALTH_CHECK):
        return
    await job_queue.enqueue(
        lambda: _run_tracked(JobName.HEALTH_CHECK, _check_jobs), key="health-check-jobs"
    )


async def _dispatch_wake_cooldowns() -> None:
    from app.workers.health_check_task import _wake

    if await _is_paused(JobName.HEALTH_CHECK):
        return
    await job_queue.enqueue(
        lambda: _run_tracked(JobName.HEALTH_CHECK, _wake), key="wake-cooldowns"
    )


async def _dispatch_publisher() -> None:
    from app.workers.publisher_task import _due_publishes, _execute_one

    if await _is_paused(JobName.PR_POST):
        return
    pub_ids = await _due_publishes()
    for pub_id in pub_ids:
        await job_queue.enqueue(
            lambda publish=pub_id: _run_tracked(
                JobName.PR_POST, lambda: _execute_one(publish)
            ),
            key=f"publish:{pub_id}",
        )


async def _dispatch_maintenance() -> None:
    from app.workers.maintenance_task import recover_stale_jobs, deliver_notifications

    await recover_stale_jobs()
    await deliver_notifications()


def start_scheduler() -> None:
    """Goi 1 lan trong lifespan khi RUN_MODE=desktop."""
    job_queue.set_default_timeout(get_settings().browser_operation_timeout_seconds)
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
        _dispatch_job_health, "interval", seconds=1800, id="health-check-jobs"
    )
    scheduler.add_job(
        _dispatch_wake_cooldowns, "interval", seconds=600, id="wake-cooldowns"
    )
    scheduler.add_job(
        _dispatch_publisher, "interval", seconds=60, id="publisher-process-queue"
    )
    scheduler.start()
    scheduler.add_job(_dispatch_maintenance, "interval", seconds=30, id="durable-maintenance", max_instances=1)
    logger.info("Scheduler desktop da khoi dong: 8 job dang ky")


def readiness_snapshot() -> dict[str, object]:
    snapshot = job_queue.readiness()
    scheduler_running = bool(scheduler.running)
    snapshot["scheduler_running"] = scheduler_running
    if not scheduler_running:
        snapshot["status"] = "not_ready"
    return snapshot


async def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    await job_queue.stop()
