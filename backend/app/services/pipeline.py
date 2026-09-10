"""
Pipeline xử lý bài viết (bản Phase 2, multi-tenant).

Giữ nguyên THỨ TỰ đã chứng minh ở Phase 1 — cái rẻ chặn trước cái đắt:

    dedup (hash)  →  từ khoá (miễn phí)  →  AI chấm điểm (tốn tiền)
        →  anti-crowding  →  semi_auto: bắn Telegram | full_auto: xếp hàng comment

Hàm ở đây nhận sẵn session DB nên dùng được cả từ router (thao tác tay của
người dùng) lẫn từ Celery worker (chạy nền).
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.campaign import Campaign, CampaignGroup, CommentScript
from app.models.enums import CampaignMode, CommentStatus, PostStatus, ScriptType
from app.models.post import CommentAction, DiscoveredPost
from app.models.user import User
from app.services.ai_service import AIService, keyword_match
from app.services.script_engine import (
    ScriptError,
    render_unique,
    validate_comment,
)


def compute_content_hash(author: str, text: str) -> str:
    """Cùng công thức với Phase 1 để DB cũ và mới khớp nhau."""
    return hashlib.md5(f"{author}:{text[:200]}".encode("utf-8")).hexdigest()


async def ingest_raw_posts(
    db: AsyncSession,
    campaign: Campaign,
    group: CampaignGroup,
    raw_posts: list[dict],
) -> list[DiscoveredPost]:
    """Lưu bài Scout vừa quét, bỏ bài đã thấy trong CÙNG chiến dịch.

    raw_posts là dữ liệu thô từ EXTRACT_POST_JS:
        {"author", "text", "url", "commentCount"}
    """
    from app.services.facebook_utils import extract_post_id

    fresh: list[DiscoveredPost] = []
    for raw in raw_posts:
        text = (raw.get("text") or "").strip()
        if len(text) < 20:
            continue
        author = raw.get("author") or "Unknown"
        content_hash = compute_content_hash(author, text)

        exists = await db.execute(
            select(DiscoveredPost.id).where(
                DiscoveredPost.campaign_id == campaign.id,
                DiscoveredPost.content_hash == content_hash,
            )
        )
        if exists.scalar_one_or_none():
            continue

        post = DiscoveredPost(
            campaign_id=campaign.id,
            campaign_group_id=group.id,
            content_hash=content_hash,
            post_id_fb=extract_post_id(raw.get("url") or ""),
            post_url=raw.get("url") or "",
            author_name=author,
            content_text=text,
            existing_comment_count=int(raw.get("commentCount") or 0),
            status=PostStatus.NEW.value,
        )
        db.add(post)
        fresh.append(post)

    group.last_scanned_at = utcnow()
    await db.flush()
    return fresh


async def evaluate_post(
    db: AsyncSession,
    campaign: Campaign,
    post: DiscoveredPost,
    ai: AIService,
) -> tuple[bool, str]:
    """Chấm điểm 1 bài. Trả về (đạt, lý_do). Bài trượt bị đánh dấu skipped."""
    passed, reason = keyword_match(
        post.content_text,
        campaign.whitelist_keywords or [],
        campaign.blacklist_keywords or [],
    )
    if not passed:
        post.status = PostStatus.SKIPPED.value
        post.ai_reason = reason
        return False, reason

    result = await ai.filter_post(post.content_text, campaign)
    try:
        score = float(result.get("relevance_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0.0

    post.ai_relevance_score = score
    post.ai_reason = str(result.get("reason", ""))
    post.ai_extracted = result.get("extracted") or {}

    if score < float(campaign.min_relevance_score or 0.7):
        post.status = PostStatus.SKIPPED.value
        return False, f"low_score:{score:.2f}"

    if post.existing_comment_count > int(campaign.max_competitor_comments or 8):
        post.status = PostStatus.SKIPPED.value
        post.ai_reason = f"too_competitive:{post.existing_comment_count}"
        return False, post.ai_reason

    return True, ""


async def count_today_actions(db: AsyncSession, campaign_id: str) -> int:
    """Đếm LƯỢT thao tác hôm nay (kể cả thất bại) — quota tính theo lượt.

    Đếm theo lượt thay vì theo comment thành công là bài học Phase 1 (N-04):
    nếu chỉ đếm thành công, một clone đang bị chặn sẽ thử lại vô hạn.
    """
    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count(CommentAction.id))
        .join(DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id)
        .where(
            DiscoveredPost.campaign_id == campaign_id,
            CommentAction.executed_at.is_not(None),
            CommentAction.executed_at >= start_of_day,
        )
    )
    return int(result.scalar_one() or 0)


# Số comment gần nhất được dùng làm "bộ nhớ chống lặp". 30 là đủ: quá ít thì
# lặp lộ liễu, quá nhiều thì mẫu nghèo biến thể sẽ không còn câu nào hợp lệ.
RECENT_COMMENT_WINDOW = 30


async def recent_comment_texts(
    db: AsyncSession, campaign_id: str, limit: int = RECENT_COMMENT_WINDOW
) -> list[str]:
    """Lấy các comment gần đây NHẤT của chiến dịch để tránh nói lại y hệt.

    Tính cả lượt đang xếp hàng chứ không chỉ lượt đã gửi — nếu không, hai bài
    duyệt liền nhau sẽ nhận cùng một câu.
    """
    result = await db.execute(
        select(CommentAction.comment_content)
        .join(DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id)
        .where(DiscoveredPost.campaign_id == campaign_id)
        .order_by(CommentAction.created_at.desc())
        .limit(limit)
    )
    return [text for text in result.scalars().all() if text]


async def pick_script(db: AsyncSession, campaign_id: str) -> CommentScript | None:
    """Chọn kịch bản theo lối XOAY VÒNG, không bám mãi một cái.

    Thứ tự ưu tiên: ít dùng nhất → lâu chưa dùng nhất → mặc định → cũ nhất.
    Nhờ vậy khách tạo 3 kịch bản thì cả 3 đều được dùng đều tay, thay vì
    kịch bản mặc định gánh 100% còn hai cái kia nằm không.
    """
    result = await db.execute(
        select(CommentScript)
        .where(
            CommentScript.campaign_id == campaign_id,
            CommentScript.is_active.is_(True),
        )
        .order_by(
            CommentScript.usage_count.asc(),
            CommentScript.last_used_at.asc().nulls_first(),
            CommentScript.is_default.desc(),
            CommentScript.created_at.asc(),
        )
    )
    script = result.scalars().first()
    if script is not None:
        return script

    # Không còn kịch bản nào đang bật: rơi về mặc định để chiến dịch vẫn chạy.
    fallback = await db.execute(
        select(CommentScript)
        .where(CommentScript.campaign_id == campaign_id)
        .order_by(CommentScript.is_default.desc(), CommentScript.created_at.asc())
    )
    return fallback.scalars().first()


def mark_script_used(script: CommentScript | None) -> None:
    """Ghi nhận một lượt dùng để vòng xoay nhích sang kịch bản kế tiếp."""
    if script is None:
        return
    script.usage_count = (script.usage_count or 0) + 1
    script.last_used_at = utcnow()


async def build_comment(
    db: AsyncSession, campaign: Campaign, post: DiscoveredPost, ai: AIService
) -> tuple[str, CommentScript | None]:
    """Sinh nội dung comment theo kịch bản mặc định của chiến dịch.

    Kịch bản spintax không tốn tiền AI; ai_contextual thì gọi AI. Cả hai đều
    đi qua validate_comment() nên comment chứa link không bao giờ lọt xuống
    hàng đợi.
    """
    script = await pick_script(db, campaign.id)
    used = await recent_comment_texts(db, campaign.id)

    if script is not None and script.type == ScriptType.SPINTAX.value:
        try:
            text = validate_comment(render_unique(script.template_content, used))
            mark_script_used(script)
            return text, script
        except ScriptError:
            # Kịch bản hỏng thì rơi sang AI thay vì bỏ lỡ khách hàng tiềm năng.
            pass

    text = await ai.generate_comment(post.content_text, campaign, post.ai_extracted or {})
    if not text:
        return "", script
    try:
        cleaned = validate_comment(text)
    except ScriptError:
        return "", script

    mark_script_used(script)
    return cleaned, script


async def queue_comment(
    db: AsyncSession,
    campaign: Campaign,
    post: DiscoveredPost,
    comment_text: str,
    script: CommentScript | None = None,
    clone_id: str | None = None,
    scheduled_at: datetime | None = None,
) -> CommentAction:
    """Đưa 1 lượt comment vào hàng đợi (status=queued)."""
    action = CommentAction(
        discovered_post_id=post.id,
        clone_account_id=clone_id,
        comment_script_id=script.id if script else None,
        comment_content=comment_text,
        status=CommentStatus.QUEUED.value,
        scheduled_at=scheduled_at or utcnow(),
    )
    db.add(action)
    await db.flush()
    return action


async def process_campaign_posts(
    db: AsyncSession,
    campaign: Campaign,
    posts: list[DiscoveredPost],
    ai: AIService,
    notifier=None,
    user: User | None = None,
) -> dict:
    """Chạy hết pipeline cho danh sách bài mới. Trả về thống kê tóm tắt."""
    stats = {"evaluated": 0, "matched": 0, "notified": 0, "queued": 0, "skipped": 0}
    quota = int(campaign.max_comments_per_day or 20)
    used = await count_today_actions(db, campaign.id)

    for post in posts:
        stats["evaluated"] += 1
        ok, _reason = await evaluate_post(db, campaign, post, ai)
        if not ok:
            stats["skipped"] += 1
            continue

        stats["matched"] += 1

        if campaign.mode == CampaignMode.SEMI_AUTO.value:
            post.status = PostStatus.NOTIFIED.value
            post.notified_at = utcnow()
            stats["notified"] += 1
            if notifier is not None and user is not None and user.telegram_chat_id:
                await notifier.send_post_notification(
                    user.telegram_chat_id, post, campaign.name
                )
            continue

        # full_auto
        if used >= quota:
            post.status = PostStatus.SKIPPED.value
            post.ai_reason = f"quota_reached:{used}/{quota}"
            stats["skipped"] += 1
            continue

        comment_text, script = await build_comment(db, campaign, post, ai)
        if not comment_text:
            post.status = PostStatus.SKIPPED.value
            post.ai_reason = "khong_sinh_duoc_comment"
            stats["skipped"] += 1
            continue

        await queue_comment(db, campaign, post, comment_text, script)
        used += 1
        stats["queued"] += 1

    await db.flush()
    return stats
