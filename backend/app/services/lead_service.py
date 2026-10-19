# plan: docs/plans/phase2_dashboard_detail.md
"""
Săn lead qua comment: quét bình luận dưới bài, so khớp từ khoá
(``Campaign.lead_keywords``) — khác ``mention_service`` ở chỗ so khớp NỘI
DUNG BÌNH LUẬN chứ không phải nội dung bài, và giữ lại danh tính người bình
luận (``author_fb_id`` + ``commented_at``) để anh Ber chủ động liên hệ.

Chạy SAU khi trình duyệt đã bóc comment thô từ một bài (xem
``workers/browser_runtime`` — phần bóc DOM thật cần kiểm chứng trên Chrome
CDP thật trước khi bật, chưa nằm trong file này). File này thuần DB, không
đụng Playwright nên test offline được.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignGroup
from app.models.base import utcnow
from app.models.enums import LeadStatus
from app.models.lead import CommentLead
from app.models.user import User
from app.services.ai_service import normalize_vi
from app.services.notification_service import NotificationService
from app.services.pipeline import compute_content_hash


@dataclass(frozen=True)
class RawComment:
    """Comment thô bóc từ DOM Facebook (hoặc dữ liệu test giả lập)."""

    text: str
    author_name: str = ""
    author_fb_id: str = ""
    fb_comment_id: str = ""
    post_url: str = ""
    comment_url: str = ""
    commented_at: datetime | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "RawComment":
        commented_at = None
        raw_time = raw.get("commentedAt") or raw.get("commented_at")
        if raw_time:
            try:
                commented_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
            except ValueError:
                commented_at = None
        return cls(
            text=(raw.get("text") or "").strip(),
            author_name=(raw.get("author") or raw.get("authorName") or "").strip(),
            author_fb_id=str(raw.get("authorId") or raw.get("author_fb_id") or "").strip(),
            fb_comment_id=str(raw.get("id") or raw.get("fbCommentId") or "").strip(),
            post_url=(raw.get("url") or raw.get("post_url") or "").strip(),
            comment_url=(raw.get("commentUrl") or raw.get("comment_url") or raw.get("commentURL") or "").strip(),
            commented_at=commented_at,
        )


def match_lead_keywords(text: str, keywords: list[str]) -> list[str]:
    """Từ khoá nào xuất hiện trong comment (bỏ dấu, không phân biệt hoa/thường)."""
    haystack = normalize_vi(text)
    return [
        keyword
        for keyword in keywords or []
        if keyword and normalize_vi(keyword) in haystack
    ]


def lead_content_hash(comment: RawComment) -> str:
    """Khoá dedup: ưu tiên fb_comment_id (ổn định, không đổi dù text bị sửa).

    Không có fb_comment_id (bóc DOM thất bại) mới rơi về content_hash theo
    tác giả + text — cùng công thức với mention_service để nhất quán.
    """
    if comment.fb_comment_id:
        return f"fbc:{comment.fb_comment_id}"
    return compute_content_hash(comment.author_fb_id or comment.author_name or "unknown", comment.text)


async def detect_leads(
    db: AsyncSession,
    campaign: Campaign,
    group: CampaignGroup | None,
    raw_comments: list[dict],
    *,
    own_fb_id: str = "",
) -> list[CommentLead]:
    """Quét danh sách comment thô, tạo ``CommentLead`` cho comment khớp từ khoá.

    - ``campaign.lead_keywords`` rỗng → bỏ qua hoàn toàn (tính năng tắt).
    - ``own_fb_id`` khớp ``author_fb_id`` của comment → bỏ qua (không cào
      trúng chính nick đang quét).
    - Dedup theo ``content_hash`` trong CÙNG chiến dịch — comment đã lưu rồi
      thì không tạo lại (khớp ``UniqueConstraint(campaign_id, content_hash)``).

    Không commit — nhánh gọi tự quyết.
    """
    keywords = campaign.lead_keywords or []
    if not keywords:
        return []

    created: list[CommentLead] = []
    for raw in raw_comments:
        comment = raw if isinstance(raw, RawComment) else RawComment.from_dict(raw)
        if not comment.text:
            continue
        if own_fb_id and comment.author_fb_id and comment.author_fb_id == own_fb_id:
            continue

        matched = match_lead_keywords(comment.text, keywords)
        if not matched:
            continue

        content_hash = lead_content_hash(comment)
        exists = await db.execute(
            select(CommentLead.id).where(
                CommentLead.campaign_id == campaign.id,
                CommentLead.content_hash == content_hash,
            )
        )
        if exists.scalar_one_or_none():
            continue

        lead = CommentLead(
            campaign_id=campaign.id,
            campaign_group_id=group.id if group is not None else None,
            fb_comment_id=comment.fb_comment_id,
            content_hash=content_hash,
            matched_keywords=matched,
            author_fb_id=comment.author_fb_id,
            author_name=comment.author_name or "Unknown",
            comment_text=comment.text,
            post_url=comment.post_url,
            comment_url=comment.comment_url,
            commented_at=comment.commented_at,
            status=LeadStatus.NEW.value,
        )
        db.add(lead)
        created.append(lead)

    await db.flush()
    return created


def lead_summary(campaign_name: str, leads: list[CommentLead]) -> str:
    """Thẻ tóm tắt một dòng gửi Telegram (hàm thuần — test offline được)."""
    keywords = sorted({kw for lead in leads for kw in (lead.matched_keywords or [])})
    kw_text = ", ".join(keywords) if keywords else "từ khoá"
    return (
        f"Săn Lead qua Comment — chiến dịch {campaign_name}\n"
        f"Có {len(leads)} người bình luận nhắc {kw_text}. "
        f"Mở mục Săn Lead trên dashboard để xem và liên hệ."
    )


async def notify_leads(
    user: User | None,
    campaign_name: str,
    leads: list[CommentLead],
    notifier: NotificationService | None = None,
    db=None,
) -> bool:
    """Bắn Telegram tóm tắt các lead mới cho chủ chiến dịch.

    Không có lead mới, hoặc user chưa liên kết Telegram → không làm gì.
    Trả về ``True`` nếu đã gọi ``send_text``.
    """
    if not leads or user is None:
        return False
    if db is not None:
        from app.services.outbox_service import queue_text

        from app.services.notification_service import notify_handoff

        notified = False
        if user.telegram_chat_id:
            await queue_text(db, user.telegram_chat_id, lead_summary(campaign_name, leads))
            notified = True

        first_lead = leads[0]
        link = getattr(first_lead, "comment_url", "") or getattr(first_lead, "post_url", "")
        queued = await notify_handoff(
            db,
            user_id=user.id,
            event_type="lead",
            summary=lead_summary(campaign_name, leads),
            source="COMMENT_LEAD",
            occurred_at=utcnow(),
            link=link,
        )
        return notified or queued > 0
    if not user.telegram_chat_id:
        return False
    notifier = notifier or NotificationService()
    await notifier.send_text(
        user.telegram_chat_id, lead_summary(campaign_name, leads)
    )
    return True
