"""
Shooter Worker — Module comment vào bài viết Facebook.
Kế thừa pattern từ ai-comment-bot/main.py post_comment.
"""
import asyncio
import random
import re
import time
from datetime import datetime
from typing import Optional

from loguru import logger

from browser_manager import BrowserManager
from constants import (
    COMMENT_BOX_SELECTORS,
    COMMENT_DELETE_CONFIRM_HEADINGS,
    COMMENT_DELETE_MENU_TEXTS,
    COMPOSER_SUBMIT_SELECTORS,
    COMPOSER_TEXTBOX_SELECTORS,
    COMPOSER_TRIGGER_SELECTORS,
    COMPOSER_VERIFY_SCROLL_PASSES,
    EXTRACT_LATEST_POST_JS,
    MARK_TIMESTAMP_ANCHOR_JS,
    MARK_TIMESTAMP_ANCHOR_SELECTOR,
    CURRENT_ACCOUNT_NAME_RE,
    OWN_COMMENT_MENU_LABELS,
    OWN_POST_DELETE_CONFIRM_BUTTON_TEXTS,
    OWN_POST_DELETE_CONFIRM_HINTS,
    OWN_POST_DELETE_MENU_TEXTS,
    OWN_POST_MENU_ARIA_NAMED,
    OWN_POST_MENU_SELECTORS,
    PERMALINK_URL_RE,
    POST_GONE_MARKERS,
    POST_SUBMIT_CONFIRM_TIMEOUT_MS,
    POST_SUCCESS_PHRASES,
    SCROLL_WAIT_MAX_MS,
    SCROLL_WAIT_MIN_MS,
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
from models import (
    AppConfig,
    CommentAction,
    CommentStatus,
    DiscoveredPost,
    PublishResult,
    PublishStatus,
)


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
                    f"Rate limit: Đã thực hiện {today_count}/{max_daily} lượt hôm nay. Dừng lại."
                )
                return CommentStatus.FAILED

        # 2. Ghi nhận attempt_id trước khi warmup (warmup đã là hành vi thật)
        attempt_id = None
        if dedup_store:
            attempt_id = dedup_store.record_attempt(post_hash, comment_text)

        # 3. Warmup: Lướt newsfeed
        logger.info("Warmup trước khi comment...")
        await warmup_session(
            page,
            duration_min=WARMUP_DURATION_MIN_SEC,
            duration_max=WARMUP_DURATION_MAX_SEC,
        )

        try:
            # 4. Navigate đến bài viết
            logger.info(f"Navigate đến bài viết: {post_url}")
            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            # Kiểm tra checkpoint
            if await BrowserManager.detect_checkpoint_page(page):
                logger.error("Phát hiện checkpoint khi mở bài viết")
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
                logger.error("Không tìm thấy ô comment")
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
            logger.info("Đã nhấn Enter gửi comment")

            # 11. Đợi và verify 2 chiều
            await page.wait_for_timeout(random.randint(2000, 4000))

            status = await self._verify_comment(page, comment_box, comment_text)

            if status == CommentStatus.SUCCESS:
                logger.info("Comment thành công!")
                if delete_after:
                    await random_pause(2, 4)
                    await self.delete_comment(page, comment_text)
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.SUCCESS)
                    dedup_store.increment_comments_sent()
            elif status == CommentStatus.SHADOWBANNED:
                logger.warning("Nghi ngờ bị shadowban — comment không hiển thị")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.SHADOWBANNED, "shadowbanned")
            else:
                logger.warning("Không thể xác nhận comment hoặc enter không gửi được")
                if dedup_store and attempt_id is not None:
                    dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, "verify_failed")

            return status

        except Exception as e:
            logger.error(f"Lỗi comment: {e}")
            if dedup_store and attempt_id is not None:
                dedup_store.finish_attempt(attempt_id, CommentStatus.FAILED, str(e))
            return CommentStatus.FAILED

    async def publish_post(
        self,
        group_url: str,
        content: str,
        media_paths: Optional[list] = None,
    ) -> PublishResult:
        """Đăng một bài viết (seeding) vào group Facebook.

        Bám cùng trình tự phòng thủ của post_comment: warmup -> goto ->
        detect checkpoint -> tìm composer -> jiggle -> click -> human_type ->
        submit -> verify -> tìm lại permalink.

        Fail an toàn: không tìm thấy composer / nút Đăng / checkpoint -> trả
        PublishResult(FAILED), KHÔNG thử mù, KHÔNG bịa link.
        """
        if not (content or "").strip():
            return PublishResult(PublishStatus.FAILED, error="empty_content")

        page = await self._get_page()

        logger.info("Warmup trước khi đăng bài...")
        await warmup_session(
            page,
            duration_min=WARMUP_DURATION_MIN_SEC,
            duration_max=WARMUP_DURATION_MAX_SEC,
        )

        try:
            logger.info(f"Navigate đến group để đăng bài: {group_url}")
            await page.goto(group_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            if await BrowserManager.detect_checkpoint_page(page):
                logger.error("Phát hiện checkpoint khi mở group để đăng bài")
                return PublishResult(PublishStatus.FAILED, error="checkpoint")

            # Mở composer
            trigger = await self._first_selector(page, COMPOSER_TRIGGER_SELECTORS, timeout=6000)
            if trigger is None:
                logger.error("Không tìm thấy nút mở ô soạn bài — dừng, không thử mù")
                return PublishResult(PublishStatus.FAILED, error="composer_trigger_not_found")
            bbox = await trigger.bounding_box()
            if bbox:
                await human_mouse_jiggle(
                    page,
                    int(bbox["x"] + bbox["width"] / 2),
                    int(bbox["y"] + bbox["height"] / 2),
                    moves=3,
                )
            await trigger.click()
            await random_pause(1.0, 2.5)

            # Ô nhập nội dung
            textbox = await self._first_selector(page, COMPOSER_TEXTBOX_SELECTORS, timeout=8000)
            if textbox is None:
                logger.error("Không tìm thấy ô nhập nội dung bài viết")
                return PublishResult(PublishStatus.FAILED, error="composer_textbox_not_found")
            await textbox.click()
            await random_pause(0.5, 1.5)

            typing_config = {
                "typing_delay_min_ms": self.config.comment.typing_delay_min_ms,
                "typing_delay_max_ms": self.config.comment.typing_delay_max_ms,
                "typo_probability": self.config.comment.typo_probability,
            }
            await human_type(page, content, typing_config)
            await random_pause(1.0, 2.5)

            if media_paths:
                logger.warning(
                    "publish_post: đính kèm media chưa được hỗ trợ, bỏ qua %d file",
                    len(media_paths),
                )

            # Bấm Đăng
            submit = await self._first_selector(page, COMPOSER_SUBMIT_SELECTORS, timeout=6000)
            if submit is None:
                logger.error("Không tìm thấy nút Đăng")
                return PublishResult(PublishStatus.FAILED, error="composer_submit_not_found")
            await submit.click()
            await page.wait_for_timeout(random.randint(3000, 6000))

            if not await self._post_submitted_ok(page):
                logger.warning("Không xác nhận được bài đã lên")
                return PublishResult(PublishStatus.FAILED, error="submit_not_confirmed")

            # Tìm lại permalink của bài vừa đăng
            post_url = await self._find_published_permalink(page, group_url, content)
            if post_url:
                logger.info(f"Đăng bài thành công, permalink: {post_url}")
                return PublishResult(PublishStatus.PUBLISHED, post_url=post_url)

            logger.warning("Đăng bài thành công nhưng không bóc được permalink")
            return PublishResult(PublishStatus.PUBLISHED_NO_URL)

        except Exception as e:
            logger.error(f"Lỗi đăng bài: {e}")
            return PublishResult(PublishStatus.FAILED, error=str(e))

    async def _first_selector(self, page, selectors, timeout: int = 5000):
        """Trả về element khớp selector đầu tiên, hoặc None nếu không selector nào khớp."""
        for selector in selectors:
            try:
                el = await page.wait_for_selector(selector, timeout=timeout)
                if el:
                    logger.info(f"Khớp selector: {selector}")
                    return el
            except Exception:
                continue
        return None

    async def _composer_textbox_visible(self, page) -> bool:
        """Ô nhập của hộp thoại soạn bài còn hiển thị không?"""
        for selector in COMPOSER_TEXTBOX_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el and await el.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _post_submitted_ok(self, page) -> bool:
        """Xác nhận bài đã lên: thấy cụm từ thành công, hoặc ô soạn bài đã đóng.

        KHÔNG đếm mọi [role="dialog"] — FB luôn giữ sẵn dialog thông báo và
        dialog bài viết ẩn trong DOM nên số đó không bao giờ về 0 (từng làm
        publish_post báo FAILED giả). Chỉ soi đúng ô nhập của composer.

        Hộp thoại đóng dần (có spinner) nên POLL tối đa vài giây thay vì soi 1
        lần — soi sớm quá làm publish_post báo FAILED giả trong khi bài đã lên.
        """
        deadline = time.monotonic() + POST_SUBMIT_CONFIRM_TIMEOUT_MS / 1000
        while True:
            try:
                low = ((await page.text_content("body")) or "").lower()
                if any(p in low for p in POST_SUCCESS_PHRASES):
                    return True
                if not await self._composer_textbox_visible(page):
                    return True
            except Exception:
                pass
            if time.monotonic() >= deadline:
                # Hết giờ mà ô soạn bài vẫn hiển thị -> coi như chưa gửi được.
                return False
            await page.wait_for_timeout(2000)

    @staticmethod
    def _clean_permalink(url: str) -> Optional[str]:
        """Rút URL bài chuẩn (/groups/<id>/posts/<id>/) khỏi URL kèm tracking."""
        if not url:
            return None
        m = re.search(PERMALINK_URL_RE, url)
        return (m.group(0).rstrip("/") + "/") if m else None

    async def _find_published_permalink(self, page, group_url: str, content: str) -> Optional[str]:
        """Mở lại feed nhóm, cuộn, bóc permalink bài chứa lát text vừa đăng."""
        try:
            fragment = " ".join((content or "").split())[:80]
            await page.goto(group_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))
            for _ in range(COMPOSER_VERIFY_SCROLL_PASSES):
                await page.evaluate(f"window.scrollBy(0, {random.randint(600, 1000)})")
                await page.wait_for_timeout(
                    random.randint(SCROLL_WAIT_MIN_MS, SCROLL_WAIT_MAX_MS)
                )
            # 1) Thử bóc thẳng từ href (một số phiên bản FB còn nhả permalink sạch).
            url = await page.evaluate(EXTRACT_LATEST_POST_JS, [fragment])
            if url:
                return url
            # 2) FB đời mới giấu permalink khỏi href — click mốc thời gian của
            #    bài rồi đọc URL đích.
            return await self._permalink_by_clicking_timestamp(page, group_url, fragment)
        except Exception as e:
            logger.debug(f"Không bóc được permalink bài vừa đăng: {e}")
            return None

    async def _permalink_by_clicking_timestamp(
        self, page, group_url: str, fragment: str
    ) -> Optional[str]:
        """Đánh dấu thẻ mốc thời gian của bài chứa lát text, click, đọc URL đích."""
        try:
            marked = await page.evaluate(MARK_TIMESTAMP_ANCHOR_JS, [fragment])
            if not marked:
                return None
            try:
                async with page.expect_navigation(timeout=15000):
                    await page.click(MARK_TIMESTAMP_ANCHOR_SELECTOR, timeout=8000)
            except Exception:
                # Có phiên bản mở dialog thay vì điều hướng — vẫn thử đọc URL.
                pass
            await page.wait_for_timeout(random.randint(1500, 3000))
            permalink = self._clean_permalink(page.url)
            if permalink:
                await page.goto(group_url, wait_until="domcontentloaded")
            return permalink
        except Exception as e:
            logger.debug(f"Click mốc thời gian để lấy permalink lỗi: {e}")
            return None

    async def _verify_comment(self, page, comment_box, comment_text: str) -> CommentStatus:
        """Kiểm tra comment đã gửi thành công chưa bằng 2 tín hiệu.

        | Ô nhập đã trống? | Text xuất hiện NGOÀI ô nhập? | Kết luận |
        |---|---|---|
        | trống | có | SUCCESS |
        | trống | không (sau 1 lần chờ lại) | SHADOWBANNED |
        | còn text | — | FAILED (enter_did_not_submit) |
        | lỗi khi kiểm tra | — | FAILED (verify_error) |
        """
        try:
            # 1. Kiểm tra ô nhập
            is_empty = await _composer_is_empty(comment_box)
            if not is_empty:
                logger.warning("Ô nhập comment vẫn còn text sau Enter (enter_did_not_submit)")
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

            logger.warning("Text không hiển thị ngoài ô nhập sau khi gửi (nghi ngờ shadowban)")
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
                logger.info(" Đã xoá comment")
                return True
            logger.warning(f"Comment có thể chưa xoá (còn {still} node) — kiểm tra lại")
            return False
        except Exception as e:
            logger.error(f"Lỗi xoá comment: {e}")
            return False

    async def _current_account_name(self, page) -> Optional[str]:
        """Tên tài khoản đang đăng nhập, bóc từ payload bootstrap của trang.

        Dùng để phân biệt bài của MÌNH với bài "được đề xuất" / quảng cáo mà FB
        chèn vào trang permalink (cùng nút "Hành động đối với bài viết này...").
        """
        try:
            html = await page.content()
        except Exception:
            return None
        m = re.search(CURRENT_ACCOUNT_NAME_RE, html)
        if not m:
            return None
        try:
            return m.group(1).encode("utf-8").decode("unicode_escape")
        except Exception:
            return m.group(1)

    async def _open_own_post_menu(self, page, account_name: Optional[str]) -> bool:
        """Mở menu hành động của ĐÚNG bài mình đăng trên trang permalink.

        Ưu tiên nút aria-label kèm tên tài khoản ("... của <tên>"); chỉ khi
        không xác định được tên mới rơi về nút khớp chung (query_selector đầu
        tiên — có rủi ro trúng bài người khác). JS click: nút hay bị overlay chắn.
        """
        labels: list[str] = []
        if account_name:
            labels = [tpl.format(name=account_name) for tpl in OWN_POST_MENU_ARIA_NAMED]
        for label in labels:
            btn = await page.query_selector(f'[aria-haspopup="menu"][aria-label*="{label}"]')
            if btn is not None:
                await btn.evaluate("el => el.click()")
                return True
        if account_name:
            logger.error(
                "Không thấy nút hành động của bài mình (tên tài khoản: %s)", account_name
            )
            return False
        for selector in OWN_POST_MENU_SELECTORS:
            try:
                btn = await page.query_selector(selector)
            except Exception:
                btn = None
            if btn is not None:
                logger.warning(
                    "Xoá bài: không xác định được tên tài khoản, dùng nút khớp chung "
                    "(có thể trúng bài người khác) — kiểm tra kỹ kết quả"
                )
                await btn.evaluate("el => el.click()")
                return True
        return False

    async def delete_own_post(
        self, page, post_url: str, author_name: Optional[str] = None
    ) -> bool:
        """Xoá bài viết CHÍNH mình đã đăng — đường rollback / cleanup của publish_post.

        Luồng (DOM group thật 2026-09-10, nick "Hoang Minh"):
          mở permalink → nút "Hành động đối với bài viết này của <tên nick>"
          → menu "Xóa bài viết" / "Chuyển vào thùng rác"
          → hộp thoại xác nhận → nút "Xóa" / "Chuyển".

        `author_name` rỗng → tự bóc tên tài khoản đang đăng nhập từ trang.
        Fail an toàn: không khớp nút menu / mục xoá → trả False, KHÔNG thử mù.

        Returns:
            True nếu mở lại permalink thấy bài đã biến mất; False nếu không.
        """
        if not (post_url or "").strip():
            return False
        try:
            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(2000, 4000))

            name = author_name or await self._current_account_name(page)
            if not await self._open_own_post_menu(page, name):
                logger.error("Không thấy nút menu hành động của bài mình (để xoá)")
                return False
            await random_pause(0.8, 1.6)

            if not await self._click_menu_text(page, OWN_POST_DELETE_MENU_TEXTS):
                logger.error("Không thấy mục 'Xóa bài viết' trong menu")
                return False
            await random_pause(0.8, 1.6)

            await self._confirm_delete_dialog(
                page, OWN_POST_DELETE_CONFIRM_HINTS, OWN_POST_DELETE_CONFIRM_BUTTON_TEXTS
            )
            await random_pause(2.0, 3.5)

            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(random.randint(1500, 3000))
            body = ((await page.text_content("body")) or "").lower()
            if any(marker in body for marker in POST_GONE_MARKERS):
                logger.info("Đã xoá bài viết")
                return True
            logger.warning("Không xác nhận được bài đã xoá — kiểm tra lại")
            return False
        except Exception as e:
            logger.error(f"Lỗi xoá bài viết: {e}")
            return False

    async def _click_menu_text(self, page, texts) -> bool:
        """Trong [role="menu"], click item chứa một trong `texts` (không phân biệt hoa thường)."""
        menu = await page.query_selector('[role="menu"]')
        if menu is None:
            return False
        try:
            items = await menu.query_selector_all('[role="menuitem"], div[role="button"], span')
        except Exception:
            return False
        wanted = [t.lower() for t in texts]
        for item in items:
            try:
                label = (await item.inner_text() or "").strip().lower()
            except Exception:
                continue
            if label and any(w in label for w in wanted):
                # JS click: menu item của FB hay bị lớp phủ (overlay) chắn,
                # click chuột thường bị "subtree intercepts pointer events".
                await item.evaluate("el => el.click()")
                return True
        return False

    async def _confirm_delete_dialog(self, page, hints, button_texts) -> bool:
        """Trong hộp thoại xác nhận (khớp `hints`), bấm nút có nhãn KHỚP TUYỆT ĐỐI."""
        try:
            dialogs = await page.query_selector_all('[role="dialog"]')
        except Exception:
            return False
        for dlg in dialogs:
            try:
                txt = (await dlg.inner_text() or "").lower()
            except Exception:
                continue
            if not any(h in txt for h in hints):
                continue
            try:
                buttons = await dlg.query_selector_all('[role="button"], button')
            except Exception:
                buttons = []
            for btn in buttons:
                try:
                    label = (await btn.inner_text() or "").strip()
                except Exception:
                    continue
                if label in button_texts:
                    await btn.evaluate("el => el.click()")
                    return True
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
        logger.info(f"Đặt lịch comment sau {delay:.0f}s cho bài: {post.post_url}")

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
