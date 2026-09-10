"""
Shooter Worker — Module comment vào bài viết Facebook.
Kế thừa pattern từ ai-comment-bot/main.py post_comment.
"""
import asyncio
import random
from datetime import datetime
from typing import Optional

from loguru import logger

from browser_manager import BrowserManager
from constants import (
    COMMENT_BOX_SELECTORS,
    COMMENT_DELETE_CONFIRM_HEADINGS,
    COMMENT_DELETE_MENU_TEXTS,
    OWN_COMMENT_MENU_LABELS,
    WARMUP_DURATION_MIN_SEC,
    WARMUP_DURATION_MAX_SEC,
)
from dedup_store import DedupStore
from human_emulator import (
    human_mouse_jiggle,
    human_type,
    random_scroll,
    random_pause,
    warmup_session,
)
from models import AppConfig, CommentAction, CommentStatus, DiscoveredPost


def _pick_verify_phrase(comment_text: str) -> str:
    """Lấy lát cắt ~40-60 ký tự từ phần GIỮA comment thay vì 3 từ đầu.
    
    Hàm thuần, có thể test offline.
    """
    normalized = " ".join((comment_text or "").split())
    if len(normalized) <= 40:
        return normalized

    mid = len(normalized) // 2
    start = max(0, mid - 25)
    end = min(len(normalized), mid + 25)
    sub = normalized[start:end]

    # Cắt bớt từ dở dang ở đầu/cuối nếu có khoảng trắng
    words = sub.split()
    if len(words) > 2 and start > 0:
        phrase = " ".join(words[1:-1]) if end < len(normalized) else " ".join(words[1:])
    elif len(words) > 1 and end < len(normalized):
        phrase = " ".join(words[:-1])
    else:
        phrase = " ".join(words)

    return phrase if len(phrase) >= 10 else normalized


async def _composer_is_empty(comment_box) -> bool:
    """Kiểm tra xem ô nhập comment đã trống chưa.
    
    Nếu element bị detach (FB re-render sau khi gửi) -> coi như đã trống.
    """
    if comment_box is None:
        return True
    try:
        text = await comment_box.inner_text()
        if text is None:
            text = await comment_box.text_content()
        return not (text or "").strip()
    except Exception:
        return True


async def _text_present_outside(page, comment_box, phrase: str) -> bool:
    """Kiểm tra phrase có xuất hiện trong body nhưng NGOÀI ô comment_box hay không.
    
    Dùng TreeWalker duyệt các text node, loại trừ mọi node thuộc subtree của comment_box.
    Chuẩn hoá khoảng trắng cả hai phía.
    """
    if not phrase:
        return False
    try:
        js_code = """
        ([composer, searchPhrase]) => {
            if (!searchPhrase) return false;
            const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const target = clean(searchPhrase);
            if (!target) return false;

            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: (node) => {
                        if (composer && composer.contains && composer.contains(node)) {
                            return NodeFilter.FILTER_REJECT;
                        }
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );

            let node;
            while ((node = walker.nextNode())) {
                const nodeText = clean(node.nodeValue);
                if (nodeText && nodeText.includes(target)) {
                    return true;
                }
            }
            return false;
        }
        """
        return await page.evaluate(js_code, [comment_box, phrase])
    except Exception as e:
        logger.debug(f"Lỗi kiểm tra text ngoài composer: {e}")
        return False


