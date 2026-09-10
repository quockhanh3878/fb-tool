"""
CommHunter (F-Leads) — Nền tảng tự động hóa săn khách hàng và tương tác nhóm Facebook.
"""
__version__ = "1.0.0"

from .models import (
    DiscoveredPost,
    PostStatus,
    CommentStatus,
    AppConfig,
    ServiceInfo,
    GroupConfig,
    FilterConfig,
    CommentConfig,
    TelegramConfig,
    OpenAIConfig,
    DatabaseConfig,
)
from .config_loader import load_config
from .dedup_store import DedupStore, compute_content_hash
from .constants import DEFAULT_DB_PATH, MAX_COMMENTS_PER_DAY

__all__ = [
    "__version__",
    "DiscoveredPost",
    "PostStatus",
    "CommentStatus",
    "AppConfig",
    "ServiceInfo",
    "GroupConfig",
    "FilterConfig",
    "CommentConfig",
    "TelegramConfig",
    "OpenAIConfig",
    "DatabaseConfig",
    "load_config",
    "DedupStore",
    "compute_content_hash",
    "DEFAULT_DB_PATH",
    "MAX_COMMENTS_PER_DAY",
]
