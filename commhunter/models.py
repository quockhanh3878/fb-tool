"""
Data classes cho toàn bộ hệ thống CommHunter MVP.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from constants import (
    BROWSER_CHANNEL,
    BROWSER_HEADLESS_DEFAULT,
    DEFAULT_DB_PATH,
    MAX_COMMENTS_PER_DAY,
)


class PostStatus(Enum):
    NEW = "new"
    NOTIFIED = "notified"
    COMMENTED = "commented"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class CommentStatus(Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SHADOWBANNED = "shadowbanned"


class PublishStatus(Enum):
    """Kết quả đăng bài seeding vào 1 group."""
    PUBLISHED = "published"                # đăng xong, đã xác minh permalink
    PUBLISHED_NO_URL = "published_no_url"  # đăng xong nhưng không bóc được link
    FAILED = "failed"                      # không đăng được (selector, checkpoint...)


@dataclass
class PublishResult:
    """Kết quả một lần đăng bài vào một group."""
    status: PublishStatus
    post_url: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DiscoveredPost:
    """Bài viết được tìm thấy từ Scout."""
    post_id: str
    post_url: str
    group_url: str
    group_name: str
    author_name: str
    content_text: str
    existing_comment_count: int
    ai_relevance_score: float = 0.0
    ai_reason: str = ""
    ai_extracted: dict = field(default_factory=dict)
    status: PostStatus = PostStatus.NEW
    discovered_at: datetime = field(default_factory=datetime.now)
    content_hash: str = ""  # MD5 hash for dedup


@dataclass
class CommentAction:
    """Hành động comment vào bài viết."""
    post: DiscoveredPost
    comment_content: str
    status: CommentStatus = CommentStatus.QUEUED
    error_message: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None


@dataclass
class GroupConfig:
    """Cấu hình 1 group cần giám sát."""
    url: str
    name: str
    scan_interval_minutes: int = 10


@dataclass
class AccountConfig:
    """Cấu hình 1 tài khoản Facebook."""
    cookie_file: str
    profile_dir: str
    proxy: Optional[str] = None
    # Nếu đặt (VD "http://localhost:9222"), BrowserManager sẽ ATTACH vào một
    # Chrome đang chạy sẵn qua CDP thay vì tự mở persistent context. Dùng để
    # test tay trên nick thật đã đăng nhập trong Chrome. Khi attach: KHÔNG
    # spoof fingerprint, KHÔNG áp proxy (Chrome đó tự lo), KHÔNG đóng browser
    # của người dùng lúc dọn dẹp.
    cdp_endpoint: Optional[str] = None


@dataclass
class BrowserConfig:
    """Cấu hình runtime trình duyệt dùng chung cho Scout + Shooter."""
    channel: str = BROWSER_CHANNEL          # "chrome" | "chromium" | "msedge"
    headless: bool = BROWSER_HEADLESS_DEFAULT
    # CDP endpoint mặc định — account.cdp_endpoint ghi đè nếu có.
    attach_cdp: Optional[str] = None


@dataclass
class ServiceInfo:
    """Thông tin dịch vụ của chủ tài khoản."""
    name: str
    specialties: str
    strengths: str
    landing_page_note: str


@dataclass
class FilterConfig:
    """Cấu hình lọc bài viết."""
    whitelist_keywords: list = field(default_factory=list)
    blacklist_keywords: list = field(default_factory=list)
    ai_filter_prompt: str = ""
    min_relevance_score: float = 0.7
    max_competitor_comments: int = 8


@dataclass
class CommentConfig:
    """Cấu hình comment."""
    mode: str = "semi_auto"
    ai_model: str = "gpt-4o-mini"
    max_comments_per_day: int = MAX_COMMENTS_PER_DAY
    delay_min_seconds: int = 300
    delay_max_seconds: int = 900
    typing_delay_min_ms: int = 80
    typing_delay_max_ms: int = 350
    typo_probability: float = 0.05


@dataclass
class TelegramConfig:
    """Cấu hình Telegram bot."""
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class OpenAIConfig:
    """Cấu hình OpenAI."""
    api_key: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class DatabaseConfig:
    """Cấu hình Database."""
    path: str = DEFAULT_DB_PATH


@dataclass
class AppConfig:
    """Cấu hình tổng thể ứng dụng."""
    service: ServiceInfo = field(default_factory=lambda: ServiceInfo("", "", "", ""))
    groups: list = field(default_factory=list)
    filter: FilterConfig = field(default_factory=FilterConfig)
    accounts: dict = field(default_factory=dict)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    comment: CommentConfig = field(default_factory=CommentConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
