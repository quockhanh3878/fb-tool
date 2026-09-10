"""
Browser Manager — Quản lý Playwright context cho từng nick clone.

Kế thừa từ openclaw/create_browser_context + fbn/browser.py, nâng lên:
  • channel="chrome"  — chạy Google Chrome THẬT đã cài, không phải Chromium
    bundled (khó bị Facebook phát hiện hơn nhiều).
  • Vân tay theo từng nick — canvas / WebGL / hardwareConcurrency… cố định
    và khớp nhau, sinh từ fingerprint.py, lưu trong profile.
  • Chế độ ATTACH (CDP) — cắm vào một Chrome đang chạy sẵn để test tay trên
    nick thật đã đăng nhập, không tự mở profile mới.

Triết lý: nuôi nick bằng browser thật + thao tác UI như người an toàn hơn
headless + gọi mã trực tiếp. Vì thế mặc định `headless=False`.
"""
import asyncio
import random
from pathlib import Path
from typing import Optional

from loguru import logger

from constants import (
    BROWSER_ARGS,
    BROWSER_CHANNEL,
    BROWSER_CHANNEL_FALLBACK,
    BROWSER_HEADLESS_DEFAULT,
    CHECKPOINT_URL_PATTERNS,
    LOCALE,
    TIMEZONE,
    USER_AGENTS_POOL,
    VIEWPORT,
)
from fingerprint import build_stealth_init_js, load_or_create_fingerprint


def stealth_status() -> tuple[bool, str]:
    """Kiểm tra playwright-stealth có khả dụng không, và theo API version nào.

    Returns:
        (khả_dụng, mô_tả). Dùng cho lệnh `commhunter.py status` để cảnh báo
        sớm thay vì chạy trần mà không ai biết.
    """
    try:
        import playwright_stealth as _ps
    except ImportError:
        return False, "playwright-stealth CHƯA ĐƯỢC CÀI"

    version = getattr(_ps, "__version__", "unknown")
    if getattr(_ps, "Stealth", None) is not None:
        return True, f"playwright-stealth {version} (API v2: Stealth)"
    if getattr(_ps, "stealth_async", None) is not None:
        return True, f"playwright-stealth {version} (API v1: stealth_async)"
    return False, (
        f"playwright-stealth {version} đã cài nhưng KHÔNG tìm thấy API quen thuộc "
        "(Stealth / stealth_async)"
    )


def _stealth_kwargs_from_fingerprint(fp: Optional[dict]) -> dict:
    """Ép playwright-stealth khai đúng giá trị vân tay của nick thay vì mặc
    định dùng chung (mặc định renderer của stealth là 'Intel Iris OpenGL
    Engine' — cùng một chuỗi trên MỌI nick, phản tác dụng)."""
    if not fp:
        return {}
    kwargs = {}
    langs = fp.get("languages") or []
    if len(langs) >= 2:
        kwargs["navigator_languages_override"] = (langs[0], langs[1])
    if fp.get("platform"):
        kwargs["navigator_platform_override"] = fp["platform"]
    if fp.get("user_agent"):
        kwargs["navigator_user_agent_override"] = fp["user_agent"]
    if fp.get("webgl_vendor"):
        kwargs["webgl_vendor_override"] = fp["webgl_vendor"]
    if fp.get("webgl_renderer"):
        kwargs["webgl_renderer_override"] = fp["webgl_renderer"]
    # hardwareConcurrency / deviceMemory để init script của ta lo (stealth ép cứng 4).
    kwargs["navigator_hardware_concurrency"] = False
    return kwargs


