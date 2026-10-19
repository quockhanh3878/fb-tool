# plan: docs/plans/community_job_runner_plan.md
"""Filter and persist read-only PAGE_MONITOR observations."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import as_utc, utcnow
from app.models.interaction import PageInteraction
from app.models.post import CommentAction
from app.services.notification_service import notify_handoff

CUSTOMER_REPLY = "customer_reply"
POST_AUTHOR_REPLY = "post_author_reply"
PAGE_MONITOR_SOURCE = "PAGE_MONITOR"


@dataclass(frozen=True)
class InteractionCandidate:
    fb_comment_id: str
    parent_fb_comment_id: str
    author_fb_id: str
    author_name: str
    comment_text: str
    post_url: str
    comment_url: str
    commented_at: datetime
    event_type: str

    @classmethod
    def from_dict(cls, raw: dict, *, own_comment_ids: set[str]) -> "InteractionCandidate | None":
        comment_id = str(raw.get("id") or raw.get("fbCommentId") or "").strip()
        author_id = str(
            raw.get("authorId") or raw.get("author_fb_id") or raw.get("author_id") or ""
        ).strip()
        post_url = str(raw.get("post_url") or raw.get("url") or "").strip()
        comment_url = str(raw.get("commentUrl") or raw.get("comment_url") or "").strip()
        text = str(raw.get("text") or "").strip()
        if not comment_id or not post_url or not text:
            return None
        raw_time = raw.get("commentedAt") or raw.get("commented_at")
        try:
            commented_at = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if commented_at.tzinfo is None:
            commented_at = commented_at.replace(tzinfo=timezone.utc)
        parent_id = str(raw.get("parentCommentId") or raw.get("parent_comment_id") or "").strip()
        event_type = CUSTOMER_REPLY if parent_id and parent_id in own_comment_ids else POST_AUTHOR_REPLY
        return cls(
            fb_comment_id=comment_id,
            parent_fb_comment_id=parent_id,
            author_fb_id=author_id,
            author_name=str(raw.get("author") or raw.get("authorName") or "").strip(),
            comment_text=text,
            post_url=post_url,
            comment_url=comment_url,
            commented_at=commented_at,
            event_type=event_type,
        )


def filter_recent_interactions(
    raw_comments: list[dict],
    *,
    post_urls: set[str],
    own_fb_id: str,
    own_comment_ids: set[str],
    now: datetime | None = None,
    lookback: timedelta = timedelta(days=14),
) -> list[InteractionCandidate]:
    """Fail-safe lọc comment có locator, timestamp và nằm trong cửa sổ theo dõi."""
    current = as_utc(now) or utcnow()
    cutoff = current - lookback
    normalized_posts = {url.split("#", 1)[0].split("?", 1)[0].rstrip("/") for url in post_urls}
    seen: set[str] = set()
    result: list[InteractionCandidate] = []
    for raw in raw_comments:
        candidate = InteractionCandidate.from_dict(raw, own_comment_ids=own_comment_ids)
        if candidate is None or candidate.fb_comment_id in seen:
            continue
        if own_fb_id and candidate.author_fb_id == own_fb_id:
            continue
        base_post_url = candidate.post_url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
        if base_post_url not in normalized_posts:
            continue
        if candidate.commented_at < cutoff or candidate.commented_at > current + timedelta(minutes=5):
            continue
        seen.add(candidate.fb_comment_id)
        result.append(candidate)
    return result


async def record_interactions(
    db: AsyncSession,
    *,
    user_id: str,
    candidates: list[InteractionCandidate],
    campaign_id: str | None = None,
    post_publish_history_id: str | None = None,
) -> list[PageInteraction]:
    if not candidates:
        return []
    ids = [candidate.fb_comment_id for candidate in candidates]
    existing = set((await db.scalars(select(PageInteraction.fb_comment_id).where(
        PageInteraction.user_id == user_id,
        PageInteraction.fb_comment_id.in_(ids),
    ))).all())
    created: list[PageInteraction] = []
    for candidate in candidates:
        if candidate.fb_comment_id in existing:
            continue
        interaction = PageInteraction(
            user_id=user_id,
            campaign_id=campaign_id,
            post_publish_history_id=post_publish_history_id,
            event_type=candidate.event_type,
            fb_comment_id=candidate.fb_comment_id,
            parent_fb_comment_id=candidate.parent_fb_comment_id,
            author_fb_id=candidate.author_fb_id,
            author_name=candidate.author_name or "Unknown",
            comment_text=candidate.comment_text,
            post_url=candidate.post_url,
            comment_url=candidate.comment_url,
            commented_at=candidate.commented_at,
        )
        db.add(interaction)
        created.append(interaction)
        label = "Khách phản hồi" if candidate.event_type == CUSTOMER_REPLY else "Người đăng bài phản hồi"
        await notify_handoff(
            db,
            user_id=user_id,
            event_type=candidate.event_type,
            summary=f"{label}: {candidate.author_name or 'Unknown'} — {candidate.comment_text[:700]}",
            source=PAGE_MONITOR_SOURCE,
            occurred_at=candidate.commented_at,
            link=candidate.comment_url or candidate.post_url,
            dedup_key=f"interaction:{candidate.fb_comment_id}",
        )
        existing.add(candidate.fb_comment_id)
    await db.flush()
    return created


def own_comment_ids_from_urls(comment_urls: list[str]) -> set[str]:
    ids: set[str] = set()
    for url in comment_urls:
        marker = "comment_id="
        if marker in url:
            ids.add(url.split(marker, 1)[1].split("&", 1)[0])
    return ids
