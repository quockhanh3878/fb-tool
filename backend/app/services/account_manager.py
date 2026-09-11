"""
Account State Machine (Phase 3 — Task 3.1).

Mỗi clone đi qua 7 trạng thái; mọi chuyển trạng thái đều phải qua đây để:
  1. chặn chuyển trạng thái bất hợp lệ (ví dụ banned -> active),
  2. ghi log vào account_health_logs (dấu vết điều tra khi mất tài khoản),
  3. kích hoạt side-effect: hẹn giờ cooldown, cảnh báo Telegram, đổi clone dự phòng.
"""
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import as_utc, utcnow
from app.models.clone_account import AccountHealthLog, CloneAccount
from app.models.enums import AccountState, AccountTransition, HealthEventType

# Bảng chuyển trạng thái hợp lệ: (từ_trạng_thái, sự_kiện) -> trạng_thái_mới
STATE_TRANSITIONS: dict[tuple[AccountState, AccountTransition], AccountState] = {
    (AccountState.ONBOARDING, AccountTransition.COOKIE_VALID): AccountState.WARMING_UP,
    (AccountState.ONBOARDING, AccountTransition.CHECKPOINT_DETECTED): AccountState.CHECKPOINT,
    (AccountState.WARMING_UP, AccountTransition.WARMUP_COMPLETE): AccountState.ACTIVE,
    (AccountState.WARMING_UP, AccountTransition.CHECKPOINT_DETECTED): AccountState.CHECKPOINT,
    (AccountState.ACTIVE, AccountTransition.QUOTA_REACHED): AccountState.COOLDOWN,
    (AccountState.ACTIVE, AccountTransition.RATE_LIMITED): AccountState.COOLDOWN,
    (AccountState.ACTIVE, AccountTransition.CHECKPOINT_DETECTED): AccountState.CHECKPOINT,
    (AccountState.ACTIVE, AccountTransition.ROTATE): AccountState.ROTATING,
    (AccountState.COOLDOWN, AccountTransition.COOLDOWN_EXPIRED): AccountState.ACTIVE,
    (AccountState.COOLDOWN, AccountTransition.CHECKPOINT_DETECTED): AccountState.CHECKPOINT,
    (AccountState.CHECKPOINT, AccountTransition.VERIFICATION_SUCCESS): AccountState.COOLDOWN,
    (AccountState.CHECKPOINT, AccountTransition.VERIFICATION_FAILED): AccountState.BANNED,
    (AccountState.ROTATING, AccountTransition.ROTATE): AccountState.ACTIVE,
}

# Nghỉ bao lâu khi vào cooldown, tuỳ nguyên nhân (giờ).
COOLDOWN_HOURS = {
    AccountTransition.QUOTA_REACHED: (4, 8),
    AccountTransition.RATE_LIMITED: (6, 12),
    AccountTransition.VERIFICATION_SUCCESS: (48, 48),  # sau checkpoint: nghỉ 48h
}
DEFAULT_COOLDOWN_HOURS = (4, 8)

# Số lần thất bại/shadowban liên tiếp trước khi tự đưa clone đi nghỉ.
SHADOWBAN_COOLDOWN_THRESHOLD = 3
SHADOWBAN_ALERT_THRESHOLD = 5


class InvalidTransitionError(Exception):
    """Chuyển trạng thái không nằm trong bảng STATE_TRANSITIONS."""


def next_state(
    current: AccountState | str, event: AccountTransition | str
) -> AccountState:
    """Tra bảng chuyển trạng thái (hàm thuần — test offline được).

    Raises:
        InvalidTransitionError: nếu cặp (trạng thái, sự kiện) không hợp lệ.
    """
    current_state = AccountState(current)
    transition = AccountTransition(event)
    key = (current_state, transition)
    if key not in STATE_TRANSITIONS:
        raise InvalidTransitionError(
            f"Không thể '{transition.value}' khi đang ở trạng thái '{current_state.value}'"
        )
    return STATE_TRANSITIONS[key]