async def apply_stealth(target, fingerprint: Optional[dict] = None) -> bool:
    """Áp dụng stealth cho 1 page HOẶC cả 1 context, tương thích v1 và v2.

    v1.x expose hàm `stealth_async(page)`.
    v2.x bỏ hàm đó, thay bằng class `Stealth`; apply_stealth_async nhận cả
    Page lẫn BrowserContext (context = phủ mọi page hiện tại + tương lai).

    Returns:
        True nếu đã áp dụng được, False nếu không (đang chạy TRẦN).
    """
    try:
        import playwright_stealth as _ps
    except ImportError:
        return False

    # --- API v2: class Stealth ---
    stealth_cls = getattr(_ps, "Stealth", None)
    if stealth_cls is not None:
        kwargs = _stealth_kwargs_from_fingerprint(fingerprint)
        try:
            instance = stealth_cls(**kwargs)
        except TypeError:
            instance = stealth_cls()
        except Exception as e:  # pragma: no cover - phụ thuộc version
            logger.error(f"Không khởi tạo được Stealth(): {e}")
            return False
        for method_name in ("apply_stealth_async", "apply_async", "apply_stealth"):
            method = getattr(instance, method_name, None)
            if method is None:
                continue
            try:
                result = method(target)
                if hasattr(result, "__await__"):
                    await result
                return True
            except Exception as e:
                logger.error(f"Stealth.{method_name}() lỗi: {e}")
                return False
        logger.error(
            "playwright-stealth v2 đã cài nhưng không tìm thấy method apply_* — "
            "kiểm tra lại API của version đang dùng"
        )
        return False

    # --- API v1: hàm stealth_async (chỉ nhận page) ---
    stealth_fn = getattr(_ps, "stealth_async", None)
    if stealth_fn is not None:
        try:
            await stealth_fn(target)
            return True
        except Exception as e:
            logger.error(f"stealth_async() lỗi: {e}")
            return False

    return False


