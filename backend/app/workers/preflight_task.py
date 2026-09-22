# plan: docs/plans/phase2_dashboard_detail.md
"""Celery task: preflight sức khoẻ nick (Track D — bổ sung 11/09/2026).

Kích hoạt theo yêu cầu (không vào Beat): mở browser kiểm tra một nick — hoặc
toàn bộ nick đang active của một khách — còn đăng nhập + không checkpoint,
đồng bộ state machine qua `preflight_service.run_preflight`.
"""
from sqlalchemy import select
from fastapi import HTTPException
from app.services.execution_policy import require_entitlement

from app.database import get_session_factory
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState
from app.services.preflight_service import run_preflight
from app.workers.celery_app import celery_app, run_async


async def _preflight_one(clone_id: str) -> dict:
    async with get_session_factory()() as db:
        clone = await db.get(CloneAccount, clone_id)
        if clone is None:
            return {"skipped": "clone_not_found"}
        try:
            await require_entitlement(db, clone.user_id)
        except HTTPException:
            return {"skipped": "policy_denied"}
        await db.commit()
        result = await run_preflight(db, clone)
        await db.commit()
        return {"clone_id": clone_id, "status": clone.status, **result}


async def _preflight_user(user_id: str) -> dict:
    async with get_session_factory()() as db:
        rows = await db.execute(
            select(CloneAccount.id).where(
                CloneAccount.user_id == user_id,
                CloneAccount.status == AccountState.ACTIVE.value,
            )
        )
        ids = [r for (r,) in rows.all()]
    checked = [await _preflight_one(cid) for cid in ids]
    return {"checked": len(checked), "items": checked}


@celery_app.task(name="app.workers.preflight_task.preflight_clone")
def preflight_clone(clone_id: str) -> dict:
    return run_async(_preflight_one(clone_id))


@celery_app.task(name="app.workers.preflight_task.preflight_user_clones")
def preflight_user_clones(user_id: str) -> dict:
    return run_async(_preflight_user(user_id))
