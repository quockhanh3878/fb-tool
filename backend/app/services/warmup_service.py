"""
Warm-up Pipeline 7 ngày (Phase 3 — Task 3.2).

Lịch ủ ấm được mô tả bằng DỮ LIỆU (WARMUP_SCHEDULE) thay vì if/elif rải rác,
nhờ vậy dashboard hiển thị được tiến trình và bộ test kiểm tra được lịch mà
không cần mở browser.
"""
from dataclasses import dataclass, field

from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, AccountTransition, HealthEventType
from app.services.account_manager import AccountManager


@dataclass(frozen=True)
class WarmupStep:
    day: int
    label: str
    duration_minutes: int
    browse_minutes: int = 0
    watch_reels: int = 0
    like_posts: int = 0
    comment_posts: int = 0
    join_groups: int = 0
    health_check: bool = False
    actions: tuple = field(default=())


WARMUP_SCHEDULE: tuple[WarmupStep, ...] = (
    WarmupStep(1, "Lướt Newsfeed", 5, browse_minutes=5, actions=("browse",)),
    WarmupStep(2, "Lướt Newsfeed + xem 2 Reels", 8, browse_minutes=3, watch_reels=2,
               actions=("browse", "reels")),
    WarmupStep(3, "Like 3 bài ngẫu nhiên", 3, like_posts=3, actions=("like",)),
    WarmupStep(4, "Like 5 bài + xem Reels", 8, like_posts=5, watch_reels=2,
               actions=("like", "reels")),
    WarmupStep(5, "Comment 1 bài ngắn", 5, comment_posts=1, actions=("comment",)),
    WarmupStep(6, "Comment 2 bài + tham gia 2-3 group", 10, comment_posts=2,
               join_groups=3, actions=("comment", "join")),
    WarmupStep(7, "Kiểm tra sức khoẻ tổng thể", 3, health_check=True,
               actions=("health_check",)),
)

TOTAL_WARMUP_DAYS = len(WARMUP_SCHEDULE)
# Ngày quay lại khi health check cuối chu kỳ không đạt (kéo dài ủ ấm).
WARMUP_RETRY_DAY = 5


def get_step(day: int) -> WarmupStep:
    """Lấy bước ủ ấm của ngày thứ `day` (ngày > 7 dùng bước cuối)."""
    if day < 1:
        day = 1
    index = min(day, TOTAL_WARMUP_DAYS) - 1
    return WARMUP_SCHEDULE[index]


def warmup_progress(clone: CloneAccount) -> dict:
    """Tiến trình ủ ấm để hiển thị progress bar trên Health Dashboard."""
    day = max(0, min(clone.warmup_day or 0, TOTAL_WARMUP_DAYS))
    return {
        "day": day,
        "total_days": TOTAL_WARMUP_DAYS,
        "percent": round(day / TOTAL_WARMUP_DAYS * 100, 1),
        "next_step": get_step(day + 1).label if day < TOTAL_WARMUP_DAYS else "Hoàn tất",
    }


class WarmupService:
    """Chạy 1 bước ủ ấm mỗi ngày cho 1 clone.

    Lớp này KHÔNG tự mở browser: nó nhận `executor` (async callable nhận
    (clone, step) và thực thi hành vi trên Playwright). Nhờ vậy Celery task
    dùng executor thật, còn test dùng executor giả.
    """

    def __init__(self, db, notifier=None, executor=None):
        self.db = db
        self.manager = AccountManager(db, notifier=notifier)
        self.executor = executor

    async def run_daily_step(self, clone: CloneAccount) -> dict:
        """Thực hiện bước ủ ấm kế tiếp. Trả về tóm tắt kết quả."""
        if clone.status != AccountState.WARMING_UP.value:
            return {"skipped": True, "reason": f"clone đang ở trạng thái {clone.status}"}

        day = (clone.warmup_day or 0) + 1
        step = get_step(day)

        if self.executor is not None:
            result = await self.executor(clone, step)
            # executor trả về False khi gặp checkpoint giữa chừng
            if result is False:
                await self.manager.transition(
                    clone,
                    AccountTransition.CHECKPOINT_DETECTED,
                    f"Checkpoint trong lúc ủ ấm ngày {day}",
                )
                return {"day": day, "checkpoint": True}

        if step.health_check:
            healthy = True if self.executor is None else bool(result)
            if healthy:
                clone.warmup_day = TOTAL_WARMUP_DAYS
                await self.manager.log_event(
                    clone, HealthEventType.WARMUP_DONE, "Hoàn tất 7 ngày ủ ấm"
                )
                await self.manager.transition(
                    clone, AccountTransition.WARMUP_COMPLETE, "Health check đạt"
                )
                return {"day": day, "completed": True, "step": step.label}
            # Chưa khoẻ: lùi về ngày 5, ủ thêm 2 ngày nữa
            clone.warmup_day = WARMUP_RETRY_DAY
            await self.manager.log_event(
                clone, HealthEventType.STATE_CHANGED, "Health check chưa đạt, ủ ấm thêm"
            )
            await self.db.flush()
            return {"day": day, "completed": False, "retry_from_day": WARMUP_RETRY_DAY}

        clone.warmup_day = day
        await self.db.flush()
        return {"day": day, "completed": False, "step": step.label}
