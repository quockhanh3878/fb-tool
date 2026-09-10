"""
Celery Task: Xử lý hàng đợi đăng bài tự động (Publisher Task).

Quét các bản ghi post_publishes đến hạn và phân bổ cho clone có vai trò Poster.
"""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import get_session_factory
from app.models.enums import PublishStatus
from app.models.post import PostPublish
from app.services.publisher_service import as_utc, execute_publish
from app.workers.celery_app import celery_app


def run_async(coro):
    return asyncio.run(coro)


async def _due_publishes() -> list[str]:
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        result = await db.execute(
            select(PostPublish)
            .where(PostPublish.status == PublishStatus.SCHEDULED.value)
            .order_by(PostPublish.scheduled_at.asc())
            .limit(10)
        )
        return [
            item.id
            for item in result.scalars().all()
            if as_utc(item.scheduled_at) is None or as_utc(item.scheduled_at) <= now
        ]


@celery_app.task(name="app.workers.publisher_task.process_publish_queue")
def process_publish_queue() -> dict:
    """Task định kỳ quét các bài đăng đến hạn."""
    due_ids = run_async(_due_publishes())
    processed = []
    for pub_id in due_ids:
        res = run_async(_execute_one(pub_id))
        processed.append(res)
    return {"processed_count": len(processed), "items": processed}


async def _execute_one(publish_id: str) -> dict:
    async with get_session_factory()() as db:
        return await execute_publish(db, publish_id)
