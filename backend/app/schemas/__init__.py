"""Pydantic schemas cho request/response của API."""
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.url_policy import facebook_url
from app.services.publishing_defaults import (
    DEFAULT_BUMP_JITTER_ENABLED,
    DEFAULT_BUMP_JITTER_MAX_MINUTES,
    DEFAULT_BUMP_JITTER_MIN_MINUTES,
    DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS,
    DEFAULT_SCHEDULE_TIMEZONE,
    default_bump_hours,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ───────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Mật khẩu tối đa 72 byte UTF-8; không tự cắt mật khẩu")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AppSettingsOut(BaseModel):
    """Màn 'Cài đặt' chế độ desktop — chỉ báo đã cấu hình hay chưa, không trả
    lại giá trị thật (key đã nhập không hiện lại nguyên văn)."""
    openai_api_key_set: bool
    telegram_bot_token_set: bool
    discord_webhook_url_set: bool
    discord_bot_token_set: bool


class AppSettingsUpdate(BaseModel):
    openai_api_key: str | None = Field(default=None, max_length=200)
    telegram_bot_token: str | None = Field(default=None, max_length=200)
    discord_webhook_url: str | None = Field(default=None, max_length=500)
    discord_bot_token: str | None = Field(default=None, max_length=300)


class DiscordLinkCodeOut(BaseModel):
    code: str
    expires_at: datetime


class NotificationRecipientOut(ORMModel):
    id: str
    channel: str
    recipient_id: str
    display_name: str
    event_types: list[str] = Field(default_factory=list)
    source: str
    verified_at: datetime | None = None
    is_active: bool


class NotificationRecipientCreate(BaseModel):
    channel: Literal["discord_webhook", "discord_dm"]
    recipient_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(default="", max_length=120)
    event_types: list[str] = Field(default_factory=lambda: ["lead", "customer_reply", "post_author_reply", "error"])


class NotificationRecipientUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    event_types: list[str] | None = None
    is_active: bool | None = None


class JobStatusOut(BaseModel):
    job_name: str
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)


class SubscriptionOut(ORMModel):
    plan: str
    max_groups: int
    max_clones: int
    max_comments_per_day: int
    ai_comments_enabled: bool
    bump_enabled: bool
    payment_status: str
    expires_at: datetime | None = None


class UserOut(ORMModel):
    id: str
    email: str
    display_name: str
    telegram_chat_id: str | None = None
    tier: str
    is_admin: bool
    created_at: datetime
    subscription: SubscriptionOut | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, max_length=120)
    telegram_chat_id: None = None


class TelegramLinkOut(BaseModel):
    link_code: str
    instructions: str


