"""Pydantic schemas cho request/response của API."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ───────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=120)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


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
    display_name: str | None = Field(default=None, max_length=120)
    telegram_chat_id: str | None = Field(default=None, max_length=64)


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
    ai_filter_prompt: str = ""
    mention_keywords: list[str] = Field(default_factory=list)
    whitelist_keywords: list[str] = Field(default_factory=list)
    blacklist_keywords: list[str] = Field(default_factory=list)
    min_relevance_score: float = Field(default=0.7, ge=0.0, le=1.0)
    max_competitor_comments: int = Field(default=8, ge=0, le=1000)
    max_comments_per_day: int = Field(default=20, ge=1, le=500)
    delay_min_seconds: int = Field(default=300, ge=30)
    delay_max_seconds: int = Field(default=900, ge=30)

    @field_validator("delay_max_seconds")
    @classmethod
    def check_delay_range(cls, value: int, info):
        minimum = info.data.get("delay_min_seconds")
        if minimum is not None and value < minimum:
            raise ValueError("delay_max_seconds phải >= delay_min_seconds")
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
    ai_filter_prompt: str | None = None
    mention_keywords: list[str] | None = None
    whitelist_keywords: list[str] | None = None
    blacklist_keywords: list[str] | None = None
    min_relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    max_competitor_comments: int | None = Field(default=None, ge=0, le=1000)
    max_comments_per_day: int | None = Field(default=None, ge=1, le=500)
    delay_min_seconds: int | None = Field(default=None, ge=30)
    delay_max_seconds: int | None = Field(default=None, ge=30)


class CampaignOut(ORMModel):
    id: str
    user_id: str
    name: str
    mode: str
    service_name: str
    service_specialties: str
    service_strengths: str
    landing_page_note: str
    ai_filter_prompt: str
    mention_keywords: list[str] = Field(default_factory=list)
    whitelist_keywords: list[str]
    blacklist_keywords: list[str]
    min_relevance_score: float
    max_competitor_comments: int
    is_active: bool
    max_comments_per_day: int
    delay_min_seconds: int
    delay_max_seconds: int
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
    status: str
    error_message: str | None = None
    scheduled_at: datetime | None = None
    executed_at: datetime | None = None


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


class IngestPostsRequest(BaseModel):
    """Scout worker nộp bài thô về API."""

    group_id: str
    posts: list[dict[str, Any]]


class IngestResultOut(BaseModel):
    ingested: int
    evaluated: int
    matched: int
    notified: int
    queued: int
    skipped: int
    mentions: int = 0


class ApplyRequest(BaseModel):
    comment_text: str | None = None
    clone_id: str | None = None


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
    content_template: str = Field(min_length=5)
    media_urls: list[str] = Field(default_factory=list)
    target_groups: list[dict] = Field(min_length=1)
    scheduled_at: datetime | None = None


class PostPublishUpdate(BaseModel):
    clone_account_id: str | None = None
    title: str | None = None
    content_template: str | None = None
    media_urls: list[str] | None = None
    target_groups: list[dict] | None = None
    scheduled_at: datetime | None = None


class PostPublishOut(ORMModel):
    id: str
    campaign_id: str | None = None
    clone_account_id: str | None = None
    title: str
    content_template: str
    media_urls: list[str] = Field(default_factory=list)
    target_groups: list[dict] = Field(default_factory=list)
    status: str
    scheduled_at: datetime | None = None
    published_at: datetime | None = None
    publish_results: list[dict] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime


class PostPublishListOut(BaseModel):
    items: list[PostPublishOut]
    total: int

