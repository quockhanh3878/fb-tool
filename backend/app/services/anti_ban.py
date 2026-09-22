"""
Anti-Ban Engine (Phase 3 — Task 3.3, 3.4, 3.6).

Ba khối:
  • CheckpointDetector   — 3 lớp phát hiện checkpoint (URL / title / DOM)
  • ShadowbanDetector    — kiểm tra comment có hiển thị với người khác không
  • AdaptiveRateLimiter  — tự giãn/rút delay theo tỉ lệ thành công gần đây

Phần tính toán được tách thành hàm thuần để test offline; phần chạm
Playwright chỉ là lớp vỏ mỏng bọc quanh chúng.
"""
import random
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CommentStatus
from app.models.post import CommentAction

# ── Checkpoint ─────────────────────────────────────────────────────────────
CHECKPOINT_URL_KEYWORDS = ("checkpoint", "login", "recover", "challenge", "confirm_identity")

CHECKPOINT_TITLE_KEYWORDS = (
    "security check",
    "xác minh",
    "xac minh",
    "confirm your identity",
    "xác nhận danh tính",
    "log in",
    "đăng nhập",
    "account restricted",
    "tài khoản bị hạn chế",
)

CHECKPOINT_SELECTORS = (
    '[data-testid="checkpoint"]',
    'form[action*="checkpoint"]',
    '[aria-label*="security check" i]',
    'div:has-text("Your account has been locked")',
    'div:has-text("Tài khoản của bạn đã bị khóa")',
)


@dataclass(frozen=True)
class CheckpointResult:
    type: str  # url_redirect | title_match | dom_element
    evidence: str


def detect_checkpoint_url(url: str) -> CheckpointResult | None:
    """Lớp 1 — URL bị chuyển hướng sang trang xác minh."""
    lowered = (url or "").lower()
    for keyword in CHECKPOINT_URL_KEYWORDS:
        if keyword in lowered:
            return CheckpointResult("url_redirect", url)
    return None


def detect_checkpoint_title(title: str) -> CheckpointResult | None:
    """Lớp 2 — tiêu đề trang là trang xác minh/đăng nhập."""
    lowered = (title or "").lower()
    if not lowered:
        return None
    for keyword in CHECKPOINT_TITLE_KEYWORDS:
        if keyword in lowered:
            return CheckpointResult("title_match", title)
    return None


class CheckpointDetector:
    """Gộp 3 lớp phát hiện trên một Playwright page."""

    async def detect(self, page) -> CheckpointResult | None:
        found = detect_checkpoint_url(getattr(page, "url", ""))
        if found:
            return found

        try:
            title = await page.title()
        except Exception:
            title = ""
        found = detect_checkpoint_title(title)
        if found:
            return found

        for selector in CHECKPOINT_SELECTORS:
            try:
                element = await page.query_selector(selector)
            except Exception:
                continue
            if element:
                return CheckpointResult("dom_element", selector)
        return None


# ── Shadowban ──────────────────────────────────────────────────────────────
def comment_fragment(comment_text: str, length: int = 50) -> str:
    """Lấy đoạn text đại diện để dò comment trên trang (chuẩn hoá khoảng trắng)."""
    normalized = re.sub(r"\s+", " ", (comment_text or "")).strip()
    return normalized[:length]


def is_visible_in_page(page_text: str, comment_text: str) -> bool:
    """So khớp không phân biệt hoa thường + chuẩn hoá khoảng trắng."""
    fragment = comment_fragment(comment_text).lower()
    if not fragment:
        return False
    haystack = re.sub(r"\s+", " ", (page_text or "")).lower()
    return fragment in haystack