# ── Campaign ───────────────────────────────────────────────────────────────
class CampaignBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    mode: Literal["semi_auto", "full_auto"] = "semi_auto"
    service_name: str = ""
    service_specialties: str = ""
    service_strengths: str = ""
    landing_page_note: str = ""
    ai_comments_enabled: bool = False
    ai_filter_prompt: str = ""
    mention_keywords: list[str] = Field(default_factory=list)
    lead_keywords: list[str] = Field(default_factory=list)
    whitelist_keywords: list[str] = Field(default_factory=list)
    blacklist_keywords: list[str] = Field(default_factory=list)
    min_relevance_score: float = Field(default=0.7, ge=0.0, le=1.0)
    review_floor: float = Field(default=0.5, ge=0.0, le=1.0)
    max_competitor_comments: int = Field(default=8, ge=0, le=1000)
    max_comments_per_day: int = Field(default=20, ge=1, le=500)
    delay_min_seconds: int = Field(default=300, ge=30)
    delay_max_seconds: int = Field(default=900, ge=30)
    publish_repeat_interval_days: int = Field(
        default=DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS, ge=1, le=365
    )
    publish_auto_bump: bool = True
    publish_bump_hours: list[int] = Field(default_factory=default_bump_hours)
    schedule_timezone: str = Field(default=DEFAULT_SCHEDULE_TIMEZONE, min_length=1, max_length=64)
    bump_jitter_enabled: bool = DEFAULT_BUMP_JITTER_ENABLED
    bump_jitter_min_minutes: int = Field(
        default=DEFAULT_BUMP_JITTER_MIN_MINUTES, ge=0, le=120
    )
    bump_jitter_max_minutes: int = Field(
        default=DEFAULT_BUMP_JITTER_MAX_MINUTES, ge=0, le=120
    )

    @field_validator("delay_max_seconds")
    @classmethod
    def check_delay_range(cls, value: int, info):
        minimum = info.data.get("delay_min_seconds")
        if minimum is not None and value < minimum:
            raise ValueError("delay_max_seconds phải >= delay_min_seconds")
        return value

    @field_validator("publish_bump_hours")
    @classmethod
    def check_publish_bump_hours(cls, value: list[int]) -> list[int]:
        if len(value) > 24 or any(type(hour) is not int or not 0 <= hour <= 23 for hour in value):
            raise ValueError("publish_bump_hours must contain hours from 0 to 23")
        return sorted(set(value))

    @field_validator("schedule_timezone")
    @classmethod
    def check_schedule_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("schedule_timezone must be a valid IANA timezone") from exc
        return value

    @field_validator("bump_jitter_max_minutes")
    @classmethod
    def check_bump_jitter_range(cls, value: int, info):
        minimum = info.data.get("bump_jitter_min_minutes")
        if minimum is not None and value < minimum:
            raise ValueError("bump_jitter_max_minutes must be >= bump_jitter_min_minutes")
        return value


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    mode: Literal["semi_auto", "full_auto"] | None = None
    service_name: str | None = None
    service_specialties: str | None = None
    service_strengths: str | None = None
    landing_page_note: str | None = None
    ai_comments_enabled: bool | None = None
    ai_filter_prompt: str | None = None
    mention_keywords: list[str] | None = None
    lead_keywords: list[str] | None = None
    whitelist_keywords: list[str] | None = None
    blacklist_keywords: list[str] | None = None
    min_relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    review_floor: float | None = Field(default=None, ge=0.0, le=1.0)
    max_competitor_comments: int | None = Field(default=None, ge=0, le=1000)
    publish_repeat_interval_days: int | None = Field(default=None, ge=1, le=365)
    publish_auto_bump: bool | None = None
    publish_bump_hours: list[int] | None = None
    schedule_timezone: str | None = Field(default=None, min_length=1, max_length=64)
    bump_jitter_enabled: bool | None = None
    bump_jitter_min_minutes: int | None = Field(default=None, ge=0, le=120)
    bump_jitter_max_minutes: int | None = Field(default=None, ge=0, le=120)
    max_comments_per_day: int | None = Field(default=None, ge=1, le=500)
    delay_min_seconds: int | None = Field(default=None, ge=30)
    delay_max_seconds: int | None = Field(default=None, ge=30)

    @field_validator("publish_bump_hours")
    @classmethod
    def check_update_publish_bump_hours(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if len(value) > 24 or any(type(hour) is not int or not 0 <= hour <= 23 for hour in value):
            raise ValueError("publish_bump_hours must contain hours from 0 to 23")
        return sorted(set(value))

    @field_validator("schedule_timezone")
    @classmethod
    def check_update_schedule_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("schedule_timezone must be a valid IANA timezone") from exc
        return value


class CampaignOut(ORMModel):
    id: str
    user_id: str
    name: str
    mode: str
    service_name: str
    service_specialties: str
    service_strengths: str
    landing_page_note: str
    ai_comments_enabled: bool
    ai_filter_prompt: str
    mention_keywords: list[str] = Field(default_factory=list)
    lead_keywords: list[str] = Field(default_factory=list)
    whitelist_keywords: list[str]
    blacklist_keywords: list[str]
    min_relevance_score: float
    review_floor: float
    max_competitor_comments: int
    is_active: bool
    max_comments_per_day: int
    delay_min_seconds: int
    delay_max_seconds: int
    publish_repeat_interval_days: int
    publish_auto_bump: bool
    publish_bump_hours: list[int] = Field(default_factory=list)
    schedule_timezone: str
    bump_jitter_enabled: bool
    bump_jitter_min_minutes: int
    bump_jitter_max_minutes: int
    created_at: datetime


# ── Group ──────────────────────────────────────────────────────────────────
class GroupCreate(BaseModel):
    group_url: str = Field(min_length=3, max_length=500)
    group_name: str = Field(default="", max_length=200)
    scan_interval_minutes: int = Field(default=10, ge=3, le=1440)


class GroupUpdate(BaseModel):
    group_name: str | None = Field(default=None, max_length=200)
    scan_interval_minutes: int | None = Field(default=None, ge=3, le=1440)
    status: Literal["active", "pending_join", "blocked", "paused"] | None = None


class GroupOut(ORMModel):
    id: str
    campaign_id: str
    group_url: str
    group_key: str
    group_name: str
    status: str
    scan_interval_minutes: int
    last_scanned_at: datetime | None = None


class GroupDiscoverOut(BaseModel):
    queued: bool
    message: str


# ── Script ─────────────────────────────────────────────────────────────────
class ScriptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    type: Literal["spintax", "ai_contextual"] = "spintax"
    template_content: str = ""
    ai_system_prompt: str = ""
    attached_media_urls: list[str] = Field(default_factory=list)
    is_default: bool = False
    is_active: bool = True


class ScriptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    type: Literal["spintax", "ai_contextual"] | None = None
    template_content: str | None = None
    ai_system_prompt: str | None = None
    attached_media_urls: list[str] | None = None
    is_default: bool | None = None
    is_active: bool | None = None


class ScriptOut(ORMModel):
    id: str
    campaign_id: str
    name: str
    type: str
    template_content: str
    ai_system_prompt: str
    attached_media_urls: list[str]
    is_default: bool
    is_active: bool = True
    usage_count: int = 0
    last_used_at: datetime | None = None


class ScriptPreviewOut(BaseModel):
    variants: list[str]
    total_variants: int


class LintIssue(BaseModel):
    level: Literal["error", "warning"]
    message: str


class LintRequest(BaseModel):
    """Soi một mẫu spintax CHƯA lưu — dùng cho ô soạn thảo trực tiếp."""

    template_content: str = Field(default="", max_length=8000)
    sample_count: int = Field(default=5, ge=1, le=20)


class LintOut(BaseModel):
    ok: bool
    total_variants: int
    group_count: int
    shortest_words: int
    longest_words: int
    issues: list[LintIssue]
    samples: list[str]
    # Số ngày chạy được mà chưa phải lặp lại câu nào, tính theo trần comment/ngày.
    days_without_repeat: float = 0.0


class ExpandOut(BaseModel):
    """Toàn bộ biến thể (có thể bị cắt bớt nếu mẫu quá lớn)."""

    variants: list[str]
    total_variants: int
    truncated: bool


# ── Clone ──────────────────────────────────────────────────────────────────
class CloneCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["scout", "shooter", "poster", "both", "all"] = "shooter"
    proxy_address: str | None = Field(default=None, max_length=255)
    daily_comment_limit: int = Field(default=20, ge=1, le=200)
    daily_post_limit: int = Field(default=5, ge=1, le=50)
    is_backup: bool = False


class CloneUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Literal["scout", "shooter", "poster", "both", "all"] | None = None
    proxy_address: str | None = Field(default=None, max_length=255)
    daily_comment_limit: int | None = Field(default=None, ge=1, le=200)
    daily_post_limit: int | None = Field(default=None, ge=1, le=50)
    is_backup: bool | None = None


class CloneOut(ORMModel):
    id: str
    display_name: str
    role: str
    status: str
    proxy_address: str | None = None
    daily_comment_count: int
    daily_comment_limit: int
    daily_post_count: int = 0
    daily_post_limit: int = 5
    warmup_day: int
    consecutive_failures: int
    is_backup: bool
    has_cookies: bool = False
    last_activity_at: datetime | None = None
    cooldown_until: datetime | None = None
    created_at: datetime


class CookieUploadOut(BaseModel):
    cookie_count: int
    cookie_names: list[str]
    fb_user_id: str
    status: str
    # Hạn dùng cookie phiên — None nghĩa là file không mang hạn (cookie phiên).
    expires_at: datetime | None = None
    days_left: float | None = None


class TransitionRequest(BaseModel):
    event: str
    details: str = ""


# ── Post & Action ──────────────────────────────────────────────────────────
class CommentActionOut(ORMModel):
    id: str
    comment_content: str
    fb_comment_id: str = ""
    comment_url: str = ""
    status: str
    error_message: str | None = None
    scheduled_at: datetime | None = None
    executed_at: datetime | None = None


class CommentHistoryOut(BaseModel):
    id: str
    discovered_post_id: str
    post_url: str
    comment_content: str
    fb_comment_id: str = ""
    comment_url: str = ""
    status: str
    error_message: str | None = None
    scheduled_at: datetime | None = None
    executed_at: datetime | None = None


class CommentHistoryListOut(BaseModel):
    items: list[CommentHistoryOut]
    total: int
    limit: int
    offset: int


class PostOut(ORMModel):
    id: str
    campaign_id: str
    campaign_group_id: str | None = None
    post_url: str
    post_id_fb: str
    author_name: str
    content_text: str
    existing_comment_count: int
    ai_relevance_score: float
    ai_reason: str
    ai_extracted: dict[str, Any]
    status: str
    discovered_at: datetime
    notified_at: datetime | None = None
    commented_at: datetime | None = None


class PostListOut(BaseModel):
    items: list[PostOut]
    total: int
    limit: int
    offset: int


class RawPostInput(BaseModel):
    author: str = Field(default="Unknown", max_length=160)
    text: str = Field(min_length=1, max_length=20000)
    url: str
    commentCount: int = Field(default=0, ge=0, le=10000000)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        return facebook_url(value)


class RawCommentInput(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    author: str = Field(default="", max_length=160, validation_alias=AliasChoices("author", "authorName"))
    author_fb_id: str = Field(default="", max_length=32, validation_alias=AliasChoices("authorId", "author_fb_id", "authorFbId"))
    fbCommentId: str = Field(default="", max_length=64, validation_alias=AliasChoices("id", "fbCommentId", "fb_comment_id"))
    post_url: str = Field(default="", max_length=500, validation_alias=AliasChoices("url", "post_url", "postUrl"))
    comment_url: str = Field(default="", max_length=500, validation_alias=AliasChoices("commentUrl", "comment_url", "commentURL"))
    commentedAt: datetime | None = Field(default=None, validation_alias=AliasChoices("commentedAt", "commented_at"))

    @field_validator("post_url")
    @classmethod
    def validate_url(cls, value):
        return facebook_url(value) if value else ""

    @field_validator("comment_url")
    @classmethod
    def validate_comment_url(cls, value):
        return facebook_url(value) if value else ""


class IngestPostsRequest(BaseModel):
    """Scout worker nộp bài thô về API."""

    group_id: str
    posts: list[dict[str, Any]] = Field(min_length=1, max_length=100)

    @field_validator("posts")
    @classmethod
    def validate_posts(cls, value):
        return [RawPostInput.model_validate(item).model_dump() for item in value]


class IngestResultOut(BaseModel):
    ingested: int
    evaluated: int
    matched: int
    notified: int
    queued: int
    skipped: int
    mentions: int = 0


class IngestCommentsRequest(BaseModel):
    """Nộp comment thô bóc dưới một bài để săn lead qua từ khoá."""

    group_id: str | None = None
    clone_id: str | None = None
    comments: list[dict[str, Any]] = Field(min_length=1, max_length=200)

    @field_validator("comments")
    @classmethod
    def validate_comments(cls, value):
        return [RawCommentInput.model_validate(item).model_dump(mode="json") for item in value]


class IngestCommentsResultOut(BaseModel):
    ingested: int
    leads: int


class ApplyRequest(BaseModel):
    comment_text: str | None = Field(default=None, max_length=5000)
    clone_id: str | None = Field(default=None, min_length=32, max_length=32)


# ── Săn lead qua comment ─────────────────────────────────────────────────
class LeadOut(ORMModel):
    id: str
    campaign_id: str
    campaign_group_id: str | None = None
    fb_comment_id: str = ""
    matched_keywords: list[str] = Field(default_factory=list)
    author_fb_id: str = ""
    author_name: str
    comment_text: str
    post_url: str
    comment_url: str = ""
    status: str
    commented_at: datetime | None = None
    discovered_at: datetime
    seen_at: datetime | None = None


class LeadListOut(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int


class LeadUnreadOut(BaseModel):
    count: int


# ── Hộp thư "Nhắc tới" ─────────────────────────────────────────────────────
class MentionOut(ORMModel):
    id: str
    campaign_id: str
    campaign_group_id: str | None = None
    discovered_post_id: str | None = None
    matched_keywords: list[str] = Field(default_factory=list)
    author_name: str
    content_text: str
    post_url: str
    status: str
    discovered_at: datetime
    seen_at: datetime | None = None


class MentionListOut(BaseModel):
    items: list[MentionOut]
    total: int
    limit: int
    offset: int


class MentionUnreadOut(BaseModel):
    count: int


# ── Bump ───────────────────────────────────────────────────────────────────
class BumpCreate(BaseModel):
    target_post_url: str = Field(min_length=5, max_length=500)
    cron_schedule: list[int] = Field(default_factory=list)
    bump_messages: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("cron_schedule")
    @classmethod
    def check_hours(cls, value: list[int]) -> list[int]:
        for hour in value:
            if not 0 <= int(hour) <= 23:
                raise ValueError("Khung giờ bump phải nằm trong 0..23")
        return [int(h) for h in value]


class BumpUpdate(BaseModel):
    target_post_url: str | None = Field(default=None, min_length=5, max_length=500)
    cron_schedule: list[int] | None = None
    bump_messages: list[str] | None = None
    is_active: bool | None = None


class BumpOut(ORMModel):
    id: str
    campaign_id: str
    target_post_url: str
    cron_schedule: list[int]
    bump_messages: list[str]
    is_active: bool
    last_bumped_at: datetime | None = None


# ── Stats & Health ─────────────────────────────────────────────────────────
class DailyPoint(BaseModel):
    date: str
    posts: int
    matched: int
    comments: int


class DashboardStats(BaseModel):
    posts_today: int
    matched_today: int
    comments_today: int
    success_rate: float
    active_campaigns: int
    total_groups: int
    clones_healthy: int
    clones_total: int
    trend: list[DailyPoint]


class GroupPerformance(BaseModel):
    group_id: str
    group_name: str
    posts: int
    matched: int
    match_rate: float


class CloneHealthOut(BaseModel):
    id: str
    display_name: str
    status: str
    daily_comment_count: int
    daily_comment_limit: int
    consecutive_failures: int
    warmup: dict[str, Any]
    cooldown_until: datetime | None = None
    proxy_address: str | None = None


class CloneIssueOut(BaseModel):
    code: str
    severity: Literal["critical", "warning", "info"]
    message: str
    hint: str


class CloneDiagnosisOut(BaseModel):
    """Phiếu chẩn đoán một clone (xem services/account_check.py)."""

    clone_id: str
    display_name: str
    status: str
    score: int
    grade: Literal["good", "warn", "bad"]
    ready: bool
    cookie_ok: bool
    cookie_expires_at: datetime | None = None
    cookie_days_left: float | None = None
    daily_comment_count: int
    daily_comment_limit: int
    consecutive_failures: int
    proxy_address: str | None = None
    issues: list[CloneIssueOut]
    checked_at: datetime


class IssueDigestOut(CloneIssueOut):
    """Vấn đề đã gộp: cùng một `code` xảy ra ở bao nhiêu clone."""

    count: int


class HealthSummaryOut(BaseModel):
    clone_count: int
    ready_count: int
    average_score: int
    grade: Literal["good", "warn", "bad"]
    critical_count: int
    warning_count: int
    # Năng lực comment hôm nay, chỉ tính clone thực sự sẵn sàng.
    capacity_used: int
    capacity_total: int
    capacity_left: int
    top_issues: list[IssueDigestOut]
    unacknowledged_alerts: int = 0


class CheckAllOut(BaseModel):
    """Kết quả nút «Kiểm tra tất cả»: đã sửa trạng thái clone nào, còn lại ra sao."""

    summary: HealthSummaryOut
    reports: list[CloneDiagnosisOut]
    transitioned: list[str]


class HealthEventOut(ORMModel):
    id: str
    clone_account_id: str
    event_type: str
    details: str
    from_state: str | None = None
    to_state: str | None = None
    created_at: datetime


class ProxyCreate(BaseModel):
    address: str = Field(min_length=5, max_length=255)
    type: str = "residential"
    country: str = "VN"


class ProxyOut(ORMModel):
    id: str
    address: str
    type: str
    country: str
    status: str
    assigned_to_clone_id: str | None = None
    is_healthy: bool
    last_health_check: datetime | None = None


# ── Post Publishing ────────────────────────────────────────────────────────
class PostPublishCreate(BaseModel):
    campaign_id: str | None = None
    clone_account_id: str | None = None
    title: str = Field(default="", max_length=200)
    content_template: str = Field(min_length=5, max_length=20000)
    media_urls: list[str] = Field(default_factory=list, max_length=10)
    target_groups: list[dict] = Field(min_length=1, max_length=50)
    repeat_interval_days: int | None = Field(default=None, ge=1, le=365)
    auto_bump: bool | None = None
    bump_hours: list[int] | None = None
    scheduled_at: datetime | None = None

    @field_validator("target_groups")
    @classmethod
    def validate_targets(cls, value):
        return [PublishTarget.model_validate(item).model_dump() for item in value]

    @field_validator("bump_hours")
    @classmethod
    def validate_hours(cls, value):
        if value is None:
            return value
        if len(value) > 24 or any(type(hour) is not int or not 0 <= hour <= 23 for hour in value):
            raise ValueError("bump_hours must contain hours from 0 to 23")
        return sorted(set(value))

    @field_validator("media_urls")
    @classmethod
    def validate_media_urls(cls, value: list[str]) -> list[str]:
        if any(not item.startswith("media://") for item in value):
            raise ValueError("media_urls must reference uploaded media assets")
        return value


class PublishTarget(BaseModel):
    group_url: str
    group_id: str = Field(default="", max_length=64)
    group_name: str = Field(default="", max_length=200)

    @field_validator("group_url")
    @classmethod
    def validate_url(cls, value):
        return facebook_url(value, group=True)


class PostPublishUpdate(BaseModel):
    clone_account_id: str | None = None
    title: str | None = None
    content_template: str | None = None
    media_urls: list[str] | None = None
    target_groups: list[dict] | None = None
    repeat_interval_days: int | None = None
    auto_bump: bool | None = None
    bump_hours: list[int] | None = None
    scheduled_at: datetime | None = None

    @field_validator("media_urls")
    @classmethod
    def validate_update_media_urls(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not item.startswith("media://") for item in value):
            raise ValueError("media_urls must reference uploaded media assets")
        return value


class PublishingMediaOut(ORMModel):
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    reference: str
    created_at: datetime


class PostPublishOut(ORMModel):
    id: str
    campaign_id: str | None = None
    clone_account_id: str | None = None
    title: str
    content_template: str
    media_urls: list[str] = Field(default_factory=list)
    target_groups: list[dict] = Field(default_factory=list)
    status: str
    repeat_interval_days: int | None = 14
    auto_bump: bool = True
    bump_hours: list[int] = Field(default_factory=default_bump_hours)
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    publish_results: list[dict] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime


class PostPublishListOut(BaseModel):
    items: list[PostPublishOut]
    total: int


class PostPublishHistoryOut(ORMModel):
    id: str
    post_publish_id: str | None = None
    campaign_id: str | None = None
    clone_account_id: str | None = None
    group_id: str
    group_name: str
    group_url: str
    post_url: str
    status: str
    error_message: str | None = None
    content_snapshot: str
    published_at: datetime | None = None
    created_at: datetime


class PostPublishHistoryListOut(BaseModel):
    items: list[PostPublishHistoryOut]
    total: int
    limit: int
    offset: int
