# plan: docs/plans/desktop_packaging.md
"""
SerialJobQueue — thay `worker_prefetch_multiplier=1` + `task_acks_late` của
Celery cho chế độ desktop (RUN_MODE=desktop, xem app/main.py).

Chỉ dùng khi KHÔNG có Celery worker (1 máy/1 khách): mọi job con (quét 1
group, đăng 1 comment, đăng 1 bài, chạy 1 bước warmup...) được xếp vào 1
hàng đợi asyncio DUY NHẤT, chạy tuần tự — đảm bảo không có 2 hành động
Facebook nào của cùng một clone (hoặc khác clone) chạy song song trên máy
khách, đúng lý do Celery từng đặt `worker_prefetch_multiplier=1`.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

logger = logging.getLogger("commhunter.job_queue")

Job = Callable[[], Awaitable[object]]


class SerialJobQueue:
    """Hàng đợi asyncio tuần tự — 1 job chạy xong mới tới job kế tiếp."""

    def __init__(self, maxsize: int = 128, default_timeout_seconds: float = 1200.0) -> None:
        self._queue: asyncio.Queue[tuple[str, Job, float]] = asyncio.Queue(maxsize=maxsize)
        self._pending: set[str] = set()
        self._worker_task: asyncio.Task | None = None
        self._default_timeout_seconds = default_timeout_seconds
        self._running_key: str | None = None
        self._heartbeat_at: str | None = None
        self._last_started_at: str | None = None
        self._last_finished_at: str | None = None
        self._last_error_at: str | None = None
        self._last_error_key: str | None = None
        self._last_error_kind: str | None = None

    def start(self) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run())

    def set_default_timeout(self, seconds: float) -> None:
        if seconds <= 0:
            raise ValueError("job timeout must be positive")
        self._default_timeout_seconds = seconds

    def readiness(self) -> dict[str, object]:
        worker_alive = self._worker_task is not None and not self._worker_task.done()
        return {
            "status": "ready" if worker_alive else "not_ready",
            "worker_alive": worker_alive,
            "queue_depth": self._queue.qsize(),
            "pending_count": len(self._pending),
            "running_job": self._running_key,
            "heartbeat_at": self._heartbeat_at,
            "last_job_started_at": self._last_started_at,
            "last_job_finished_at": self._last_finished_at,
            "last_error_at": self._last_error_at,
            "last_error_key": self._last_error_key,
            "last_error_kind": self._last_error_kind,
        }

    async def stop(self) -> None:
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
        self._pending.clear()

    async def enqueue(
        self,
        job: Job,
        *,
        key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> bool:
        identity = key or str(id(job))
        timeout = self._default_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            raise ValueError("job timeout must be positive")
        if identity in self._pending:
            return False
        try:
            self._queue.put_nowait((identity, job, timeout))
        except asyncio.QueueFull:
            return False
        self._pending.add(identity)
        self._heartbeat_at = datetime.now(timezone.utc).isoformat()
        return True

    async def _run(self) -> None:
        while True:
            identity, job, timeout = await self._queue.get()
            self._running_key = identity
            self._last_started_at = datetime.now(timezone.utc).isoformat()
            self._heartbeat_at = self._last_started_at
            try:
                await asyncio.wait_for(job(), timeout=timeout)
            except asyncio.TimeoutError:
                self._last_error_at = datetime.now(timezone.utc).isoformat()
                self._last_error_key = identity
                self._last_error_kind = "timeout"
                logger.warning("SerialJobQueue: job timed out; key=%s", identity)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Lỗi 1 job không được giết cả hàng đợi — job hỏng vốn sẽ
                # được lịch (scheduler.py) gọi lại ở chu kỳ kế tiếp.
                self._last_error_at = datetime.now(timezone.utc).isoformat()
                self._last_error_key = identity
                self._last_error_kind = "failed"
                logger.warning("SerialJobQueue: job failed; key=%s", identity)
            finally:
                self._pending.discard(identity)
                self._running_key = None
                self._last_finished_at = datetime.now(timezone.utc).isoformat()
                self._heartbeat_at = self._last_finished_at
                self._queue.task_done()


job_queue = SerialJobQueue()
