"""
Notification Hub — gửi Telegram cho từng user (multi-tenant).

Phase 1 dùng 1 bot cho 1 khách. Từ Phase 2 hệ thống dùng CHUNG một bot,
phân biệt khách bằng `users.telegram_chat_id`, và nhận nút bấm qua webhook
thay vì polling (xem routers/telegram_webhook.py). Riêng chế độ desktop không
có URL public nên nhận qua long-polling (workers/telegram_poller.py).

Lớp này gọi HTTP API Telegram trực tiếp bằng httpx — không kéo theo
python-telegram-bot vào tiến trình API để giữ ảnh API nhẹ.
"""
import re

import httpx

from app.config import get_settings

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
MARKDOWN_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!"


def escape_md(text: str) -> str:
    """Escape MarkdownV2 — backslash phải được xử lý ĐẦU TIÊN."""
    if text is None:
        return ""
    out = str(text).replace("\\", "\\\\")
    for char in MARKDOWN_V2_SPECIALS:
        out = out.replace(char, f"\\{char}")
    return out


def build_post_message(post, campaign_name: str = "") -> str:
    """Soạn nội dung thông báo bài viết phù hợp (MarkdownV2)."""
    score = float(post.ai_relevance_score or 0)
    stars = "⭐" * max(1, min(5, int(round(score * 5))))
    preview = (post.content_text or "")[:300]
    if len(post.content_text or "") > 300:
        preview += "..."

    extracted = post.ai_extracted or {}
    extra_lines = []
    for key, label in (
        ("genre", "📖 Thể loại"),
        ("budget", "💰 Ngân sách"),
        ("deadline", "⏰ Deadline"),
    ):
        if extracted.get(key):
            extra_lines.append(f"{label}: {escape_md(extracted[key])}")

    parts = [
        "🎯 *BÀI MỚI PHÙ HỢP\\!*",
        "",
        f"📁 Chiến dịch: {escape_md(campaign_name)}",
        f"👤 Người đăng: {escape_md(post.author_name)}",
        f"💬 Đã có {post.existing_comment_count} comment",
        "",
        f"📝 Nội dung:\n_{escape_md(preview)}_",
    ]
    if extra_lines:
        parts += ["", *extra_lines]
    parts += [
        "",
        f"🤖 AI đánh giá: {stars} {escape_md(f'{score:.2f}')}/1\\.0",
        f"📊 Lý do: {escape_md(post.ai_reason)}",
    ]
    return "\n".join(parts)


def build_post_keyboard(post_id: str, post_url: str = "") -> dict:
    """Inline Keyboard 4 nút của luồng Semi-Auto."""
    rows = [
        [
            {"text": "🚀 Ứng tuyển (AI Comment)", "callback_data": f"apply:{post_id}"},
            {"text": "📋 Xem trước comment", "callback_data": f"preview:{post_id}"},
        ],
        [{"text": "❌ Bỏ qua", "callback_data": f"skip:{post_id}"}],
    ]
    if post_url:
        rows[1].append({"text": "🔗 Mở bài viết", "url": post_url})
    return {"inline_keyboard": rows}


def strip_markdown(text: str) -> str:
    """Bản plain-text để rơi về khi MarkdownV2 bị Telegram từ chối."""
    return re.sub(r"\\(.)", r"\1", text).replace("*", "").replace("_", "")


class NotificationService:
    """Gửi tin nhắn Telegram. Không có token thì im lặng bỏ qua (dev/test)."""

    def __init__(self, bot_token: str | None = None, client: httpx.AsyncClient | None = None):
        self.bot_token = bot_token if bot_token is not None else get_settings().telegram_bot_token
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token)

    async def _call(self, method: str, payload: dict, timeout: float = 15) -> dict | None:
        if not self.enabled:
            return None
        url = TELEGRAM_API.format(token=self.bot_token, method=method)
        client = self._client or httpx.AsyncClient(timeout=timeout)
        try:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                return {"ok": False, "status": response.status_code, "body": response.text}
            return response.json()
        except Exception as exc:  # mạng lỗi không được làm sập worker
            return {"ok": False, "error": "telegram_transport_error"}
        finally:
            if self._client is None:
                await client.aclose()

    async def send_text(self, chat_id: str, text: str, markdown: bool = False) -> dict | None:
        if not chat_id:
            return None
        payload = {"chat_id": chat_id, "text": text}
        if markdown:
            payload["parse_mode"] = "MarkdownV2"
        result = await self._call("sendMessage", payload)
        if markdown and result is not None and result.get("ok") is False:
            # MarkdownV2 rất dễ 400 — luôn có đường lui bằng plain text.
            return await self._call(
                "sendMessage", {"chat_id": chat_id, "text": strip_markdown(text)}
            )
        return result

    async def get_updates(self, offset: int, timeout: int) -> dict | None:
        """Long-polling `getUpdates` cho chế độ desktop (không có URL public cho webhook).

        Telegram giữ kết nối tối đa `timeout` giây nên client HTTP phải chờ lâu hơn thế.
        """
        return await self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": timeout,
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=timeout + 10,
        )

    async def send_post_notification(self, chat_id: str, post, campaign_name: str = "") -> dict | None:
        if not chat_id:
            return None
        payload = {
            "chat_id": chat_id,
            "text": build_post_message(post, campaign_name),
            "parse_mode": "MarkdownV2",
            "reply_markup": build_post_keyboard(post.id, post.post_url or ""),
        }
        result = await self._call("sendMessage", payload)
        if result is not None and result.get("ok") is False:
            payload.pop("parse_mode")
            payload["text"] = strip_markdown(payload["text"])
            result = await self._call("sendMessage", payload)
        return result

    async def send_result_notification(
        self, chat_id: str, post, success: bool, comment_text: str = "", error: str = ""
    ) -> dict | None:
        head = "✅ ĐÃ COMMENT THÀNH CÔNG!" if success else "❌ COMMENT THẤT BẠI"
        body = f"👤 Bài của: {post.author_name}\n"
        body += f"💬 Comment:\n{comment_text}" if success else f"⚠️ Lỗi: {error}"
        return await self.send_text(chat_id, f"{head}\n\n{body}")


async def build_clone_notifier(db):
    """Trả về async callable `(user_id, message)` bắn Telegram cho chủ của clone.

    Dùng chung cho mọi worker cần đưa cảnh báo vòng đời clone (checkpoint,
    tự-nghỉ khi chạy "mode treo") qua `AccountManager(db, notifier=...)`.
    Chủ chưa liên kết Telegram thì im lặng bỏ qua.
    """
    from app.models.user import User

    from app.services.outbox_service import queue_text

    async def send(user_id: str, message: str) -> None:
        user = await db.get(User, user_id)
        if user and user.telegram_chat_id:
            await queue_text(db, user.telegram_chat_id, message)

    return send
