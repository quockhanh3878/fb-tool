# plan: docs/plans/desktop_packaging.md
"""
Telegram long-polling cho chế độ desktop (RUN_MODE=desktop, xem app/main.py).

Webhook cần URL public — máy khách chạy local không có, nên nút bấm Telegram
(ứng tuyển / xem trước / bỏ qua) và lệnh `/start <mã>` liên kết chat sẽ không
bao giờ tới backend. Poller hỏi `getUpdates` liên tục rồi đưa từng Update vào
đúng `routers/telegram_webhook.handle_update` mà webhook SaaS đang dùng, để
hai đường không lệch hành vi.

Token đọc lại mỗi vòng: khách có thể nhập token ở màn Cài đặt khi app đang chạy.
"""
import asyncio
import logging

from app.config import get_settings
from app.database import get_session_factory
from app.routers.telegram_webhook import handle_update
from app.services.notification_service import NotificationService

logger = logging.getLogger("commhunter.telegram_poller")

LONG_POLL_TIMEOUT_SEC = 25
IDLE_SLEEP_SEC = 10  # chưa cấu hình token
ERROR_BACKOFF_SEC = 30  # mạng lỗi / Telegram từ chối
HTTP_CONFLICT = 409  # bot đang gắn webhook -> getUpdates bị từ chối


async def poll_once(offset: int, notifier: NotificationService) -> tuple[int, bool]:
    """Một vòng getUpdates. Trả (offset kế tiếp, vòng này có gọi Telegram OK không).

    Chỉ xác nhận offset sau khi transaction xử lý đã thành công.
    """
    result = await notifier.get_updates(offset, timeout=LONG_POLL_TIMEOUT_SEC)
    if not result or result.get("ok") is not True:
        if result and result.get("status") == HTTP_CONFLICT:
            logger.warning(
                "Telegram poller: bot dang gan webhook nen getUpdates bi tu choi (409). "
                "Go webhook cua bot (deleteWebhook) de dung che do desktop."
            )
        else:
            logger.warning("Telegram poller: getUpdates loi: %s", result)
        return offset, False

    for update in result.get("result") or []:
        update_id = int(update.get("update_id", offset - 1))
        try:
            async with get_session_factory()() as db:
                await handle_update(db, update, notifier)
            offset = max(offset, update_id + 1)
        except Exception:
            logger.warning("Telegram update processing failed; retry pending")
            return offset, False
    return offset, True


class TelegramPoller:
    """Vòng long-polling chạy nền trong tiến trình API desktop."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        offset = 0
        active_token = ""
        while True:
            token = get_settings().telegram_bot_token
            if not token:
                await asyncio.sleep(IDLE_SLEEP_SEC)
                continue
            if token != active_token:
                # update_id thuộc riêng từng bot: đổi bot mà giữ offset cũ sẽ nuốt mất update.
                offset, active_token = 0, token
            offset, ok = await poll_once(offset, NotificationService(bot_token=token))
            if not ok:
                await asyncio.sleep(ERROR_BACKOFF_SEC)


telegram_poller = TelegramPoller()
