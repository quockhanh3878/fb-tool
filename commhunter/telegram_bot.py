"""
Telegram Bot — Thông báo bài viết mới + Semi-Auto Inline Keyboard.
Kế thừa pattern từ fbn/notifications.py.
"""
import asyncio
import json
from typing import Optional

from loguru import logger

from models import AppConfig, DiscoveredPost, TelegramConfig


class TelegramBot:
    """Telegram Bot cho thông báo Semi-Auto."""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self._application = None
        self._bot = None
        self._callbacks = {}  # {callback_data: handler}

    def _get_bot(self):
        """Lazy init bot singleton."""
        if self._bot is None:
            from telegram import Bot
            self._bot = Bot(token=self.config.bot_token)
        return self._bot

    def _get_application(self):
        """Lazy init telegram application."""
        if self._application is None:
            from telegram.ext import Application
            self._application = (
                Application.builder()
                .token(self.config.bot_token)
                .build()
            )
        return self._application

    async def send_post_notification(
        self,
        post: DiscoveredPost,
        ai_result: dict,
    ) -> Optional[int]:
        """Gửi tin nhắn thông báo bài viết mới với Inline Keyboard.
        
        Args:
            post: Bài viết đã phát hiện.
            ai_result: Kết quả chấm điểm AI (score, reason, extracted).
        
        Returns:
            Message ID nếu gửi thành công, None nếu lỗi.
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        bot = self._get_bot()

        # Format nội dung tin nhắn
        score = ai_result.get("relevance_score", 0)
        reason = ai_result.get("reason", "N/A")
        extracted = ai_result.get("extracted", {})

        # Số sao dựa trên score
        stars = "⭐" * max(1, int(score * 5))

        content_preview = post.content_text[:300]
        if len(post.content_text) > 300:
            content_preview += "..."

        extracted_info = ""
        if extracted:
            parts = []
            if extracted.get("genre"):
                parts.append(f"📖 Thể loại: {extracted['genre']}")
            if extracted.get("budget"):
                parts.append(f"💰 Budget: {extracted['budget']}")
            if extracted.get("deadline"):
                parts.append(f"⏰ Deadline: {extracted['deadline']}")
            if parts:
                extracted_info = "\n".join(parts) + "\n"

        message = (
            f"🎯 *BÀI MỚI PHÙ HỢP!*\n\n"
            f"📌 Nhóm: {_escape_md(post.group_name)}\n"
            f"👤 Người đăng: {_escape_md(post.author_name)}\n"
            f"💬 Đã có {post.existing_comment_count} comment\n\n"
            f"📝 Nội dung:\n_{_escape_md(content_preview)}_\n\n"
            f"{extracted_info}"
            f"🤖 AI đánh giá: {stars} {score:.1f}/1\\.0\n"
            f"📊 Lý do: {_escape_md(reason)}\n"
        )

        # Inline Keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🚀 Ứng tuyển (AI Comment)",
                    callback_data=f"apply:{post.content_hash}",
                ),
                InlineKeyboardButton(
                    "📋 Xem trước comment",
                    callback_data=f"preview:{post.content_hash}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "❌ Bỏ qua",
                    callback_data=f"skip:{post.content_hash}",
                ),
                InlineKeyboardButton(
                    "🔗 Mở bài viết",
                    url=post.post_url if post.post_url else "https://facebook.com",
                ),
            ],
        ])

        try:
            msg = await bot.send_message(
                chat_id=self.config.chat_id,
                text=message,
                parse_mode="MarkdownV2",
                reply_markup=keyboard,
            )
            logger.info(f"Đã gửi thông báo Telegram cho bài: {post.author_name}")
            return msg.message_id

        except Exception as e:
            logger.error(f"Lỗi gửi Telegram: {e}")
            # Retry không dùng markdown
            try:
                plain_message = (
                    f"🎯 BÀI MỚI PHÙ HỢP!\n\n"
                    f"📌 Nhóm: {post.group_name}\n"
                    f"👤 Người đăng: {post.author_name}\n"
                    f"💬 Đã có {post.existing_comment_count} comment\n\n"
                    f"📝 Nội dung:\n{content_preview}\n\n"
                    f"🤖 AI: {score:.1f}/1.0 — {reason}\n"
                )
                msg = await bot.send_message(
                    chat_id=self.config.chat_id,
                    text=plain_message,
                    reply_markup=keyboard,
                )
                return msg.message_id
            except Exception as e2:
                logger.error(f"Lỗi gửi Telegram (retry): {e2}")
                return None

    async def send_result_notification(
        self,
        post: DiscoveredPost,
        success: bool,
        comment_text: str = "",
        error: str = "",
    ):
        """Báo kết quả comment.
        
        Args:
            post: Bài viết đã comment.
            success: True nếu thành công.
            comment_text: Nội dung comment.
            error: Thông báo lỗi nếu thất bại.
        """
        bot = self._get_bot()

        if success:
            message = (
                f"✅ *ĐÃ COMMENT THÀNH CÔNG\!*\n\n"
                f"📌 Nhóm: {_escape_md(post.group_name)}\n"
                f"👤 Bài của: {_escape_md(post.author_name)}\n\n"
                f"💬 Comment:\n_{_escape_md(comment_text)}_"
            )
            plain = (
                f"✅ ĐÃ COMMENT THÀNH CÔNG!\n\n"
                f"📌 Nhóm: {post.group_name}\n"
                f"👤 Bài của: {post.author_name}\n\n"
                f"💬 Comment:\n{comment_text}"
            )
        else:
            message = (
                f"❌ *COMMENT THẤT BẠI*\n\n"
                f"📌 Nhóm: {_escape_md(post.group_name)}\n"
                f"👤 Bài của: {_escape_md(post.author_name)}\n"
                f"⚠️ Lỗi: {_escape_md(error)}"
            )
            plain = (
                f"❌ COMMENT THẤT BẠI\n\n"
                f"📌 Nhóm: {post.group_name}\n"
                f"👤 Bài của: {post.author_name}\n"
                f"⚠️ Lỗi: {error}"
            )

        try:
            await bot.send_message(
                chat_id=self.config.chat_id,
                text=message,
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            # MarkdownV2 rất dễ 400 nếu sót ký tự đặc biệt — luôn có đường lui
            # bằng plain text, nếu không người dùng sẽ mất hẳn thông báo kết quả.
            logger.error(f"Lỗi gửi kết quả Telegram: {e}")
            try:
                await bot.send_message(chat_id=self.config.chat_id, text=plain)
            except Exception as e2:
                logger.error(f"Lỗi gửi kết quả Telegram (retry plain): {e2}")

    async def send_text(self, text: str, markdown: bool = False):
        """Gửi 1 tin nhắn text thuần (dùng cho Preview comment, cảnh báo...)."""
        bot = self._get_bot()
        try:
            await bot.send_message(
                chat_id=self.config.chat_id,
                text=text,
                parse_mode="MarkdownV2" if markdown else None,
            )
            return True
        except Exception as e:
            logger.error(f"Lỗi gửi text Telegram: {e}")
            return False

    async def send_status_report(self, stats: dict):
        """Gửi báo cáo trạng thái hệ thống."""
        bot = self._get_bot()

        message = (
            f"📊 *BÁO CÁO TRẠNG THÁI*\n\n"
            f"📡 Bài quét hôm nay: {stats.get('today_scanned', 0)}\n"
            f"🎯 Bài phù hợp: {stats.get('today_matched', 0)}\n"
            f"💬 Comment đã gửi: {stats.get('today_comments', 0)}\n\n"
            f"📦 Tổng bài mới: {stats.get('new', 0)}\n"
            f"📨 Đã thông báo: {stats.get('notified', 0)}\n"
            f"✅ Đã comment: {stats.get('commented', 0)}\n"
            f"❌ Đã bỏ qua: {stats.get('skipped', 0)}\n"
        )

        try:
            await bot.send_message(
                chat_id=self.config.chat_id,
                text=message,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Lỗi gửi báo cáo Telegram: {e}")

    async def _handle_callback(self, update, on_apply=None, on_skip=None, on_preview=None):
        """Xử lý sự kiện callback từ Inline Keyboard với validation chat_id và payload an toàn."""
        query = update.callback_query
        if not query:
            return

        effective_chat = update.effective_chat
        if effective_chat and str(effective_chat.id) != str(self.config.chat_id):
            logger.warning(
                f"Từ chối callback từ chat không xác thực: {effective_chat.id} (mong đợi {self.config.chat_id})"
            )
            try:
                await query.answer("Bạn không có quyền thực hiện thao tác này.", show_alert=True)
            except Exception as e:
                logger.debug(f"handle_callback unauthorized answer: {e}")
            return

        await query.answer()

        data = query.data or ""
        try:
            action, post_hash = data.split(":", 1)
        except ValueError:
            logger.warning(f"Malformed callback data: {data}")
            return

        if action == "apply" and on_apply:
            await query.edit_message_text(
                text=(query.message.text or "") + "\n\n⏳ Đang xử lý ứng tuyển..."
            )
            await on_apply(post_hash)

        elif action == "skip" and on_skip:
            await query.edit_message_text(
                text=(query.message.text or "") + "\n\n❌ Đã bỏ qua."
            )
            await on_skip(post_hash)

        elif action == "preview" and on_preview:
            await on_preview(post_hash)

        else:
            logger.warning(f"Unknown callback: {data}")

    async def start_polling(self, on_apply=None, on_skip=None, on_preview=None):
        """Khởi động Telegram bot polling để nhận callback từ Inline Keyboard.
        
        Args:
            on_apply: Async callback khi user bấm "Ứng tuyển". Nhận (post_hash).
            on_skip: Async callback khi user bấm "Bỏ qua". Nhận (post_hash).
            on_preview: Async callback khi user bấm "Xem trước". Nhận (post_hash).
        """
        from telegram.ext import Application, CallbackQueryHandler

        app = self._get_application()

        async def handle_callback(update, context):
            await self._handle_callback(update, on_apply=on_apply, on_skip=on_skip, on_preview=on_preview)

        app.add_handler(CallbackQueryHandler(handle_callback))

        logger.info("Telegram bot bắt đầu polling...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

    async def stop_polling(self):
        """Dừng polling và giải phóng tài nguyên (phục vụ graceful shutdown)."""
        app = self._application
        if app is None:
            return
        try:
            if app.updater is not None and app.updater.running:
                await app.updater.stop()
        except Exception as e:
            logger.debug(f"stop_polling/updater: {e}")
        try:
            if app.running:
                await app.stop()
        except Exception as e:
            logger.debug(f"stop_polling/app: {e}")
        try:
            await app.shutdown()
        except Exception as e:
            logger.debug(f"stop_polling/shutdown: {e}")
        self._application = None
        logger.info("Telegram bot đã dừng")

    async def close(self):
        """Dừng bot, giải phóng application và session bot."""
        await self.stop_polling()
        if self._bot is not None:
            try:
                await self._bot.shutdown()
            except Exception as e:
                logger.debug(f"close/bot: {e}")
            self._bot = None


def _escape_md(text: str) -> str:
    """Escape ký tự đặc biệt cho MarkdownV2."""
    if text is None:
        return ""
    # Backslash phải escape ĐẦU TIÊN, nếu không sẽ escape chồng lên các
    # ký tự vừa được thêm ở vòng lặp bên dưới.
    text = str(text).replace("\\", "\\\\")
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f"\\{char}")
    return text
