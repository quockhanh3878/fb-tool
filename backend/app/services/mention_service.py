# plan: docs/plans/phase2_dashboard_detail.md
"""
Phát hiện bài "nhắc tới" thương hiệu trong lúc Scout quét nhóm.

Chạy SAU khi bài đã được ``pipeline.ingest_raw_posts`` lưu xuống
``discovered_posts`` — file này chỉ so khớp từ khoá thương hiệu với text bài
và ghi bản ghi ``Mention``. Thuần DB, không đụng Playwright nên test offline.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignGroup
from app.models.enums import MentionStatus
from app.models.mention import Mention
from app.models.post import DiscoveredPost
from app.models.user import User
from app.services.ai_service import normalize_vi
from app.services.notification_service import NotificationService
from app.services.pipeline import compute_content_hash


def match_mention_keywords(text: str, keywords: list[str]) -> list[str]:
    """Từ khoá thương hiệu nào xuất hiện trong bài (bỏ dấu, không phân biệt hoa thường)."""
    haystack = normalize_vi(text)
    return [
        keyword
        for keyword in keywords or []
        if keyword and normalize_vi(keyword) in haystack
    ]


async def detect_mentions(
    db: AsyncSession,
    campaign: Campaign,
    group: CampaignGroup | None,
    posts: list[DiscoveredPost],
) -> list[Mention]:
    """Quét danh sách bài mới, tạo ``Mention`` cho bài nhắc tên thương hiệu.

    - ``campaign.mention_keywords`` rỗng → bỏ qua hoàn toàn (tính năng tắt).
    - Dedup theo ``content_hash`` trong cùng chiến dịch (khớp
      ``UniqueConstraint(campaign_id, content_hash)``).

    Không commit — nhánh gọi tự quyết.
    """
    keywords = campaign.mention_keywords or []
    if not keywords:
        return []

    created: list[Mention] = []
    for post in posts:
        matched = match_mention_keywords(post.content_text, keywords)
        if not matched:
            continue

        content_hash = post.content_hash or compute_content_hash(
            post.author_name or "Unknown", post.content_text or ""
        )
        exists = await db.execute(
            select(Mention.id).where(
                Mention.campaign_id == campaign.id,
                Mention.content_hash == content_hash,
            )
        )
        if exists.scalar_one_or_none():
            continue

        mention = Mention(
            campaign_id=campaign.id,
            campaign_group_id=group.id if group is not None else None,
            discovered_post_id=post.id,
            content_hash=content_hash,
            matched_keywords=matched,
            author_name=post.author_name or "",
            content_text=post.content_text or "",
            post_url=post.post_url or "",
            status=MentionStatus.NEW.value,
        )
        db.add(mention)
        created.append(mention)

    await db.flush()
    return created


def mention_summary(campaign_name: str, mentions: list[Mention]) -> str:
    """Thẻ tóm tắt một dòng gửi Telegram (hàm thuần — test offline được)."""
    keywords = sorted({kw for m in mentions for kw in (m.matched_keywords or [])})
    kw_text = ", ".join(keywords) if keywords else "thương hiệu"
    return (
        f"Hộp thư Nhắc tới — chiến dịch {campaign_name}\n"
        f"Có {len(mentions)} bài mới nhắc tới {kw_text}. "
        f"Mở mục Nhắc tới trên dashboard để xem và phản hồi."
    )


async def notify_mentions(
    user: User | None,
    campaign_name: str,
    mentions: list[Mention],
    notifier: NotificationService | None = None,
) -> bool:
    """Bắn Telegram tóm tắt các lượt nhắc mới cho chủ chiến dịch.

    Gọi từ CẢ HAI đường ingest — Beat (``scout_task._scan_one``) và API
    (``POST /api/campaigns/{id}/ingest``) — vì plan yêu cầu cả hai đều báo.
    Không có lượt nhắc mới, hoặc user chưa liên kết Telegram → không làm gì.
    Trả về ``True`` nếu đã gọi ``send_text``.
    """
    if not mentions or user is None or not user.telegram_chat_id:
        return False
    notifier = notifier or NotificationService()
    await notifier.send_text(
        user.telegram_chat_id, mention_summary(campaign_name, mentions)
    )
    return True
