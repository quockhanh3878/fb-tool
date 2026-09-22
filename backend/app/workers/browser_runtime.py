"""
Cầu nối giữa backend Phase 2 và mã trình duyệt đã kiểm chứng ở Phase 1.

Thay vì viết lại Scout/Shooter, worker nạp thẳng các module trong thư mục
`commhunter/` (đã chạy thật với khách Nyatymita) và bơm cấu hình lấy từ
PostgreSQL vào. Nhờ vậy mọi vá lỗi anti-ban ở Phase 1 tự động có hiệu lực
cho toàn bộ khách hàng SaaS.
"""
import asyncio
import sys
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.config import get_settings
from app.services.leases import LeaseBusy, resource_lease
from app.services.url_policy import browser_request_allowed, facebook_url

# commhunter/ nằm cạnh backend/ trong repo; thêm vào sys.path để import phẳng.
COMMHUNTER_DIR = Path(__file__).resolve().parents[3] / "commhunter"
if COMMHUNTER_DIR.is_dir() and str(COMMHUNTER_DIR) not in sys.path:
    sys.path.insert(0, str(COMMHUNTER_DIR))


class BrowserRuntimeUnavailable(RuntimeError):
    """Chưa cài Playwright hoặc không tìm thấy package commhunter."""


def exclusive_browser(function):
    @wraps(function)
    async def guarded(clone, *args, **kwargs):
        if not get_settings().browser_automation_enabled:
            raise BrowserRuntimeUnavailable("browser_automation_disabled")
        try:
            async with resource_lease(f"clone:{clone.id}"):
                async with asyncio.timeout(get_settings().browser_operation_timeout_seconds):
                    return await function(clone, *args, **kwargs)
        except LeaseBusy:
            raise BrowserRuntimeUnavailable("clone_busy") from None
    return guarded


class ScoutCheckpoint(RuntimeError):
    """Clone Scout bị checkpoint / bị đá về trang đăng nhập khi quét.

    Tín hiệu riêng để "mode treo" tự dừng nick thay vì để Beat quét lại mãi.
    `scout_worker.CheckpointError` không import được ở tầng module (kéo theo
    Playwright) nên bắt theo tên lớp rồi bọc lại thành ngoại lệ này.
    """


def wrap_scout_error(exc: BaseException) -> BaseException:
    """Đổi CheckpointError của Phase 1 thành ScoutCheckpoint; giữ nguyên lỗi khác.

    Tách thành hàm thuần để test offline được (không kéo Playwright)."""
    if type(exc).__name__ == "CheckpointError":
        return ScoutCheckpoint(str(exc))
    return exc


@dataclass
class RuntimeAccount:
    """Bản sao tối thiểu của AccountConfig Phase 1."""

    cookie_file: str = ""
    profile_dir: str = ""
    proxy: str | None = None
    # Có giá trị => ScoutWorker/ShooterWorker attach vào Chrome đang mở qua CDP
    # thay vì mở profile persistent (khi đó không cần nạp cookie vào profile).
    cdp_endpoint: str | None = None


@dataclass
class RuntimeBrowser:
    """Đủ để BrowserManager Phase 1 đọc `browser.attach_cdp` toàn cục."""

    attach_cdp: str | None = None
    headless: bool = True
    channel: str = "chromium"
    context_initializer: object = None


@dataclass
class RuntimeComment:
    max_comments_per_day: int = 20
    delay_min_seconds: int = 300
    delay_max_seconds: int = 900
    typing_delay_min_ms: int = 80
    typing_delay_max_ms: int = 350
    typo_probability: float = 0.05
    mode: str = "full_auto"
    ai_model: str = "gpt-4o-mini"


@dataclass
class RuntimeGroup:
    url: str
    name: str = ""
    scan_interval_minutes: int = 10


@dataclass
class RuntimeConfig:
    """Đủ thuộc tính để ScoutWorker/ShooterWorker Phase 1 hoạt động."""

    accounts: dict = field(default_factory=dict)
    groups: list = field(default_factory=list)
    comment: RuntimeComment = field(default_factory=RuntimeComment)
    browser: RuntimeBrowser = field(default_factory=RuntimeBrowser)


def _resolve_cdp_endpoint(explicit: str | None) -> str | None:
    """CDP endpoint muốn dùng: tham số truyền vào > cấu hình > không có."""
    if explicit is not None:
        return explicit.strip() or None
    from app.config import get_settings

    return (get_settings().browser_cdp_endpoint or "").strip() or None


