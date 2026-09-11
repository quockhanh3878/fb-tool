# plan: docs/plans/phase2_dashboard_detail.md
"""Preflight — kiểm tra sức khoẻ nick + phiên đăng nhập trước một lượt chạy thật
(Track D — bổ sung 11/09/2026).

Trước khi Scout quét hay Poster đăng bài không người trực, mở browser xác nhận
nick còn đăng nhập và không dính checkpoint. Không đạt → đưa nick qua state
machine (dừng nó lại) rồi báo caller huỷ lượt, thay vì để Beat 60s cứ chọn lại
đúng nick hỏng — cùng tinh thần "mode treo" của Track C.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clone_account import CloneAccount
from app.models.enums import AccountTransition
from app.services.account_manager import AccountManager, InvalidTransitionError
from app.services.notification_service import build_clone_notifier
from app.workers.browser_runtime import preflight_check_real


async def run_preflight(
    db: AsyncSession, clone: CloneAccount, *, cookies=None, prober=None
) -> dict:
    """Chạy preflight cho một clone và đồng bộ state machine theo kết quả.

    `prober`: async callable(clone, cookies) -> {"ok": bool, "reason": str} —
    mặc định `preflight_check_real`; tách ra để test offline tiêm giả.

    Trả về dict kết quả preflight (đã kèm khoá "ok"). KHÔNG commit — caller commit.
    """
    prober = prober or preflight_check_real
    result = await prober(clone, cookies)
    reason = result.get("reason", "error")

    if result.get("ok"):
        await AccountManager(db).note_ok(clone)
        return result

    mgr = AccountManager(db, notifier=await build_clone_notifier(db))
    if reason == "checkpoint":
        try:
            await mgr.transition(
                clone, AccountTransition.CHECKPOINT_DETECTED, "Preflight: phát hiện checkpoint"
            )
        except InvalidTransitionError:
            pass
    else:
        # login_expired / error / runtime_unavailable — lượt chạy hỏng, đếm dồn;
        # đủ ngưỡng thì AccountManager tự cho nick nghỉ.
        await mgr.record_failure(clone, f"Preflight không đạt: {reason}")
    return result
