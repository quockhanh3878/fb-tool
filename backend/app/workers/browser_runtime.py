"""
Cầu nối giữa backend Phase 2 và mã trình duyệt đã kiểm chứng ở Phase 1.

Thay vì viết lại Scout/Shooter, worker nạp thẳng các module trong thư mục
`commhunter/` (đã chạy thật với khách Nyatymita) và bơm cấu hình lấy từ
PostgreSQL vào. Nhờ vậy mọi vá lỗi anti-ban ở Phase 1 tự động có hiệu lực
cho toàn bộ khách hàng SaaS.
"""
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# commhunter/ nằm cạnh backend/ trong repo; thêm vào sys.path để import phẳng.
COMMHUNTER_DIR = Path(__file__).resolve().parents[3] / "commhunter"
if COMMHUNTER_DIR.is_dir() and str(COMMHUNTER_DIR) not in sys.path:
    sys.path.insert(0, str(COMMHUNTER_DIR))


class BrowserRuntimeUnavailable(RuntimeError):
    """Chưa cài Playwright hoặc không tìm thấy package commhunter."""


@dataclass
class RuntimeAccount:
    """Bản sao tối thiểu của AccountConfig Phase 1."""

    cookie_file: str = ""
    profile_dir: str = ""
    proxy: str | None = None


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


def build_runtime_config(clone, groups: list) -> RuntimeConfig:
    """Dựng cấu hình runtime từ bản ghi clone + group trong DB."""
    account = RuntimeAccount(
        profile_dir=clone.browser_profile_path or f"data/browser_profiles/{clone.id}",
        proxy=clone.proxy_address,
    )
    return RuntimeConfig(
        # Cùng một clone có thể đóng cả hai vai; Phase 1 tra theo khoá cố định.
        accounts={"scout": account, "shooter": account},
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


def write_cookie_file(clone, cookies: list) -> str:
    """Ghi cookie đã giải mã ra file tạm trong thư mục profile của clone."""
    profile_dir = Path(clone.browser_profile_path or f"data/browser_profiles/{clone.id}")
    profile_dir.mkdir(parents=True, exist_ok=True)
    path = profile_dir / "cookies.json"
    path.write_text(json.dumps(cookies, ensure_ascii=False), encoding="utf-8")
    return str(path)


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


async def scan_group_raw(clone, group, cookies: list | None = None) -> list[dict]:
    """Quét 1 group, trả về danh sách bài thô để API xử lý pipeline."""
    BrowserManager, ScoutWorker, _ = load_phase1_modules()
    config = build_runtime_config(clone, [group])
    if cookies:
        write_cookie_file(clone, cookies)

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
    finally:
        await manager.close_all()


async def post_comment_real(clone, post_url: str, comment_text: str, cookies: list | None = None):
    """Đăng 1 comment bằng ShooterWorker Phase 1. Trả về CommentStatus (chuỗi)."""
    BrowserManager, _, ShooterWorker = load_phase1_modules()
    config = build_runtime_config(clone, [])
    if cookies:
        write_cookie_file(clone, cookies)

    manager = BrowserManager(config)
    shooter = ShooterWorker(manager, config)
    try:
        status = await shooter.post_comment(
            post_url=post_url, comment_text=comment_text, dedup_store=None
        )
        return getattr(status, "value", str(status))
    finally:
        await manager.close_all()