class ShooterWorker:
    """Module comment vào bài viết Facebook."""

    def __init__(self, browser_mgr: BrowserManager, config: AppConfig):
        self.browser_mgr = browser_mgr
        self.config = config
        self._context = None
        self._page = None

    async def _ensure_context(self):
        """Đảm bảo browser context đã sẵn sàng."""
        shooter_cfg = self.config.accounts.get("shooter")
        if not shooter_cfg:
            raise ValueError("Chưa cấu hình tài khoản shooter trong config.accounts")

        if self._context is None:
            self._context = await self.browser_mgr.create_stealth_context(
                profile_dir=shooter_cfg.profile_dir,
                proxy=shooter_cfg.proxy,
                headless=None,  # theo cấu hình browser.headless
                cdp_endpoint=getattr(shooter_cfg, "cdp_endpoint", None),
            )

    async def _get_page(self):
        """Lấy page, tái sử dụng nếu có."""
        await self._ensure_context()
        if self._page is None or self._page.is_closed():
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                # Stealth + vân tay đã gắn ở cấp context; page mới tự kế thừa.
                self._page = await self._context.new_page()
        return self._page

    async def post_comment(
        self,
        post_url: str,
        comment_text: str,
        dedup_store: DedupStore = None,
        post_hash: str = "",
        delete_after: bool = False,
    ) -> CommentStatus:
        """Comment vào bài viết trên Facebook.
        
        Luồng xử lý:
        1. Kiểm tra rate limit theo số LƯỢT thao tác
        2. Ghi nhận attempt_id (status=in_progress)
        3. Warmup: Lướt newsfeed 30-60s
        4. Navigate đến bài viết
        5. Tìm ô comment
        6. Gõ comment mô phỏng người thật
        7. Gửi và verify 2 chiều (empty composer + text outside)
        8. finish_attempt cập nhật kết quả
        """
        page = await self._get_page()

        # 1. Kiểm tra rate limit (theo số LƯỢT thao tác)
        if dedup_store:
            today_count = dedup_store.get_today_action_count()
            max_daily = self.config.comment.max_comments_per_day
            if today_count >= max_daily:
                logger.warning(
                    f"⛔ Rate limit: Đã thực hiện {today_count}/{max_daily} lượt hôm nay. Dừng lại."
                )
                return CommentStatus.FAILED

        # 2. Ghi nhận attempt_id trước khi warmup (warmup đã là hành vi thật)
        attempt_id = None
        if dedup_store:
            attempt_id = dedup_store.record_attempt(post_hash, comment_text)

        # 3. Warmup: Lướt newsfeed
        logger.info("🔥 Warmup trước khi comment...")
        await warmup_session(
            page,
            duration_min=WARMUP_DURATION_MIN_SEC,
            duration_max=WARMUP_DURATION_MAX_SEC,
        )

        try:
            # 4. Navigate đến bài viết
            logger.info(f"📝 Navigate đến bài viết: {post_url}")
            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Kiểm tra checkpoint
            if await BrowserManager.detect_checkpoint_page(page):
                logger.error("🚨 Phát hiện checkpoint khi mở bài viết")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, "checkpoint")
                return CommentStatus.FAILED

            # Kiểm tra bài viết tồn tại
            page_content = await page.text_content("body")
            if page_content and any(
                text in page_content.lower()
                for text in ["không tìm thấy", "content isn't available", "nội dung không khả dụng"]
            ):
                logger.warning("Bài viết không còn tồn tại hoặc bị xóa")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, "post_deleted")
                return CommentStatus.FAILED

            # 5. Cuộn xuống vùng comment
            await random_scroll(page)
            await random_pause(1, 2)

            # 6. Tìm ô comment
            comment_box = None
            for selector in COMMENT_BOX_SELECTORS:
                try:
                    comment_box = await page.wait_for_selector(selector, timeout=5000)
                    if comment_box:
                        logger.info(f"Tìm thấy ô comment bằng selector: {selector}")
                        break
                except Exception:
                    continue

            if not comment_box:
                logger.error("❌ Không tìm thấy ô comment")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, "comment_box_not_found")
                return CommentStatus.FAILED

            # 7. Mouse jiggle quanh ô comment
            bbox = await comment_box.bounding_box()
            if bbox:
                await human_mouse_jiggle(
                    page,
                    int(bbox["x"] + bbox["width"] / 2),
                    int(bbox["y"] + bbox["height"] / 2),
                    moves=3,
                )

            # 8. Click vào ô comment
            await comment_box.click()
            await random_pause(0.5, 2.0)

            # 9. Gõ comment mô phỏng người thật
            typing_config = {
                "typing_delay_min_ms": self.config.comment.typing_delay_min_ms,
                "typing_delay_max_ms": self.config.comment.typing_delay_max_ms,
                "typo_probability": self.config.comment.typo_probability,
            }
            await human_type(page, comment_text, typing_config)
            await random_pause(0.5, 2.0)

            # 10. Gửi comment (Enter)
            await page.keyboard.press("Enter")
            logger.info("📤 Đã nhấn Enter gửi comment")

            # 11. Đợi và verify 2 chiều
            await page.wait_for_timeout(random.randint(2000, 4000))

            status = await self._verify_comment(page, comment_box, comment_text)

            if status == CommentStatus.SUCCESS:
                logger.info("✅ Comment thành công!")
                if delete_after:
                    await random_pause(2, 4)
                    await self.delete_comment(page, comment_text)
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.SUCCESS)
                    dedup_store.increment_comments_sent()
            elif status == CommentStatus.SHADOWBANNED:
                logger.warning("⚠️ Nghi ngờ bị shadowban — comment không hiển thị")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.SHADOWBANNED, "shadowbanned")
            else:
                logger.warning("⚠️ Không thể xác nhận comment hoặc enter không gửi được")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, "verify_failed")

            return status

        except Exception as e:
            logger.error(f"❌ Lỗi comment: {e}")
            if dedup_store and attempt_id is not None:
                dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, str(e))
            return CommentStatus.FAILED

    async def _verify_comment(self, page, comment_box, comment_text: str) -> CommentStatus:
        """Kiểm tra comment đã gửi thành công chưa bằng 2 tín hiệu.
        
        | Ô nhập đã trống? | Text xuất hiện NGOÀI ô nhập? | Kết luận |
        |---|---|---|
        | ✅ trống | ✅ có | SUCCESS |
        | ✅ trống | ❌ không (sau 1 lần chờ lại) | SHADOWBANNED |
        | ❌ còn text | — | FAILED (enter_did_not_submit) |
        | lỗi khi kiểm tra | — | FAILED (verify_error) |
        """
        try:
            # 1. Kiểm tra ô nhập
            is_empty = await _composer_is_empty(comment_box)
            if not is_empty:
                logger.warning("❌ Ô nhập comment vẫn còn text sau Enter (enter_did_not_submit)")
                return CommentStatus.FAILED

            phrase = _pick_verify_phrase(comment_text)

            # 2. Kiểm tra text xuất hiện ngoài ô nhập
            found = await _text_present_outside(page, comment_box, phrase)
            if found:
                return CommentStatus.SUCCESS

            # Chờ thêm 1 lần (FB re-render DOM)
            await page.wait_for_timeout(3000)
            found = await _text_present_outside(page, comment_box, phrase)
            if found:
                return CommentStatus.SUCCESS

            logger.warning("⚠️ Text không hiển thị ngoài ô nhập sau khi gửi (nghi ngờ shadowban)")
            return CommentStatus.SHADOWBANNED

        except Exception as e:
            logger.debug(f"Lỗi verify comment: {e}")
            return CommentStatus.FAILED

    async def delete_comment(self, page, comment_text: str) -> bool:
        """Xoá bình luận của CHÍNH mình vừa đăng, dựa vào nội dung.

        Luồng (đã kiểm chứng trên DOM group thật 2026-09):
          hover dòng comment → nút "Chỉnh sửa hoặc xóa bình luận này"
          → menu "Xóa" → hộp thoại "Xóa bình luận?" → nút "Xóa".

        Returns:
            True nếu sau khi reload không còn thấy comment, False nếu không xoá được.
        """
        key = " ".join((comment_text or "").split())[:40]
        if not key:
            return False
        try:
            line = page.get_by_text(key, exact=False).first
            await line.scroll_into_view_if_needed(timeout=6000)
            await random_pause(0.4, 1.0)
            bbox = await line.bounding_box()
            if bbox:
                await page.mouse.move(bbox["x"] + bbox["width"] / 2, bbox["y"])
                await random_pause(0.8, 1.6)

            menu_btn = None
            for label in OWN_COMMENT_MENU_LABELS:
                loc = page.get_by_label(label).first
                if await loc.count() > 0:
                    menu_btn = loc
                    break
            if menu_btn is None:
                logger.error("Không thấy nút menu của comment mình (để xoá)")
                return False
            await menu_btn.click(timeout=6000, force=True)
            await random_pause(0.8, 1.5)

            # Menu: chọn "Xóa" (KHÔNG phải "Chỉnh sửa")
            menu = page.locator('[role="menu"]').last
            clicked = False
            for name in COMMENT_DELETE_MENU_TEXTS:
                try:
                    await menu.get_by_text(name, exact=True).first.click(timeout=2500)
                    clicked = True
                    break
                except Exception:
                    continue
            if not clicked:
                logger.error("Không thấy mục 'Xóa' trong menu comment")
                return False
            await random_pause(0.8, 1.6)

            # Hộp thoại xác nhận — chỉ nút trong dialog có heading "Xóa bình luận"
            for dlg in await page.locator('[role="dialog"]').all():
                try:
                    txt = await dlg.inner_text()
                except Exception:
                    continue
                if not any(h in txt for h in COMMENT_DELETE_CONFIRM_HEADINGS):
                    continue
                for name in COMMENT_DELETE_MENU_TEXTS:
                    try:
                        await dlg.get_by_role("button", name=name).first.click(timeout=2500)
                        break
                    except Exception:
                        continue
                break
            await random_pause(2.0, 3.5)

            still = await page.get_by_text(key, exact=False).count()
            if still == 0:
                logger.info("🗑️  Đã xoá comment")
                return True
            logger.warning(f"Comment có thể chưa xoá (còn {still} node) — kiểm tra lại")
            return False
        except Exception as e:
            logger.error(f"Lỗi xoá comment: {e}")
            return False

    async def schedule_comment(
        self,
        post: DiscoveredPost,
        comment_text: str,
        dedup_store: DedupStore,
    ):
        """Đặt lịch comment với delay ngẫu nhiên.
        
        Delay nằm trong [delay_min_seconds, delay_max_seconds] từ config.
        """
        delay = random.uniform(
            self.config.comment.delay_min_seconds,
            self.config.comment.delay_max_seconds,
        )
        logger.info(f"⏰ Đặt lịch comment sau {delay:.0f}s cho bài: {post.post_url}")

        await asyncio.sleep(delay)

        result = await self.post_comment(
            post_url=post.post_url,
            comment_text=comment_text,
            dedup_store=dedup_store,
            post_hash=post.content_hash,
        )

        if result == CommentStatus.SUCCESS:
            dedup_store.mark_commented(post, comment_text)

        return result