def cooldown_duration(event: AccountTransition, rng: random.Random | None = None) -> timedelta:
    low, high = COOLDOWN_HOURS.get(event, DEFAULT_COOLDOWN_HOURS)
    rng = rng or random
    return timedelta(hours=rng.uniform(low, high))


class AccountManager:
    """Điều phối vòng đời clone trên database."""

    def __init__(self, db: AsyncSession, notifier=None):
        self.db = db
        # notifier: async callable(user_id, message) — thường là NotificationService.
        self.notifier = notifier

    async def get_clone(self, clone_id: str) -> CloneAccount | None:
        return await self.db.get(CloneAccount, clone_id)

    async def log_event(
        self,
        clone: CloneAccount,
        event_type: HealthEventType,
        details: str = "",
        from_state: str | None = None,
        to_state: str | None = None,
    ) -> AccountHealthLog:
        entry = AccountHealthLog(
            clone_account_id=clone.id,
            event_type=event_type.value,
            details=details,
            from_state=from_state,
            to_state=to_state,
        )
        self.db.add(entry)
        return entry

    async def transition(
        self,
        clone: CloneAccount,
        event: AccountTransition,
        details: str = "",
    ) -> CloneAccount:
        """Chuyển trạng thái + ghi log + chạy side-effect."""
        from_state = clone.status
        to_state = next_state(from_state, event)

        clone.status = to_state.value
        clone.last_activity_at = utcnow()

        if to_state is AccountState.COOLDOWN:
            clone.cooldown_until = utcnow() + cooldown_duration(event)
        elif to_state is AccountState.WARMING_UP:
            clone.warmup_day = 0
            clone.warmup_started_at = utcnow()
        elif to_state is AccountState.ACTIVE:
            clone.cooldown_until = None
            clone.consecutive_failures = 0
        elif to_state is AccountState.CHECKPOINT:
            clone.last_checkpoint_at = utcnow()

        await self.log_event(
            clone,
            HealthEventType.STATE_CHANGED,
            details or f"{from_state} → {to_state.value} ({event.value})",
            from_state=from_state,
            to_state=to_state.value,
        )

        await self._side_effects(clone, to_state, event)
        await self.db.flush()
        return clone

    async def _side_effects(
        self, clone: CloneAccount, to_state: AccountState, event: AccountTransition
    ) -> None:
        if to_state is AccountState.CHECKPOINT:
            await self.log_event(
                clone, HealthEventType.CHECKPOINT, "Phát hiện checkpoint, tạm dừng mọi task"
            )
            await self._notify(
                clone,
                f"Clone '{clone.display_name}' bị checkpoint! Cần xác minh thủ công.",
            )
            await self.try_switch_to_backup(clone)
        elif to_state is AccountState.BANNED:
            clone.is_backup = False
            await self.log_event(clone, HealthEventType.BANNED, "Clone bị ban")
            switched = await self.try_switch_to_backup(clone)
            if switched:
                await self._notify(
                    clone,
                    f"Clone '{clone.display_name}' bị ban. Đã chuyển sang "
                    f"clone dự phòng '{switched.display_name}'.",
                )
            else:
                await self._notify(
                    clone,
                    f"Clone '{clone.display_name}' bị ban và KHÔNG còn clone dự phòng. "
                    "Vui lòng thêm clone mới.",
                )
        elif to_state is AccountState.COOLDOWN and event is AccountTransition.RATE_LIMITED:
            await self.log_event(
                clone, HealthEventType.RATE_LIMITED, "Bị giới hạn tốc độ, cho nghỉ"
            )

    async def _notify(self, clone: CloneAccount, message: str) -> None:
        if self.notifier is None:
            return
        await self.notifier(clone.user_id, message)

    async def find_backup_clone(self, clone: CloneAccount) -> CloneAccount | None:
        """Tìm clone khác cùng chủ, cùng vai trò, đang sẵn sàng nhận việc."""
        usable = (AccountState.ACTIVE.value, AccountState.COOLDOWN.value)
        result = await self.db.execute(
            select(CloneAccount)
            .where(
                CloneAccount.user_id == clone.user_id,
                CloneAccount.id != clone.id,
                CloneAccount.status.in_(usable),
            )
            .order_by(CloneAccount.is_backup.desc(), CloneAccount.created_at.asc())
        )
        candidates = list(result.scalars().all())
        same_role = [
            c
            for c in candidates
            if c.role == clone.role
            or "all" in (c.role, clone.role)
            or ("both" in (c.role, clone.role) and {c.role, clone.role}.issubset({"scout", "shooter", "both"}))
        ]
        return (same_role or candidates or [None])[0]

    async def try_switch_to_backup(self, clone: CloneAccount) -> CloneAccount | None:
        """Đưa clone dự phòng vào vận hành thay clone gặp sự cố."""
        backup = await self.find_backup_clone(clone)
        if backup is None:
            return None
        backup.is_backup = False
        if backup.status == AccountState.COOLDOWN.value:
            backup.status = AccountState.ACTIVE.value
            backup.cooldown_until = None
        await self.log_event(
            backup,
            HealthEventType.STATE_CHANGED,
            f"Nhận việc thay clone '{clone.display_name}'",
            from_state=clone.status,
            to_state=backup.status,
        )
        await self.db.flush()
        return backup

    async def record_failure(
        self, clone: CloneAccount, reason: str, shadowban: bool = False
    ) -> CloneAccount:
        """Ghi nhận 1 lượt comment hỏng và tự cho nghỉ nếu hỏng liên tiếp."""
        clone.consecutive_failures = (clone.consecutive_failures or 0) + 1
        await self.log_event(
            clone,
            HealthEventType.SHADOWBAN if shadowban else HealthEventType.COMMENT_BLOCKED,
            reason,
        )

        if (
            clone.consecutive_failures >= SHADOWBAN_COOLDOWN_THRESHOLD
            and clone.status == AccountState.ACTIVE.value
        ):
            await self.transition(
                clone,
                AccountTransition.RATE_LIMITED,
                f"Tự cho nghỉ sau {clone.consecutive_failures} lượt hỏng liên tiếp",
            )
        if clone.consecutive_failures >= SHADOWBAN_ALERT_THRESHOLD:
            await self._notify(
                clone,
                f"Clone '{clone.display_name}' hỏng {clone.consecutive_failures} lượt "
                "liên tiếp — nghi bị hạn chế. Hãy kiểm tra tài khoản.",
            )
        await self.db.flush()
        return clone

    async def note_ok(self, clone: CloneAccount) -> None:
        """Một lượt việc KHÔNG-phải-comment (quét, đăng bài) chạy trót lọt.

        Chỉ xoá bộ đếm hỏng liên tiếp + dập nhịp hoạt động — KHÔNG đụng
        `daily_comment_count` như `record_success` (quét/đăng bài không phải
        comment). Dùng cho "mode treo" để một lượt tốt reset ngưỡng tự-nghỉ.
        """
        if clone.consecutive_failures:
            clone.consecutive_failures = 0
        clone.last_activity_at = utcnow()
        await self.db.flush()

    async def record_success(self, clone: CloneAccount) -> None:
        clone.consecutive_failures = 0
        clone.last_activity_at = utcnow()
        today = datetime.now(timezone.utc).date().isoformat()
        if clone.daily_counter_date != today:
            clone.daily_counter_date = today
            clone.daily_comment_count = 0
        clone.daily_comment_count += 1
        await self.db.flush()

    async def wake_expired_cooldowns(self) -> list[CloneAccount]:
        """Đưa các clone đã hết hạn nghỉ trở lại Active (Celery Beat gọi định kỳ)."""
        result = await self.db.execute(
            select(CloneAccount).where(
                CloneAccount.status == AccountState.COOLDOWN.value,
                CloneAccount.cooldown_until.is_not(None),
            )
        )
        now = datetime.now(timezone.utc)
        woken = []
        for clone in result.scalars().all():
            if as_utc(clone.cooldown_until) and as_utc(clone.cooldown_until) <= now:
                await self.transition(
                    clone, AccountTransition.COOLDOWN_EXPIRED, "Hết thời gian nghỉ"
                )
                woken.append(clone)
        return woken