def build_runtime_config(
    clone, groups: list, *, cdp_endpoint: str | None = None
) -> RuntimeConfig:
    """Dựng cấu hình runtime từ bản ghi clone + group trong DB.

    Khi `BROWSER_CDP_ENDPOINT` được đặt (hoặc truyền `cdp_endpoint`), mọi thao
    tác trình duyệt attach vào Chrome đó — không cần cookie clone trong DB.
    """
    endpoint = _resolve_cdp_endpoint(cdp_endpoint)
    account = RuntimeAccount(
        profile_dir=clone.browser_profile_path or f"data/browser_profiles/{clone.id}",
        proxy=None if endpoint else clone.proxy_address,
        cdp_endpoint=endpoint,
    )
    return RuntimeConfig(
        # Cùng một clone có thể đóng cả hai vai; Phase 1 tra theo khoá cố định.
        accounts={"scout": account, "shooter": account},
        browser=RuntimeBrowser(attach_cdp=endpoint),
        groups=[
            RuntimeGroup(
                url=g.group_url,
                name=g.group_name,
                scan_interval_minutes=g.scan_interval_minutes,
            )
            for g in groups
        ],
        comment=RuntimeComment(max_comments_per_day=clone.daily_comment_limit or 20),
    )


def _maybe_write_cookies(config: RuntimeConfig, clone, cookies: list | None) -> None:
    """Install request policy and supply cookies directly in memory."""
    async def initialize(context):
        async def route_request(route):
            if browser_request_allowed(route.request.url):
                await route.continue_()
            else:
                await route.abort()

        await context.route("**/*", route_request)
        if hasattr(context, "route_web_socket"):
            async def deny_socket(socket):
                await socket.close()

            await context.route_web_socket("**/*", deny_socket)
        if cookies and not config.browser.attach_cdp:
            if not isinstance(cookies, list) or any(
                not isinstance(cookie, dict) or not (
                    str(cookie.get("domain", "")).lstrip(".") == "facebook.com"
                    or str(cookie.get("domain", "")).lstrip(".").endswith(".facebook.com")
                ) for cookie in cookies
            ):
                raise ValueError("Only Facebook cookies are accepted")
            await context.add_cookies(cookies)

    config.browser.context_initializer = initialize


def load_phase1_modules():
    """Nạp BrowserManager/ScoutWorker/ShooterWorker của Phase 1.

    Raises:
        BrowserRuntimeUnavailable: khi thiếu Playwright hoặc thiếu mã Phase 1.
    """
    try:
        from browser_manager import BrowserManager  # type: ignore
        from scout_worker import ScoutWorker  # type: ignore
        from shooter_worker import ShooterWorker  # type: ignore
    except ImportError as exc:
        raise BrowserRuntimeUnavailable(
            "Không nạp được module Phase 1 (commhunter/). "
            "Cài playwright và kiểm tra COMMHUNTER_DIR."
        ) from exc
    return BrowserManager, ScoutWorker, ShooterWorker


@exclusive_browser
async def scan_group_raw(clone, group, cookies: list | None = None) -> list[dict]:
    """Quét 1 group, trả về danh sách bài thô để API xử lý pipeline."""
    facebook_url(group.group_url, group=True)
    BrowserManager, ScoutWorker, _ = load_phase1_modules()
    config = build_runtime_config(clone, [group])
    _maybe_write_cookies(config, clone, cookies)

    manager = BrowserManager(config)
    scout = ScoutWorker(manager, config)
    try:
        posts = await scout.scan_group(group.group_url, limit=20)
        return [
            {
                "author": p.author_name,
                "text": p.content_text,
                "url": p.post_url,
                "commentCount": p.existing_comment_count,
            }
            for p in posts
        ]
    except Exception as exc:
        wrapped = wrap_scout_error(exc)
        if wrapped is not exc:
            raise wrapped from exc
        raise
    finally:
        await manager.close_all()


@exclusive_browser
async def scrape_joined_groups_raw(clone, cookies: list | None = None) -> list[dict]:
    """Lấy danh sách nhóm mà tài khoản Scout của clone đã tham gia (chỉ đọc).

    Trả về danh sách dict {key, name, url}; rỗng nếu không bóc được gì.
    """
    BrowserManager, ScoutWorker, _ = load_phase1_modules()
    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)

    manager = BrowserManager(config)
    scout = ScoutWorker(manager, config)
    try:
        return await scout.scrape_joined_groups()
    finally:
        await manager.close_all()


