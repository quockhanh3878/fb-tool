"""
Webhook Telegram — thay cho polling của Phase 1 (chế độ SaaS).

Chế độ desktop không có URL public để nhận webhook nên dùng long-polling
(workers/telegram_poller.py), gọi lại đúng `handle_update` bên dưới.

Bảo mật: Telegram gửi kèm header `X-Telegram-Bot-Api-Secret-Token`; nếu
TELEGRAM_WEBHOOK_SECRET được đặt mà header sai thì từ chối. Nếu không có
lớp này, bất kỳ ai biết URL đều có thể giả lệnh "ứng tuyển" cho khách hàng.
"""
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.base import as_utc, utcnow
from app.models.campaign import Campaign
from app.models.enums import PostStatus
from app.models.post import DiscoveredPost
from app.models.user import User
from app.models.operations import TelegramUpdate
from app.dependencies import rate_limit
from app.services.execution_policy import lock_user, require_comment_policy
from app.services.outbox_service import bot_scope, queue_text
from app.services.ai_service import AIService
from app.services.notification_service import NotificationService
from app.services.pipeline import build_comment, count_today_actions, queue_comment

router = APIRouter(prefix="/api/webhook", tags=["telegram"])


class TelegramChat(BaseModel):
    id: int = Field(strict=True)
    type: Literal["private"]


class TelegramMessage(BaseModel):
    chat: TelegramChat
    text: str = Field(default="", max_length=4096)


class TelegramCallback(BaseModel):
    message: TelegramMessage
    data: str = Field(max_length=128)


class TelegramEnvelope(BaseModel):
    update_id: int = Field(ge=0, strict=True)
    message: TelegramMessage | None = None
    callback_query: TelegramCallback | None = None


def _ai() -> AIService:
    settings = get_settings()
    return AIService(settings.openai_api_key, settings.openai_model)


async def _user_by_chat(db: AsyncSession, chat_id: str) -> User | None:
    result = await db.execute(select(User).where(User.telegram_chat_id == str(chat_id), User.is_active.is_(True)))
    return result.scalar_one_or_none()


async def _handle_start(db: AsyncSession, chat_id: str, text: str) -> str:
    """`/start <mã>` — gắn chat Telegram vào tài khoản web."""
    parts = text.split(maxsplit=1)
    code = parts[1].strip().upper() if len(parts) > 1 else ""
    if not code:
        return (
            "👋 Chào bạn! Hãy vào Dashboard → Cài đặt → Kết nối Telegram để lấy mã, "
            "rồi gửi: /start <mã>"
        )

    result = await db.execute(select(User).where(User.telegram_link_code == code))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or not user.telegram_link_expires_at or as_utc(user.telegram_link_expires_at) <= utcnow():
        return "❌ Mã liên kết không đúng hoặc đã được dùng."
    await lock_user(db, user.id)
    linked = await _user_by_chat(db, chat_id)
    if linked is not None and linked.id != user.id:
        return "❌ Chat đã liên kết với tài khoản khác."
    claimed = await db.execute(sql_update(User).where(
        User.id == user.id, User.telegram_link_code == code,
        User.telegram_link_expires_at > utcnow(),
    ).values(telegram_chat_id=str(chat_id), telegram_link_code=None, telegram_link_expires_at=None))
    if claimed.rowcount != 1:
        return "❌ Mã liên kết không đúng hoặc đã được dùng."
    return f"✅ Đã liên kết Telegram với tài khoản {user.email}."