class ShadowbanDetector:
    """Mở lại bài viết bằng context KHÁC (Scout/ẩn danh) để soi comment."""

    async def check_comment_visibility(
        self, post_url: str, comment_text: str, verification_context
    ) -> bool:
        page = await verification_context.new_page()
        try:
            await page.goto(post_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            await page.evaluate("window.scrollBy(0, 2000)")
            await page.wait_for_timeout(2000)
            page_text = await page.inner_text("body")
            return is_visible_in_page(page_text, comment_text)
        finally:
            try:
                await page.close()
            except Exception:
                pass


# ── Adaptive Rate Limiter ──────────────────────────────────────────────────
BASE_DELAY_SEC = 600
MIN_DELAY_SEC = 180
MAX_DELAY_SEC = 1800


def compute_delay(
    success_rate: float,
    *,
    base: int = BASE_DELAY_SEC,
    minimum: int = MIN_DELAY_SEC,
    maximum: int = MAX_DELAY_SEC,
    jitter_rng: random.Random | None = None,
) -> int:
    """Tính delay (giây) trước lượt comment kế tiếp từ tỉ lệ thành công 24h qua.

    ≥95% → rút ngắn 20%; ≥80% → giữ nguyên; ≥50% → giãn 1.5×; dưới nữa → kịch trần.
    Kết quả luôn nằm trong [minimum, maximum] kể cả sau khi cộng jitter ±20%.
    """
    if success_rate >= 0.95:
        delay = max(minimum, base * 0.8)
    elif success_rate >= 0.80:
        delay = base
    elif success_rate >= 0.50:
        delay = min(maximum, base * 1.5)
    else:
        delay = maximum

    rng = jitter_rng or random
    delay += delay * rng.uniform(-0.2, 0.2)
    return int(max(minimum, min(maximum, delay)))


def comment_gap_seconds(
    success_rate: float,
    delay_min_seconds: int,
    delay_max_seconds: int,
    rng: random.Random | None = None,
) -> int:
    """Delay giữa 2 comment của MỘT nick theo khoảng khách đặt cho chiến dịch.

    Gốc bốc ngẫu nhiên trong [min, max] của chiến dịch (mặc định 5–15 phút) rồi
    đi qua compute_delay để giãn theo tỉ lệ thành công. Sàn là
    max(MIN_DELAY_SEC, min): không ngắn hơn khoảng khách chọn, không dưới sàn cứng.
    """
    rng = rng or random
    minimum = max(MIN_DELAY_SEC, int(delay_min_seconds or 0))
    upper = max(minimum, int(delay_max_seconds or 0))
    base = int(rng.uniform(minimum, upper))
    return compute_delay(
        success_rate,
        base=base,
        minimum=minimum,
        maximum=max(MAX_DELAY_SEC, upper),
        jitter_rng=rng,
    )


def schedule_jitter_seconds(
    rng: random.Random | None = None, *, min_minutes: int = 5, max_minutes: int = 10
) -> int:
    """Lệch mốc giờ đã đặt (đăng bài lặp lại, bump) 5-10 phút, sớm hoặc trễ ngẫu nhiên.

    Hành vi đúng y hệt mốc chẵn mỗi lần là dấu hiệu máy móc dễ bị soi — dùng
    hàm này để dịch ``scheduled_at``/mốc bump ra khỏi con số tròn.
    """
    rng = rng or random
    magnitude = rng.uniform(min_minutes, max_minutes) * 60
    sign = rng.choice((-1, 1))
    return int(sign * magnitude)


class AdaptiveRateLimiter:
    """Đọc lịch sử comment_actions để quyết định nhịp bắn tiếp theo."""

    def __init__(self, db: AsyncSession, base_delay: int = BASE_DELAY_SEC):
        self.db = db
        self.base_delay = base_delay

    async def recent_actions(self, clone_id: str, hours: int = 24) -> list[CommentAction]:
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        result = await self.db.execute(
            select(CommentAction).where(
                CommentAction.clone_account_id == clone_id,
                CommentAction.executed_at.is_not(None),
                CommentAction.executed_at >= since,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def success_rate(actions: list[CommentAction]) -> float:
        """Chưa có dữ liệu thì coi như 0.85 — đủ tốt để không rút ngắn vội."""
        finished = [
            a
            for a in actions
            if a.status
            in (
                CommentStatus.SUCCESS.value,
                CommentStatus.FAILED.value,
                CommentStatus.SHADOWBANNED.value,
            )
        ]
        if not finished:
            return 0.85
        wins = sum(1 for a in finished if a.status == CommentStatus.SUCCESS.value)
        return wins / len(finished)

    async def next_delay(
        self,
        clone_id: str,
        hours: int = 24,
        *,
        delay_min_seconds: int | None = None,
        delay_max_seconds: int | None = None,
    ) -> int:
        """Có khoảng delay của chiến dịch thì bám khoảng đó, không thì dùng base cố định."""
        actions = await self.recent_actions(clone_id, hours=hours)
        rate = self.success_rate(actions)
        if delay_min_seconds is None or delay_max_seconds is None:
            return compute_delay(rate, base=self.base_delay)
        return comment_gap_seconds(rate, delay_min_seconds, delay_max_seconds)