@exclusive_browser
async def scrape_post_comments_raw(
    clone, post_url: str, cookies: list | None = None, limit: int = 100
) -> list[dict]:
    """Đọc comment đã render trên permalink; không click/ghi lên Facebook."""
    post_url = facebook_url(post_url)
    BrowserManager, ScoutWorker, _ = load_phase1_modules()
    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)
    manager = BrowserManager(config)
    scout = ScoutWorker(manager, config)
    try:
        return await scout.scan_post_comments(post_url, limit=limit)
    except Exception as exc:
        wrapped = wrap_scout_error(exc)
        if wrapped is not exc:
            raise wrapped from exc
        raise
    finally:
        await manager.close_all()


@exclusive_browser
async def post_comment_real(clone, post_url: str, comment_text: str, cookies: list | None = None):
    """Đăng comment và trả status cùng locator nếu Facebook hiển thị được link."""
    post_url = facebook_url(post_url)
    BrowserManager, _, ShooterWorker = load_phase1_modules()
    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)

    manager = BrowserManager(config)
    shooter = ShooterWorker(manager, config)
    try:
        status = await shooter.post_comment(
            post_url=post_url, comment_text=comment_text, dedup_store=None
        )
        comment_url = getattr(shooter, "last_comment_url", "") or ""
        comment_id = parse_qs(urlsplit(comment_url).query).get("comment_id", [""])[0]
        return {
            "status": getattr(status, "value", str(status)),
            "comment_url": comment_url,
            "fb_comment_id": comment_id,
        }
    finally:
        await manager.close_all()


@exclusive_browser
async def publish_post_real(
    clone,
    group_url: str,
    content: str,
    cookies: list | None = None,
    media_paths: list[str] | None = None,
) -> dict:
    """Đăng 1 bài viết vào group bằng ShooterWorker Phase 1.

    Trả về dict {status, post_url, error} — status là chuỗi PublishStatus
    ('published' | 'published_no_url' | 'failed'). KHÔNG bao giờ bịa link.
    """
    group_url = facebook_url(group_url, group=True)
    BrowserManager, _, ShooterWorker = load_phase1_modules()
    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)

    manager = BrowserManager(config)
    shooter = ShooterWorker(manager, config)
    try:
        result = await shooter.publish_post(
            group_url=group_url, content=content, media_paths=media_paths
        )
        return {
            "status": getattr(result.status, "value", str(result.status)),
            "post_url": result.post_url,
            "error": result.error,
        }
    finally:
        await manager.close_all()


@exclusive_browser
async def preflight_check_real(clone, cookies: list | None = None) -> dict:
    """Kiểm tra sức khoẻ nick + phiên đăng nhập TRƯỚC một lượt quét/đăng (Track D).

    Mở browser (attach CDP nếu có), vào facebook.com, xác nhận feed load bình
    thường. Trả về {"ok": bool, "reason": str} — reason là "ok" / "checkpoint" /
    "login_expired" / "error" / thông báo BrowserRuntimeUnavailable.
    """
    try:
        BrowserManager, _, _ = load_phase1_modules()
    except BrowserRuntimeUnavailable as exc:
        return {"ok": False, "reason": f"runtime_unavailable: {exc}"}

    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)
    profile_dir = config.accounts["scout"].profile_dir

    manager = BrowserManager(config)
    try:
        account = config.accounts["scout"]
        await manager.create_stealth_context(
            profile_dir=account.profile_dir, proxy=account.proxy, cdp_endpoint=account.cdp_endpoint,
        )
        reason = await manager.probe_session_reason(profile_dir)
    except Exception as exc:  # noqa: BLE001 - preflight không được giết caller
        reason = "error"
        log_detail = str(exc)
        return {"ok": False, "reason": reason, "detail": log_detail}
    finally:
        await manager.close_all()
    return {"ok": reason == "ok", "reason": reason}


@exclusive_browser
async def delete_own_post_real(
    clone, post_url: str, cookies: list | None = None
) -> bool:
    """Xoá 1 bài viết chính clone đã đăng — đường dọn dẹp / rollback thủ công.

    Cầu nối theo khuôn `publish_post_real`. Trả về True nếu mở lại permalink
    thấy bài đã biến mất; False nếu không khớp menu / không xác nhận được.
    KHÔNG thử mù, fail an toàn.
    """
    post_url = facebook_url(post_url)
    BrowserManager, _, ShooterWorker = load_phase1_modules()
    config = build_runtime_config(clone, [])
    _maybe_write_cookies(config, clone, cookies)

    manager = BrowserManager(config)
    shooter = ShooterWorker(manager, config)
    try:
        page = await shooter._get_page()
        return await shooter.delete_own_post(page, post_url)
    finally:
        await manager.close_all()
