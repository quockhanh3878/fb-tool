"""
Enum dùng chung cho toàn bộ ORM — bám sát Master Plan §3.2.

Lưu trong DB dưới dạng chuỗi (không dùng native ENUM của PostgreSQL) để
thêm giá trị mới không cần migration ALTER TYPE.
"""
from enum import Enum


class StrEnum(str, Enum):
    """Enum serialise thẳng ra chuỗi khi qua Pydantic/JSON."""

    def __str__(self) -> str:  # pragma: no cover - tiện log
        return self.value


class UserTier(StrEnum):
    STARTER = "starter"
    PRO = "pro"
    STUDIO = "studio"


class CampaignMode(StrEnum):
    SEMI_AUTO = "semi_auto"
    FULL_AUTO = "full_auto"


class GroupStatus(StrEnum):
    ACTIVE = "active"
    PENDING_JOIN = "pending_join"
    BLOCKED = "blocked"
    PAUSED = "paused"


class CloneRole(StrEnum):
    SCOUT = "scout"
    SHOOTER = "shooter"
    POSTER = "poster"
    BOTH = "both"
    ALL = "all"


class PublishStatus(StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    PARTIALLY_PUBLISHED = "partially_published"
    FAILED = "failed"
    UNKNOWN_OUTCOME = "unknown_outcome"
    CANCELLED = "cancelled"


class AccountState(StrEnum):
    """7 trạng thái vòng đời clone (Phase 3 §3.1)."""

    ONBOARDING = "onboarding"
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    COOLDOWN = "cooldown"
    CHECKPOINT = "checkpoint"
    BANNED = "banned"
    ROTATING = "rotating"


class AccountTransition(StrEnum):
    COOKIE_VALID = "cookie_valid"
    WARMUP_COMPLETE = "warmup_complete"
    QUOTA_REACHED = "quota_reached"
    RATE_LIMITED = "rate_limited"
    COOLDOWN_EXPIRED = "cooldown_expired"
    CHECKPOINT_DETECTED = "checkpoint_detected"
    VERIFICATION_SUCCESS = "verification_success"
    VERIFICATION_FAILED = "verification_failed"
    ROTATE = "rotate"


class ScriptType(StrEnum):
    SPINTAX = "spintax"
    AI_CONTEXTUAL = "ai_contextual"


class PostStatus(StrEnum):
    NEW = "new"
    NOTIFIED = "notified"
    COMMENTED = "commented"
    NEED_REVIEW = "need_review"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    NOTIFICATION_PENDING = "notification_pending"


class MentionStatus(StrEnum):
    """Hộp thư 'Nhắc tới' — vòng đời một lượt nhắc tên thương hiệu."""

    NEW = "new"
    READ = "read"
    ARCHIVED = "archived"


class LeadStatus(StrEnum):
    """Săn lead qua comment — vòng đời một lượt bình luận khớp từ khoá."""

    NEW = "new"
    READ = "read"
    ARCHIVED = "archived"


class CommentStatus(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SHADOWBANNED = "shadowbanned"
    UNKNOWN_OUTCOME = "unknown_outcome"
    CANCELLED = "cancelled"


class HealthEventType(StrEnum):
    LOGIN_OK = "login_ok"
    CHECKPOINT = "checkpoint"
    COMMENT_BLOCKED = "comment_blocked"
    RATE_LIMITED = "rate_limited"
    BANNED = "banned"
    WARMUP_DONE = "warmup_done"
    STATE_CHANGED = "state_changed"
    PROXY_ROTATED = "proxy_rotated"
    SHADOWBAN = "shadowban"


class SubscriptionPlan(StrEnum):
    STARTER = "starter"
    PRO = "pro"
    STUDIO = "studio"


class PaymentStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


class ProxyStatus(StrEnum):
    AVAILABLE = "available"
    ASSIGNED = "assigned"
    BLACKLISTED = "blacklisted"
    DEAD = "dead"