async def _handle_callback(db: AsyncSession, chat_id: str, data: str) -> str:
    """Xử lý nút Inline Keyboard: apply / preview / skip."""
    try:
        action, post_id = data.split(":", 1)
    except ValueError:
        return "⚠️ Dữ liệu nút bấm không hợp lệ."

    user = await _user_by_chat(db, chat_id)
    if user is None:
        return "❌ Chat này chưa liên kết với tài khoản nào."

    post = await db.get(DiscoveredPost, post_id)
    if post is None:
        return "⚠️ Không tìm thấy bài viết."

    campaign = await db.get(Campaign, post.campaign_id)
    # Chặn chéo tenant: chat của khách A không được thao tác bài của khách B.
    if campaign is None or campaign.user_id != user.id:
        return "❌ Bạn không có quyền với bài viết này."

    if action == "skip":
        await lock_user(db, user.id)
        post.status = PostStatus.SKIPPED.value
        post.ai_reason = "user_skipped_telegram"
        return "👍 Đã bỏ qua bài viết."

    if action in ("apply", "preview"):
        await require_comment_policy(db, campaign, post)
        comment_text, script = await build_comment(db, campaign, post, _ai())
        if not comment_text:
            return "⚠️ Không sinh được comment. Kiểm tra kịch bản hoặc OpenAI API key."

        if action == "preview":
            return f"📋 Bản nháp comment:\n\n{comment_text}"

        quota = int(campaign.max_comments_per_day or 20)
        used = await count_today_actions(db, campaign.id)
        if used >= quota:
            return f"⛔ Đã đạt trần {quota} comment/ngày. Tạm dừng tới ngày mai."

        await queue_comment(db, campaign, post, comment_text, script)
        return f"🚀 Đã xếp hàng comment:\n\n{comment_text}"

    return "⚠️ Nút bấm không được hỗ trợ."


async def _process_update(
    db: AsyncSession, update: dict, notifier: NotificationService
) -> str:
    """Xử lý 1 Update Telegram, trả nhãn đã xử lý.

    Dùng chung cho webhook (SaaS) và long-polling (desktop,
    workers/telegram_poller.py) để hai đường không lệch hành vi.
    """
    callback = update.get("callback_query")
    if callback:
        chat_id = str(
            ((callback.get("message") or {}).get("chat") or {}).get("id", "")
        )
        try:
            async with db.begin_nested():
                reply = await _handle_callback(db, chat_id, callback.get("data") or "")
        except HTTPException as exc:
            reply = str(exc.detail)
        await queue_text(db, chat_id, reply)
        return "callback_query"

    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if text.startswith("/start"):
        try:
            async with db.begin_nested():
                reply = await _handle_start(db, chat_id, text)
        except IntegrityError:
            reply = "Chat đã được liên kết; vui lòng kiểm tra lại tài khoản."
        await queue_text(db, chat_id, reply)
        return "start"

    if text.startswith("/status"):
        user = await _user_by_chat(db, chat_id)
        if user is None:
            await queue_text(db, chat_id, "❌ Chat chưa liên kết tài khoản.")
        else:
            campaigns = await db.execute(
                select(Campaign).where(Campaign.user_id == user.id)
            )
            rows = list(campaigns.scalars().all())
            active = sum(1 for c in rows if c.is_active)
            await queue_text(
                db, chat_id,
                f"📊 Tài khoản {user.email}\n"
                f"Chiến dịch: {len(rows)} (đang chạy: {active})",
            )
        return "status"

    return "ignored"


async def handle_update(db: AsyncSession, update: dict, notifier: NotificationService) -> str:
    try:
        envelope = TelegramEnvelope.model_validate(update)
    except ValidationError:
        return "ignored_invalid_update"
    key = f"{bot_scope(notifier.bot_token)}:{envelope.update_id}"
    await db.execute(sql_update(TelegramUpdate).where(
        TelegramUpdate.id == key,
    ).values(id=TelegramUpdate.id))
    try:
        async with db.begin_nested():
            db.add(TelegramUpdate(id=key))
            await db.flush()
    except IntegrityError:
        return "duplicate"
    handled = await _process_update(db, envelope.model_dump(exclude_none=True), notifier)
    await db.commit()
    return handled


@router.post("/telegram", dependencies=[Depends(rate_limit("telegram-webhook", 120))])
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = get_settings()
    if settings.run_mode != "saas":
        raise HTTPException(status_code=404, detail="Not Found")
    if not settings.telegram_webhook_secret or not secrets.compare_digest(
        x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Secret token không hợp lệ")

    try:
        update = await request.json()
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid update") from None
    handled = await handle_update(db, update, NotificationService())
    return {"ok": True, "handled": handled}
