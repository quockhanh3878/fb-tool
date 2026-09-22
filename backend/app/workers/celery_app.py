"""
Celery app + lịch Beat (Phase 2 — Task 2.5.4).

Mỗi task chạy trong tiến trình riêng nên KHÔNG dùng chung AsyncSession với
API; các task tự mở session của mình qua `run_async()`.
"""
import asyncio

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_shutdown

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "commhunter",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.scout_task",
        "app.workers.shooter_task",
        "app.workers.bump_task",
        "app.workers.warmup_task",
        "app.workers.health_check_task",
        "app.workers.publisher_task",
        "app.workers.preflight_task",
        "app.workers.maintenance_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
)

celery_app.conf.beat_schedule = {
    "durable-maintenance": {
        "task": "app.workers.maintenance_task.maintain",
        "schedule": 30.0,
    },
    "scout-scan-all": {
        "task": "app.workers.scout_task.scan_all_active_campaigns",
        "schedule": 60.0,
    },
    "shooter-process-queue": {
        "task": "app.workers.shooter_task.process_comment_queue",
        "schedule": 30.0,
    },
    "bump-check-schedule": {
        "task": "app.workers.bump_task.check_bump_schedules",
        "schedule": 300.0,
    },
    "warmup-daily-step": {
        "task": "app.workers.warmup_task.run_warmup_cycle",
        "schedule": crontab(hour=9, minute=0),
    },
    "health-check-clones": {
        "task": "app.workers.health_check_task.check_all_clones",
        "schedule": 1800.0,
    },
    "wake-cooldowns": {
        "task": "app.workers.health_check_task.wake_cooldowns",
        "schedule": 600.0,
    },
    "publisher-process-queue": {
        "task": "app.workers.publisher_task.process_publish_queue",
        "schedule": 60.0,
    },
}


_runner: asyncio.Runner | None = None


def run_async(coro):
    """Run every task in a worker process on the same event loop."""
    global _runner
    if _runner is None:
        _runner = asyncio.Runner()
    return _runner.run(coro)


@worker_process_shutdown.connect
def close_worker_runtime(**kwargs):
    global _runner
    if _runner is not None:
        from app.database import dispose_engine

        try:
            _runner.run(dispose_engine())
        finally:
            _runner.close()
            _runner = None
