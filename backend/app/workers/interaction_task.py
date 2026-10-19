# plan: docs/plans/community_job_runner_plan.md
"""PAGE_MONITOR worker: read published pages and hand off new interactions."""
from datetime import timedelta

from sqlalchemy import select

from app.database import get_session_factory
from app.models.base import utcnow
from app.models.clone_account import CloneAccount
from app.models.post import CommentAction, DiscoveredPost, PostPublishHistory
from app.services.crypto import decrypt_cookies
from app.services.interaction_service import (
    filter_recent_interactions,
    own_comment_ids_from_urls,
    record_interactions,
)
from app.workers.browser_runtime import scrape_post_comments_raw
from app.workers.celery_app import celery_app, run_async


async def monitor_comment_batch(
    db,
    *,
    user_id: str,
    post_url: str,
    raw_comments: list[dict],
    own_fb_id: str = "",
    own_comment_ids: set[str] | None = None,
    campaign_id: str | None = None,
    post_publish_history_id: str | None = None,
    now=None,
    lookback: timedelta = timedelta(days=14),
) -> dict:
    candidates = filter_recent_interactions(
        raw_comments,
        post_urls={post_url},
        own_fb_id=own_fb_id,
        own_comment_ids=own_comment_ids or set(),
        now=now,
        lookback=lookback,
    )
    created = await record_interactions(
        db,
        user_id=user_id,
        candidates=candidates,
        campaign_id=campaign_id,
        post_publish_history_id=post_publish_history_id,
    )
    return {"observed": len(raw_comments), "candidates": len(candidates), "created": len(created)}


async def _monitor_user(user_id: str, lookback_days: int = 14) -> dict:
    now = utcnow()
    cutoff = now - timedelta(days=lookback_days)
    result = {"posts": 0, "observed": 0, "created": 0, "errors": 0}
    async with get_session_factory()() as db:
        histories = list((await db.scalars(select(PostPublishHistory).where(
            PostPublishHistory.user_id == user_id,
            PostPublishHistory.status.in_(("published", "published_no_url")),
            PostPublishHistory.published_at >= cutoff,
            PostPublishHistory.post_url != "",
        ).order_by(PostPublishHistory.published_at.desc()).limit(20))).all())
        for history in histories:
            clone = await db.get(CloneAccount, history.clone_account_id) if history.clone_account_id else None
            if clone is None or not history.post_url:
                continue
            comment_urls = list((await db.scalars(select(CommentAction.comment_url).join(
                DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id,
            ).where(
                DiscoveredPost.post_url == history.post_url,
                CommentAction.comment_url != "",
            ))).all())
            try:
                cookies = decrypt_cookies(clone.cookie_data_encrypted)
                raw_comments = await scrape_post_comments_raw(clone, history.post_url, cookies, limit=100)
                stats = await monitor_comment_batch(
                    db,
                    user_id=user_id,
                    post_url=history.post_url,
                    raw_comments=raw_comments,
                    own_fb_id=clone.fb_user_id,
                    own_comment_ids=own_comment_ids_from_urls(comment_urls),
                    campaign_id=history.campaign_id,
                    post_publish_history_id=history.id,
                    now=now,
                    lookback=timedelta(days=lookback_days),
                )
                result["posts"] += 1
                result["observed"] += stats["observed"]
                result["created"] += stats["created"]
            except Exception:
                result["errors"] += 1
        await db.commit()
    return result


@celery_app.task(name="app.workers.interaction_task.monitor_user_pages")
def monitor_user_pages(user_id: str, lookback_days: int = 14) -> dict:
    return run_async(_monitor_user(user_id, lookback_days))
