# plan: docs/plans/community_job_runner_plan.md
"""Durable job tracking, stale-job detection, and a small circuit breaker."""
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import as_utc, utcnow
from app.models.job import JobRun
from app.services.notification_service import notify_error


class JobName(StrEnum):
    PR_POST = "PR_POST"
    PR_BUMP = "PR_BUMP"
    LEAD_SCAN = "LEAD_SCAN"
    LEAD_MATCH = "LEAD_MATCH"
    LEAD_REPLY = "LEAD_REPLY"
    PAGE_MONITOR = "PAGE_MONITOR"
    HANDOFF = "HANDOFF"
    HEALTH_CHECK = "HEALTH_CHECK"


JOB_INTERVALS_SECONDS = {
    JobName.PR_POST: 24 * 60 * 60,
    JobName.PR_BUMP: 5 * 60,
    JobName.LEAD_SCAN: 60 * 60,
    JobName.LEAD_MATCH: 60 * 60,
    JobName.LEAD_REPLY: 60 * 60,
    JobName.PAGE_MONITOR: 15 * 60,
    JobName.HANDOFF: 5 * 60,
    JobName.HEALTH_CHECK: 30 * 60,
}

ERROR_STATUSES = {"error", "paused"}


def _job_value(job_name: JobName | str) -> str:
    return job_name.value if isinstance(job_name, JobName) else str(job_name)


async def start_job(
    db: AsyncSession,
    job_name: JobName | str,
    *,
    user_id: str | None = None,
    started_at: datetime | None = None,
) -> JobRun:
    run = JobRun(
        user_id=user_id,
        job_name=_job_value(job_name),
        started_at=started_at or utcnow(),
        status="running",
        counts={},
    )
    db.add(run)
    await db.flush()
    return run


async def finish_job(
    db: AsyncSession,
    run: JobRun,
    *,
    counts: dict | None = None,
    finished_at: datetime | None = None,
) -> JobRun:
    run.status = "success"
    run.finished_at = finished_at or utcnow()
    run.counts = counts or {}
    run.error = None
    await db.flush()
    return run


async def fail_job(
    db: AsyncSession,
    run: JobRun,
    error: str,
    *,
    max_consecutive_failures: int = 3,
    finished_at: datetime | None = None,
    notify: bool = True,
) -> JobRun:
    run.status = "error"
    run.finished_at = finished_at or utcnow()
    run.error = (error or "job_error")[:2000]
    await db.flush()

    recent = list((await db.scalars(
        select(JobRun)
        .where(JobRun.job_name == run.job_name, JobRun.user_id == run.user_id)
        .order_by(JobRun.started_at.desc())
        .limit(max_consecutive_failures)
    )).all())
    failures = 0
    for item in recent:
        if item.status not in ERROR_STATUSES:
            break
        failures += 1
    if failures >= max_consecutive_failures:
        run.status = "paused"
        await db.flush()
        if notify and run.user_id:
            await notify_error(
                db,
                user_id=run.user_id,
                summary=(
                    f"Job {run.job_name} đã tạm dừng sau {failures} lỗi liên tiếp. "
                    "Cần người vận hành kiểm tra và chạy lại."
                ),
                source="HEALTH_CHECK",
                occurred_at=run.finished_at,
                dedup_key=f"job-paused:{run.user_id}:{run.job_name}",
            )
    return run


async def latest_job_run(
    db: AsyncSession,
    job_name: JobName | str,
    *,
    user_id: str | None = None,
) -> JobRun | None:
    return await db.scalar(
        select(JobRun)
        .where(JobRun.job_name == _job_value(job_name), JobRun.user_id == user_id)
        .order_by(JobRun.started_at.desc())
        .limit(1)
    )


async def check_job_health(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    grace_multiplier: float = 2.0,
) -> dict:
    """Report stale/paused jobs and enqueue one deduplicated ERROR per job."""
    current = as_utc(now) or utcnow()
    rows = list((await db.scalars(
        select(JobRun).order_by(JobRun.job_name, JobRun.user_id, JobRun.started_at.desc())
    )).all())
    latest: dict[tuple[str, str | None], JobRun] = {}
    for row in rows:
        latest.setdefault((row.job_name, row.user_id), row)

    stale: list[dict] = []
    paused: list[dict] = []
    for (job_name, user_id), row in latest.items():
        if row.status == "paused":
            paused.append({"job_name": job_name, "user_id": user_id})
            continue
        finished = as_utc(row.finished_at) or as_utc(row.started_at)
        interval = JOB_INTERVALS_SECONDS.get(job_name, 1800)
        if finished is None or current - finished <= timedelta(seconds=interval * grace_multiplier):
            continue
        item = {
            "job_name": job_name,
            "user_id": user_id,
            "age_seconds": int((current - finished).total_seconds()),
        }
        stale.append(item)
        if user_id:
            await notify_error(
                db,
                user_id=user_id,
                summary=f"Job {job_name} không chạy đúng hạn; cần kiểm tra worker.",
                source="HEALTH_CHECK",
                occurred_at=current,
                dedup_key=f"job-stale:{user_id}:{job_name}",
            )
    return {"checked": len(latest), "stale": stale, "paused": paused}
