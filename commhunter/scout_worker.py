"""
Scout Worker — Module quét bài viết từ Facebook Group.
Kế thừa từ openclaw/fb-group-monitor.py EXTRACT_POST_JS + cmd_scrape.
"""
import asyncio
import random
import re
from datetime import datetime
from typing import List


def extract_post_id(url: str) -> str:
    """Trích xuất Facebook post_id từ URL.
    
    Hỗ trợ:
    - /posts/123456789/ hoặc /posts/123456789
    - /permalink/123456789/ hoặc /permalink/123456789
    - story_fbid=123456789 hoặc fbid=123456789
    - URL kết thúc bằng id số
    """
    if not url:
        return ""
    # Pattern 1: /(?:posts|permalink)/(\d+)
    m = re.search(r"/(?:posts|permalink)/(\d+)", url)
    if m:
        return m.group(1)
    # Pattern 2: story_fbid=(\d+) hoặc fbid=(\d+)
    m = re.search(r"[?&](?:story_fbid|fbid)=(\d+)", url)
    if m:
        return m.group(1)
    # Pattern 3: Fallback số ở cuối path
    m = re.search(r"/(\d+)/?$", url)
    if m:
        return m.group(1)
    return ""


from loguru import logger

from browser_manager import BrowserManager
from constants import (
    EXTRACT_COMMENTS_JS,
    EXTRACT_GROUPS_JS,
    EXTRACT_POST_JS,
    FEED_SELECTOR,
    GROUPS_SCROLL_PASSES,
    JOINED_GROUPS_URL,
    PAGE_LOAD_WAIT_MIN_MS,
    PAGE_LOAD_WAIT_MAX_MS,
    SCROLL_WAIT_MIN_MS,
    SCROLL_WAIT_MAX_MS,
    SCROLL_PASSES,
    SCAN_DELAY_MIN_SEC,
    SCAN_DELAY_MAX_SEC,
)
from dedup_store import DedupStore, compute_content_hash
from models import DiscoveredPost, PostStatus, AppConfig


class CheckpointError(Exception):
    """Scout account bị checkpoint/yêu cầu xác minh."""
    pass


