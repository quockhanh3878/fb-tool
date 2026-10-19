# plan: docs/plans/community_job_runner_plan.md
"""Operational view and operator controls for the eight community jobs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import utcnow
from app.models.job import JobRun
from app.models.user import User
from app.schemas import JobStatusOut
from app.services.job_registry import JobName

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


async def _latest_for_user(db: AsyncSession, user_id: str) -> dict[str, JobRun | None]:
    rows = list(
        (
            await db.scalars(
                select(JobRun)
                .where(or_(JobRun.user_id == user_id, JobRun.user_id.is_(None)))
                .order_by(JobRun.job_name.asc(), JobRun.started_at.desc())
            )
        ).all()
    )
    latest_user: dict[str, JobRun] = {}
    latest_global: dict[str, JobRun] = {}
    for row in rows:
        target = latest_global if row.user_id is None else latest_user
        target.setdefault(row.job_name, row)
    return {name: latest_user.get(name, latest_global.get(name)) for name in set(latest_user) | set(latest_global)}


def _serialize(name: str, run: JobRun | None) -> JobStatusOut:
    if run is None:
        return JobStatusOut(job_name=name, status="waiting")
    return JobStatusOut(
        job_name=name,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        error=run.error,
        counts=run.counts or {},
    )


@router.get("", response_model=list[JobStatusOut])
async def list_jobs(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    latest = await _latest_for_user(db, user.id)
    return [_serialize(name.value, latest.get(name.value)) for name in JobName]


@router.post("/{job_name}/pause", response_model=JobStatusOut)
async def pause_job(
    job_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        name = JobName(job_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy job") from exc
    # Scheduler runs in the desktop process without a request user. Keep the
    # operator control global, while the response still requires auth.
    run = JobRun(
        user_id=None,
        job_name=name.value,
        started_at=utcnow(),
        finished_at=utcnow(),
        status="paused",
        counts={"source": "operator"},
        error="paused_by_operator",
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return _serialize(name.value, run)


@router.post("/{job_name}/resume", response_model=JobStatusOut)
async def resume_job(
    job_name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        name = JobName(job_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Không tìm thấy job") from exc
    run = JobRun(
        user_id=None,
        job_name=name.value,
        started_at=utcnow(),
        finished_at=utcnow(),
        status="success",
        counts={"source": "operator", "resumed": True},
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return _serialize(name.value, run)