class BrowserManager:
    """Quản lý Playwright browser contexts với anti-detection."""

    def __init__(self, config=None):
        self.config = config
        self._playwright = None
        self._contexts = {}  # {key: {"context", "attached", "browser"?}}

        # Cấu hình runtime — AppConfig có .browser; RuntimeConfig của backend
        # có thể không có, nên dùng getattr với mặc định an toàn.
        browser_cfg = getattr(config, "browser", None)
        self.channel = getattr(browser_cfg, "channel", BROWSER_CHANNEL)
        self.default_headless = bool(
            getattr(browser_cfg, "headless", BROWSER_HEADLESS_DEFAULT)
        )
        self.default_cdp = getattr(browser_cfg, "attach_cdp", None)

    async def _get_playwright(self):
        """Lazy-init Playwright instance."""
        if self._playwright is None:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
        return self._playwright

    # ── Chế độ ATTACH (CDP) ────────────────────────────────────────────────
    async def _attach_cdp_context(self, key: str, cdp_endpoint: str):
        """Cắm vào một Chrome đang chạy sẵn qua CDP.

        Chrome đó phải được mở với `--remote-debugging-port=<port>`. KHÔNG
        spoof fingerprint (đây là browser thật), KHÔNG áp proxy.
        """
        p = await self._get_playwright()
        logger.info(f"Attach vào Chrome qua CDP: {cdp_endpoint}")
        browser = await p.chromium.connect_over_cdp(cdp_endpoint)

        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = await browser.new_context()

        # KHÔNG áp stealth: đây là Chrome thật của người dùng, vá thêm chỉ làm
        # nó trông lạ hơn. Dùng nguyên trạng.
        self._contexts[key] = {"context": context, "attached": True, "browser": browser}
        logger.info(
            f"Đã attach — {len(context.pages)} tab đang mở. "
            "Sẽ KHÔNG đóng browser này khi dọn dẹp."
        )
        return context

    # ── Chế độ persistent (nick clone) ────────────────────────────────────
    async def _launch_persistent(
        self,
        profile_dir: str,
        proxy: Optional[str],
        headless: bool,
        user_agent: Optional[str],
    ):
        p = await self._get_playwright()
        Path(profile_dir).mkdir(parents=True, exist_ok=True)

        fp = load_or_create_fingerprint(profile_dir)
        ua = user_agent or fp.get("user_agent") or random.choice(USER_AGENTS_POOL)
        viewport = fp.get("viewport") or VIEWPORT

        proxy_config = {"server": proxy} if proxy else None
        if proxy:
            logger.info(f"Sử dụng proxy: {proxy}")

        launch_kwargs = dict(
            user_data_dir=profile_dir,
            headless=headless,
            viewport=viewport,
            user_agent=ua,
            args=BROWSER_ARGS,
            ignore_default_args=["--enable-automation"],
            locale=fp.get("locale", LOCALE),
            timezone_id=fp.get("timezone", TIMEZONE),
            proxy=proxy_config,
        )

        # channel="chrome" cần Google Chrome đã cài. Nếu máy không có → rơi về
        # Chromium bundled thay vì chết.
        try:
            context = await p.chromium.launch_persistent_context(
                channel=self.channel, **launch_kwargs
            )
            active_channel = self.channel
        except Exception as e:
            logger.warning(
                f"Không mở được channel '{self.channel}' ({e}). "
                f"Rơi về '{BROWSER_CHANNEL_FALLBACK}'."
            )
            context = await p.chromium.launch_persistent_context(
                channel=BROWSER_CHANNEL_FALLBACK, **launch_kwargs
            )
            active_channel = BROWSER_CHANNEL_FALLBACK

        # 1) playwright-stealth ở cấp CONTEXT (phủ mọi page hiện tại + tương lai),
        #    đã nhồi sẵn UA / platform / WebGL vendor+renderer của vân tay nick này.
        applied = await apply_stealth(context, fingerprint=fp)
        if not applied:
            logger.warning(
                "KHÔNG áp dụng được playwright-stealth — chạy `commhunter.py status`."
            )

        # 2) Init script vân tay CHẠY SAU stealth → thắng ở hardwareConcurrency /
        #    deviceMemory / screen / nhiễu canvas. Áp cho cả page mở sau.
        try:
            await context.add_init_script(build_stealth_init_js(fp))
        except Exception as e:
            logger.error(f"Không chèn được init script vân tay: {e}")

        self._contexts[profile_dir] = {"context": context, "attached": False}
        logger.info(
            f"Đã tạo context [{active_channel}] tại {profile_dir} "
            f"(headless={headless}, UA={ua.split(') ')[0]})…)"
        )
        return context

    async def create_stealth_context(
        self,
        profile_dir: str,
        proxy: Optional[str] = None,
        headless: Optional[bool] = None,
        user_agent: Optional[str] = None,
        cdp_endpoint: Optional[str] = None,
    ):
        """Khởi tạo context Playwright cho 1 nick.

        Args:
            profile_dir: Thư mục lưu profile (cookies, storage, fingerprint.json).
            proxy: Proxy URL (bỏ qua khi attach CDP).
            headless: None = theo cấu hình `browser.headless` (mặc định False).
            user_agent: Ghi đè UA của vân tay (hiếm khi cần).
            cdp_endpoint: None = theo `browser.attach_cdp`. Nếu có giá trị,
                ATTACH vào Chrome đang chạy thay vì mở profile mới.

        Returns:
            Playwright BrowserContext.
        """
        # cdp_endpoint=None  → chưa chỉ định, dùng browser.attach_cdp toàn cục.
        # cdp_endpoint=""    → ÉP persistent, bỏ qua attach_cdp (login_interactive).
        # cdp_endpoint="..." → attach vào endpoint đó.
        if cdp_endpoint is None:
            endpoint = self.default_cdp
        else:
            endpoint = cdp_endpoint.strip() or None

        if endpoint:
            key = f"cdp::{endpoint}"
            existing = self._contexts.get(key)
            if existing:
                return existing["context"]
            return await self._attach_cdp_context(key, endpoint)

        existing = self._contexts.get(profile_dir)
        if existing:
            return existing["context"]

        resolved_headless = (
            self.default_headless if headless is None else bool(headless)
        )
        return await self._launch_persistent(
            profile_dir, proxy, resolved_headless, user_agent
        )

    async def get_stealth_page(self, profile_dir: str):
        """Tạo page mới. Stealth + vân tay đã gắn ở CẤP CONTEXT nên page mới
        tự kế thừa — KHÔNG gọi lại apply_stealth per-page (sẽ ghi đè WebGL
        bằng giá trị mặc định dùng chung của stealth)."""
        ctx_info = self._contexts.get(profile_dir) or self._contexts.get(
            f"cdp::{self.default_cdp}"
        )
        if not ctx_info:
            raise ValueError(f"Chưa tạo context cho profile: {profile_dir}")

        return await ctx_info["context"].new_page()

    async def login_interactive(self, profile_dir: str, proxy: Optional[str] = None):
        """Mở browser có giao diện để login tay 1 lần rồi lưu session vào profile_dir."""
        context = await self.create_stealth_context(
            profile_dir=profile_dir,
            proxy=proxy,
            headless=False,  # Hiện browser để login tay
            cdp_endpoint="",  # ép persistent, kể cả khi có attach_cdp toàn cục
        )

        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

        logger.info("Browser đã mở. Vui lòng đăng nhập Facebook thủ công...")
        logger.info("   Sau khi đăng nhập xong, nhấn Enter tại terminal này để lưu session.")

        await asyncio.get_running_loop().run_in_executor(
            None, input, ">>> Nhấn Enter sau khi đăng nhập xong..."
        )

        is_logged = await self.check_session(profile_dir)
        if is_logged:
            logger.info("Đăng nhập thành công! Session đã được lưu.")
        else:
            logger.warning("Có vẻ chưa đăng nhập thành công. Kiểm tra lại.")

        await self._close_one(profile_dir)
        return is_logged

    async def check_session(
        self, profile_dir: str, cdp_endpoint: Optional[str] = None
    ) -> bool:
        """Kiểm tra session còn sống không.

        Returns:
            True nếu session hợp lệ, False nếu cần đăng nhập lại / bị checkpoint.
        """
        endpoint = cdp_endpoint or self.default_cdp
        key = f"cdp::{endpoint}" if endpoint else profile_dir
        preexisting = key in self._contexts

        context = None
        try:
            context = await self.create_stealth_context(
                profile_dir=profile_dir,
                headless=True if not endpoint else None,
                cdp_endpoint=cdp_endpoint,
            )
            page = context.pages[0] if context.pages else await context.new_page()

            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            if self.detect_checkpoint_url(page.url):
                logger.warning(f"Session bị checkpoint tại: {page.url}")
                return False

            login_button = await page.query_selector('button[name="login"]')
            if login_button:
                logger.warning("Session hết hạn — cần đăng nhập lại")
                return False

            logger.info("Session hợp lệ")
            return True

        except Exception as e:
            logger.error(f"Lỗi kiểm tra session: {e}")
            return False

        finally:
            # Chỉ dọn context do CHÍNH hàm này vừa tạo. Nếu context đã tồn tại
            # trước đó (Scout/Shooter đang dùng, hoặc là browser attach của
            # người dùng) thì để nguyên.
            if context is not None and not preexisting:
                await self._close_one(key)

    @staticmethod
    def detect_checkpoint_url(url: str) -> bool:
        """Phát hiện URL checkpoint/security check."""
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in CHECKPOINT_URL_PATTERNS)

    # Cụm từ CHỈ xuất hiện trên trang checkpoint/khóa tài khoản thật. KHÔNG
    # dùng "verify"/"xác minh"/"checkpoint" trần — chúng nằm rải rác khắp UI
    # Facebook (huy hiệu "đã xác minh", "xác minh 2 yếu tố" trong cài đặt…) và
    # từng khiến Shooter báo checkpoint giả trên bài viết bình thường.
    CHECKPOINT_STRONG_PHRASES = [
        "chúng tôi đã tạm khóa tài khoản",
        "tài khoản của bạn đã bị vô hiệu hóa",
        "tài khoản của bạn đã bị khóa",
        "hãy xác nhận danh tính của bạn",
        "xác nhận danh tính của bạn",
        "nhập mã đăng nhập",
        "giúp chúng tôi xác nhận đây là bạn",
        "we've temporarily locked",
        "your account has been disabled",
        "your account is locked",
        "please confirm your identity",
        "help us confirm it's you",
        "enter the code from your",
    ]

    @staticmethod
    async def detect_checkpoint_page(page) -> bool:
        """Phát hiện checkpoint trên page hiện tại.

        Tin URL trước hết (dấu hiệu chắc chắn nhất). Chỉ xét nội dung khi trang
        KHÔNG render feed/bài viết bình thường — trang checkpoint thật không có
        `[role="feed"]` hay `[role="article"]`.
        """
        if BrowserManager.detect_checkpoint_url(page.url):
            return True

        try:
            has_normal_content = await page.evaluate(
                "!!document.querySelector('[role=\"feed\"], [role=\"article\"], "
                "[aria-label*=\"Viết bình luận\"], [aria-label*=\"Write a comment\"]')"
            )
            if has_normal_content:
                return False

            content = (await page.text_content("body")) or ""
            low = content.lower()
            return any(p in low for p in BrowserManager.CHECKPOINT_STRONG_PHRASES)
        except Exception:
            pass

        return False

    async def _close_one(self, key: str) -> None:
        """Đóng 1 context. Nếu là attach (CDP) thì chỉ NGẮT KẾT NỐI, không
        giết Chrome của người dùng."""
        ctx_info = self._contexts.pop(key, None)
        if not ctx_info:
            return
        try:
            if ctx_info.get("attached"):
                browser = ctx_info.get("browser")
                if browser is not None:
                    await browser.close()  # CDP: chỉ disconnect
                logger.info(f"Đã ngắt kết nối CDP: {key}")
            else:
                await ctx_info["context"].close()
                logger.info(f"Đã đóng context: {key}")
        except Exception as e:
            logger.error(f"Lỗi đóng context {key}: {e}")

    async def close_all(self):
        """Đóng tất cả context. Browser attach chỉ bị ngắt kết nối."""
        for key in list(self._contexts.keys()):
            await self._close_one(key)
        self._contexts.clear()

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