class ScoutWorker:
    """Module quét bài viết từ Facebook Groups."""

    def __init__(self, browser_mgr: BrowserManager, config: AppConfig):
        self.browser_mgr = browser_mgr
        self.config = config
        self._context = None
        self._page = None

    async def _ensure_context(self):
        """Đảm bảo browser context đã sẵn sàng."""
        scout_cfg = self.config.accounts.get("scout")
        if not scout_cfg:
            raise ValueError("Chưa cấu hình tài khoản scout trong config.accounts")

        if self._context is None:
            self._context = await self.browser_mgr.create_stealth_context(
                profile_dir=scout_cfg.profile_dir,
                proxy=scout_cfg.proxy,
                headless=None,  # theo cấu hình browser.headless
                cdp_endpoint=getattr(scout_cfg, "cdp_endpoint", None),
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

    async def scan_group(self, group_url: str, limit: int = 20) -> List[DiscoveredPost]:
        """Navigate đến group, cuộn feed, extract bài viết.
        
        Args:
            group_url: URL của Facebook group.
            limit: Số bài tối đa cần lấy.
        
        Returns:
            Danh sách DiscoveredPost.
        
        Raises:
            CheckpointError: Nếu tài khoản bị checkpoint.
        """
        page = await self._get_page()
        posts = []

        try:
            # Bước 1: Navigate đến group
            logger.info(f"Scout: Đang quét group {group_url}")
            await page.goto(group_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(
                random.randint(PAGE_LOAD_WAIT_MIN_MS, PAGE_LOAD_WAIT_MAX_MS)
            )

            # Bước 2: Kiểm tra checkpoint
            current_url = page.url
            if BrowserManager.detect_checkpoint_url(current_url):
                raise CheckpointError(f"Scout account bị checkpoint tại {current_url}")

            if "login" in current_url.lower():
                raise CheckpointError(f"Scout cần đăng nhập lại: {current_url}")

            # Bước 3: Cuộn feed để load thêm bài
            for i in range(SCROLL_PASSES):
                scroll_distance = random.randint(800, 1200)
                await page.evaluate(f"window.scrollBy(0, {scroll_distance})")
                await page.wait_for_timeout(
                    random.randint(SCROLL_WAIT_MIN_MS, SCROLL_WAIT_MAX_MS)
                )
                logger.debug(f"Cuộn feed lần {i + 1}/{SCROLL_PASSES}")

            # Bước 4: Extract bài viết bằng JS
            feed_children = await page.query_selector_all(FEED_SELECTOR)
            logger.info(f"Tìm thấy {len(feed_children)} elements trong feed")

            for child in feed_children:
                if len(posts) >= limit:
                    break

                try:
                    data = await child.evaluate(EXTRACT_POST_JS)
                    if data and data.get("text") and len(data["text"]) > 20:
                        # Parse group name từ URL hoặc page title
                        group_name = self._extract_group_name(group_url)

                        content_hash = compute_content_hash(
                            data.get("author", "Unknown"),
                            data.get("text", ""),
                        )

                        post = DiscoveredPost(
                            post_id=extract_post_id(data.get("url", "")),
                            post_url=data.get("url", ""),
                            group_url=group_url,
                            group_name=group_name,
                            author_name=data.get("author", "Unknown"),
                            content_text=data.get("text", ""),
                            existing_comment_count=data.get("commentCount", 0),
                            status=PostStatus.NEW,
                            discovered_at=datetime.now(),
                            content_hash=content_hash,
                        )
                        posts.append(post)
                except Exception as e:
                    logger.debug(f"Bỏ qua element lỗi: {e}")

            logger.info(f"Quét được {len(posts)} bài viết từ {group_url}")

        except CheckpointError:
            raise
        except Exception as e:
            logger.error(f"Lỗi quét group {group_url}: {e}")

        return posts

    async def scrape_joined_groups(self, limit: int = 300) -> List[dict]:
        """Mở trang "Nhóm của bạn" của tài khoản Scout, cuộn và bóc danh sách nhóm đã tham gia.

        Chỉ ĐỌC — không join, không rời nhóm, không tương tác gì khác.

        Returns:
            Danh sách dict {key, name, url}. Rỗng nếu không bóc được gì
            (selector đổi hoặc tài khoản chưa tham gia nhóm nào).

        Raises:
            CheckpointError: nếu tài khoản Scout bị checkpoint / bị đá về trang đăng nhập.
        """
        page = await self._get_page()

        try:
            logger.info("Scout: đang lấy danh sách nhóm đã tham gia")
            await page.goto(JOINED_GROUPS_URL, wait_until="domcontentloaded")
            await page.wait_for_timeout(
                random.randint(PAGE_LOAD_WAIT_MIN_MS, PAGE_LOAD_WAIT_MAX_MS)
            )

            current_url = page.url
            if BrowserManager.detect_checkpoint_url(current_url):
                raise CheckpointError(f"Scout account bị checkpoint tại {current_url}")
            if "login" in current_url.lower():
                raise CheckpointError(f"Scout cần đăng nhập lại: {current_url}")

            for i in range(GROUPS_SCROLL_PASSES):
                await page.evaluate(
                    f"window.scrollBy(0, {random.randint(800, 1400)})"
                )
                await page.wait_for_timeout(
                    random.randint(SCROLL_WAIT_MIN_MS, SCROLL_WAIT_MAX_MS)
                )
                logger.debug(f"Cuộn danh sách nhóm lần {i + 1}/{GROUPS_SCROLL_PASSES}")

            raw = await page.evaluate(EXTRACT_GROUPS_JS)
            if not raw:
                logger.warning(
                    "Không bóc được nhóm nào từ trang 'Nhóm của bạn' — "
                    "selector có thể đã đổi hoặc tài khoản chưa tham gia nhóm nào"
                )
                return []

            seen = set()
            groups: List[dict] = []
            for item in raw:
                key = (item or {}).get("key", "")
                if not key or key in seen:
                    continue
                seen.add(key)
                groups.append(
                    {
                        "key": key,
                        "name": (item.get("name") or key).strip(),
                        "url": item.get("url")
                        or f"https://www.facebook.com/groups/{key}/",
                    }
                )
                if len(groups) >= limit:
                    break

            logger.info(f"Lấy được {len(groups)} nhóm đã tham gia")
            return groups

        except CheckpointError:
            raise
        except Exception as e:
            logger.error(f"Lỗi lấy danh sách nhóm đã tham gia: {e}")
            return []

    async def scan_post_comments(self, post_url: str, limit: int = 100) -> list[dict]:
        """Đọc comment đã render trên permalink bài viết, chỉ đọc và fail-safe."""
        page = await self._get_page()
        if not post_url or limit < 1:
            return []
        try:
            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(
                random.randint(PAGE_LOAD_WAIT_MIN_MS, PAGE_LOAD_WAIT_MAX_MS)
            )
            if BrowserManager.detect_checkpoint_url(page.url) or "login" in page.url.lower():
                raise CheckpointError(f"Scout cần xác minh khi đọc comment tại {page.url}")
            for _ in range(2):
                await page.evaluate("window.scrollBy(0, 900)")
                await page.wait_for_timeout(random.randint(700, 1400))
            raw = await page.evaluate(EXTRACT_COMMENTS_JS, [post_url, min(limit, 200)])
            return raw if isinstance(raw, list) else []
        except CheckpointError:
            raise
        except Exception as exc:
            logger.warning(f"Không bóc được comment từ {post_url}: {exc}")
            return []

    def filter_new_posts(
        self, posts: List[DiscoveredPost], dedup_store: DedupStore
    ) -> List[DiscoveredPost]:
        """Lọc bỏ bài viết đã xử lý trước đó.
        
        Args:
            posts: Danh sách bài viết vừa quét được.
            dedup_store: DedupStore để kiểm tra trùng lặp.
        
        Returns:
            Chỉ các bài viết mới chưa thấy trước đó.
        """
        new_posts = []
        for post in posts:
            if not dedup_store.is_seen(post.content_hash):
                dedup_store.insert_post(post)
                new_posts.append(post)
            else:
                logger.debug(f"Bài đã thấy: {post.content_hash[:8]}... — {post.author_name}")

        dedup_store.increment_scanned(len(posts))
        logger.info(f"Lọc: {len(new_posts)}/{len(posts)} bài mới")
        return new_posts

    def _extract_group_name(self, group_url: str) -> str:
        """Rút tên group từ config dựa trên URL."""
        for g in self.config.groups:
            if g.url.rstrip("/") == group_url.rstrip("/"):
                return g.name
        return group_url.split("/groups/")[-1].strip("/")

    async def run_scout_loop(self, dedup_store: DedupStore, callback=None):
        """Vòng lặp chính: Quét tất cả group theo scan_interval.
        
        Args:
            dedup_store: DedupStore instance.
            callback: Async callable nhận danh sách bài viết mới.
        """
        logger.info("Scout loop khởi động")

        while True:
            for group in self.config.groups:
                try:
                    posts = await self.scan_group(group.url, limit=20)
                    new_posts = self.filter_new_posts(posts, dedup_store)

                    if new_posts and callback:
                        await callback(new_posts)

                    # Giãn cách giữa các group
                    await asyncio.sleep(random.uniform(SCAN_DELAY_MIN_SEC, SCAN_DELAY_MAX_SEC))

                except CheckpointError as e:
                    logger.error(f"{e}")
                    logger.error("Scout loop tạm dừng 30 phút do checkpoint")
                    await asyncio.sleep(30 * 60)
                    break  # Thoát vòng for, quay lại while

                except Exception as e:
                    logger.error(f"Lỗi scout group {group.url}: {e}")
                    await asyncio.sleep(60)

            # Đợi đến chu kỳ quét tiếp
            min_interval = min(
                (g.scan_interval_minutes for g in self.config.groups),
                default=10,
            )
            wait_time = min_interval * 60
            logger.info(f"Đợi {min_interval} phút đến chu kỳ quét tiếp...")
            await asyncio.sleep(wait_time)
