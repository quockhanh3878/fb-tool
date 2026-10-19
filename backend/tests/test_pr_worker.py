# plan: docs/plans/community_job_runner_plan.md
"""Offline regression tests for PR duplicate and liveness guards."""

import asyncio
import base64
import os
import tempfile
from datetime import timedelta
from pathlib import Path


def _configure() -> None:
    os.environ.update(
        APP_ENV="test",
        DEBUG="false",
        RUN_MODE="desktop",
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'pr_worker.db'}",
        JWT_SECRET="offline-pr-worker-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-pr-worker-desktop-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


def test_post_probe_unknown_and_gone_fail_closed():
    from app.workers.browser_runtime import classify_post_body

    assert classify_post_body("") == "unknown"
    assert classify_post_body("Nội dung không khả dụng cho bài viết này") == "gone"
    assert classify_post_body("Bài viết còn hiển thị " * 10) == "alive"


def test_same_rendered_pr_is_duplicate_only_for_same_group_window():
    asyncio.run(_scenario_duplicate())


async def _scenario_duplicate():
    _configure()
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.base import utcnow
    from app.models.post import PostPublish, PostPublishHistory
    from app.services.publisher_service import _has_recent_duplicate

    from app.config import get_settings

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    async with get_session_factory()() as db:
        now = utcnow()
        db.add(PostPublishHistory(
            user_id="user-1",
            campaign_id="campaign-1",
            group_id="group-1",
            group_url="https://www.facebook.com/groups/group-1",
            status="published",
            content_snapshot="same rendered post",
            published_at=now - timedelta(days=1),
        ))
        await db.flush()
        post = PostPublish(
            user_id="user-1",
            campaign_id="campaign-1",
            repeat_interval_days=14,
            content_template="same rendered post",
        )
        assert await _has_recent_duplicate(
            db, post,
            {"group_id": "group-1", "group_url": "https://www.facebook.com/groups/group-1"},
            "same rendered post", now, 14,
        )
        assert not await _has_recent_duplicate(
            db, post,
            {"group_id": "group-2", "group_url": "https://www.facebook.com/groups/group-2"},
            "same rendered post", now, 14,
        )
