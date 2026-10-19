# plan: docs/plans/community_job_runner_plan.md
"""Mô phỏng PAGE_MONITOR trong cửa sổ 24 giờ, không mở Facebook."""

import asyncio
import base64
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _configure():
    os.environ.update(
        APP_ENV="test",
        DEBUG="false",
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'interaction_watcher.db'}",
        JWT_SECRET="offline-interaction-watcher-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-interaction-watcher-desktop-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


def test_page_monitor_filters_recent_deduplicates_and_handoffs():
    asyncio.run(_scenario())


async def _scenario():
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.interaction import PageInteraction
    from app.models.operations import NotificationOutbox, NotificationRecipient
    from app.models.user import User
    from app.workers.interaction_task import monitor_comment_batch

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)
    post_url = "https://www.facebook.com/groups/synthetic/posts/one-day-test"

    async with get_session_factory()() as db:
        owner = User(email="interaction-owner@example.test", hashed_password="x")
        db.add(owner)
        await db.flush()
        db.add(NotificationRecipient(
            user_id=owner.id,
            channel="discord_webhook",
            recipient_id="123456789",
            display_name="Test receiver",
            event_types=["customer_reply", "post_author_reply"],
            source="manual",
        ))
        await db.flush()

        comments = [
            {
                "id": "comment-customer",
                "parent_comment_id": "own-application",
                "author_id": "other-1",
                "author": "Khách thử nghiệm",
                "text": "Tôi muốn hỏi thêm thông tin",
                "url": post_url,
                "comment_url": post_url + "?comment_id=comment-customer",
                "commented_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "id": "comment-author",
                "author_id": "other-2",
                "author": "Người đăng bài",
                "text": "Bạn gửi mình bảng giá nhé",
                "url": post_url,
                "comment_url": post_url + "?comment_id=comment-author",
                "commented_at": (now - timedelta(hours=4)).isoformat(),
            },
            {
                "id": "own-comment",
                "author_id": "own-account",
                "author": "Nick của mình",
                "text": "Comment của nick theo dõi",
                "url": post_url,
                "commented_at": (now - timedelta(hours=1)).isoformat(),
            },
            {
                "id": "old-comment",
                "author_id": "other-old",
                "author": "Comment cũ",
                "text": "Không nằm trong cửa sổ test",
                "url": post_url,
                "commented_at": (now - timedelta(days=2)).isoformat(),
            },
            {
                "id": "comment-customer",
                "author_id": "other-1",
                "author": "Bản trùng",
                "text": "Không tạo interaction thứ hai",
                "url": post_url,
                "commented_at": (now - timedelta(hours=2)).isoformat(),
            },
            {
                "id": "other-post",
                "author_id": "other-3",
                "author": "Bài khác",
                "text": "Không thuộc bài đang theo dõi",
                "url": "https://www.facebook.com/groups/synthetic/posts/other",
                "commented_at": (now - timedelta(hours=2)).isoformat(),
            },
        ]

        first = await monitor_comment_batch(
            db,
            user_id=owner.id,
            post_url=post_url,
            raw_comments=comments,
            own_fb_id="own-account",
            own_comment_ids={"own-application"},
            now=now,
            lookback=timedelta(days=1),
        )
        await db.commit()
        assert first == {"observed": 6, "candidates": 2, "created": 2}

        interactions = list((await db.scalars(select(PageInteraction))).all())
        notifications = list((await db.scalars(select(NotificationOutbox))).all())
        assert len(interactions) == 2
        assert len(notifications) == 2
        assert {row.event_type for row in interactions} == {"customer_reply", "post_author_reply"}

        second = await monitor_comment_batch(
            db,
            user_id=owner.id,
            post_url=post_url,
            raw_comments=comments,
            own_fb_id="own-account",
            own_comment_ids={"own-application"},
            now=now,
            lookback=timedelta(days=1),
        )
        await db.commit()
        assert second == {"observed": 6, "candidates": 2, "created": 0}
        assert len((await db.scalars(select(PageInteraction))).all()) == 2
        assert len((await db.scalars(select(NotificationOutbox))).all()) == 2
