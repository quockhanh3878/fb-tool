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
from typing import Awaitable, Callable

logger = logging.getLogger("commhunter.job_queue")

Job = Callable[[], Awaitable[object]]


class SerialJobQueue:
    """Hàng đợi asyncio tuần tự — 1 job chạy xong mới tới job kế tiếp."""

    def __init__(self, maxsize: int = 128) -> None:
        self._queue: asyncio.Queue[tuple[str, Job]] = asyncio.Queue(maxsize=maxsize)
        self._pending: set[str] = set()
        self._worker_task: asyncio.Task | None = None

    def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._run())

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

    async def enqueue(self, job: Job, *, key: str | None = None) -> bool:
        identity = key or str(id(job))
        if identity in self._pending:
            return False
        try:
            self._queue.put_nowait((identity, job))
        except asyncio.QueueFull:
            return False
        self._pending.add(identity)
        return True

    async def _run(self) -> None:
        while True:
            identity, job = await self._queue.get()
            try:
                await job()
            except Exception:
                # Lỗi 1 job không được giết cả hàng đợi — job hỏng vốn sẽ
                # được lịch (scheduler.py) gọi lại ở chu kỳ kế tiếp.
                logger.warning("SerialJobQueue: job failed; durable state requires review")
            finally:
                self._pending.discard(identity)
                self._queue.task_done()


job_queue = SerialJobQueue()
