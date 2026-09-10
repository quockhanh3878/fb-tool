"""
Webhook Telegram — thay cho polling của Phase 1.

Bảo mật: Telegram gửi kèm header `X-Telegram-Bot-Api-Secret-Token`; nếu
TELEGRAM_WEBHOOK_SECRET được đặt mà header sai thì từ chối. Nếu không có
lớp này, bất kỳ ai biết URL đều có thể giả lệnh "ứng tuyển" cho khách hàng.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.base import utcnow
from app.models.campaign import Campaign
from app.models.enums import PostStatus
from app.models.post import DiscoveredPost
from app.models.user import User
from app.services.ai_service import AIService
from app.services.notification_service import NotificationService
from app.services.pipeline import build_comment, count_today_actions, queue_comment

router = APIRouter(prefix="/api/webhook", tags=["telegram"])


def _ai() -> AIService:
    settings = get_settings()
    return AIService(settings.openai_api_key, settings.openai_model)


async def _user_by_chat(db: AsyncSession, chat_id: str) -> User | None:
    result = await db.execute(select(User).where(User.telegram_chat_id == str(chat_id)))
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
    if user is None:
        return "❌ Mã liên kết không đúng hoặc đã được dùng."

    user.telegram_chat_id = str(chat_id)
    user.telegram_link_code = None
    await db.commit()
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
        post.status = PostStatus.SKIPPED.value
        post.ai_reason = "user_skipped_telegram"
        await db.commit()
        return "👍 Đã bỏ qua bài viết."

    if action in ("apply", "preview"):
        comment_text, script = await build_comment(db, campaign, post, _ai())
        if not comment_text:
            await db.rollback()
            return "⚠️ Không sinh được comment. Kiểm tra kịch bản hoặc OpenAI API key."

        if action == "preview":
            await db.commit()
            return f"📋 Bản nháp comment:\n\n{comment_text}"

        quota = int(campaign.max_comments_per_day or 20)
        used = await count_today_actions(db, campaign.id)
        if used >= quota:
            await db.rollback()
            return f"⛔ Đã đạt trần {quota} comment/ngày. Tạm dừng tới ngày mai."

        await queue_comment(db, campaign, post, comment_text, script)
        post.status = PostStatus.NOTIFIED.value
        post.notified_at = post.notified_at or utcnow()
        await db.commit()
        return f"🚀 Đã xếp hàng comment:\n\n{comment_text}"

    return "⚠️ Nút bấm không được hỗ trợ."


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    settings = get_settings()
    if settings.telegram_webhook_secret and (
        x_telegram_bot_api_secret_token != settings.telegram_webhook_secret
    ):
        raise HTTPException(status_code=403, detail="Secret token không hợp lệ")

    update = await request.json()
    notifier = NotificationService()

    callback = update.get("callback_query")
    if callback:
        chat_id = str(
            ((callback.get("message") or {}).get("chat") or {}).get("id", "")
        )
        reply = await _handle_callback(db, chat_id, callback.get("data") or "")
        await notifier.send_text(chat_id, reply)
        return {"ok": True, "handled": "callback_query"}

    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if text.startswith("/start"):
        await notifier.send_text(chat_id, await _handle_start(db, chat_id, text))
        return {"ok": True, "handled": "start"}

    if text.startswith("/status"):
        user = await _user_by_chat(db, chat_id)
        if user is None:
            await notifier.send_text(chat_id, "❌ Chat chưa liên kết tài khoản.")
        else:
            campaigns = await db.execute(
                select(Campaign).where(Campaign.user_id == user.id)
            )
            rows = list(campaigns.scalars().all())
            active = sum(1 for c in rows if c.is_active)
            await notifier.send_text(
                chat_id,
                f"📊 Tài khoản {user.email}\n"
                f"Chiến dịch: {len(rows)} (đang chạy: {active})",
            )
        return {"ok": True, "handled": "status"}

    return {"ok": True, "handled": "ignored"}
