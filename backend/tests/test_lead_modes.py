# plan: docs/plans/community_job_runner_plan.md
"""Offline regression tests for LEAD_MATCH and LEAD_REPLY modes."""

import asyncio
import base64
import os
import tempfile
from pathlib import Path


def _configure() -> None:
    os.environ.update(
        APP_ENV="test",
        DEBUG="false",
        RUN_MODE="desktop",
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'lead_modes.db'}",
        JWT_SECRET="offline-lead-modes-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-lead-modes-desktop-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


class FakeAI:
    def __init__(self, score: float):
        self.score = score

    async def filter_post(self, _text, _campaign):
        return {"relevance_score": self.score, "reason": "synthetic", "extracted": {}}


def test_full_auto_high_score_queues_existing_script():
    asyncio.run(_scenario_full_auto())


async def _scenario_full_auto():
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.campaign import Campaign, CommentScript
    from app.models.enums import CampaignMode, CommentStatus, PaymentStatus, PostStatus
    from app.models.post import CommentAction, DiscoveredPost
    from app.models.user import Subscription, User
    from app.services.pipeline import process_campaign_posts

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    async with get_session_factory()() as db:
        user = User(email="lead-mode-owner@example.test", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add(Subscription(user_id=user.id, payment_status=PaymentStatus.ACTIVE.value, max_comments_per_day=20))
        campaign = Campaign(
            user_id=user.id,
            name="full-auto",
            mode=CampaignMode.FULL_AUTO.value,
            is_active=True,
            min_relevance_score=0.7,
            review_floor=0.5,
        )
        db.add(campaign)
        await db.flush()
        db.add(CommentScript(
            campaign_id=campaign.id,
            name="existing",
            template_content="Xin chao ban, minh co the ho tro viet noi dung cho ban",
        ))
        post = DiscoveredPost(
            campaign_id=campaign.id,
            content_hash="lead-mode-full-auto",
            post_url="https://www.facebook.com/groups/synthetic/posts/1",
            content_text="Toi can nguoi viet bai gioi thieu san pham",
            status=PostStatus.NEW.value,
        )
        db.add(post)
        await db.flush()
        result = await process_campaign_posts(db, campaign, [post], FakeAI(0.9), user=user)
        await db.commit()
        action = await db.scalar(select(CommentAction).where(CommentAction.discovered_post_id == post.id))
        assert result["queued"] == 1, result
        assert action is not None and action.status == CommentStatus.QUEUED.value


def test_review_floor_and_missing_script_never_queue_comment():
    asyncio.run(_scenario_review_floor())


def test_semi_auto_only_notifies_and_never_queues_comment():
    asyncio.run(_scenario_semi_auto())


async def _scenario_review_floor():
    _configure()
    from sqlalchemy import func, select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.campaign import Campaign
    from app.models.enums import CampaignMode, PaymentStatus, PostStatus
    from app.models.post import CommentAction, DiscoveredPost
    from app.models.user import Subscription, User
    from app.services.pipeline import process_campaign_posts

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    async with get_session_factory()() as db:
        user = User(email="lead-review-owner@example.test", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add(Subscription(user_id=user.id, payment_status=PaymentStatus.ACTIVE.value, max_comments_per_day=20))
        campaign = Campaign(
            user_id=user.id,
            name="review",
            mode=CampaignMode.FULL_AUTO.value,
            is_active=True,
            min_relevance_score=0.7,
            review_floor=0.5,
        )
        db.add(campaign)
        await db.flush()
        post = DiscoveredPost(
            campaign_id=campaign.id,
            content_hash="lead-mode-review",
            post_url="https://www.facebook.com/groups/synthetic/posts/2",
            content_text="Toi can nguoi viet bai gioi thieu san pham",
            status=PostStatus.NEW.value,
        )
        db.add(post)
        await db.flush()
        result = await process_campaign_posts(db, campaign, [post], FakeAI(0.6), user=user)
        await db.commit()
        assert result["notified"] == 1
        assert post.status == PostStatus.NEED_REVIEW.value
        assert await db.scalar(select(func.count(CommentAction.id))) == 0

        campaign2 = Campaign(
            user_id=user.id,
            name="missing-script",
            mode=CampaignMode.FULL_AUTO.value,
            is_active=True,
            min_relevance_score=0.7,
            review_floor=0.5,
        )
        db.add(campaign2)
        await db.flush()
        no_script_post = DiscoveredPost(
            campaign_id=campaign2.id,
            content_hash="lead-mode-no-script",
            post_url="https://www.facebook.com/groups/synthetic/posts/3",
            content_text="Toi can nguoi viet bai gioi thieu san pham",
            status=PostStatus.NEW.value,
        )
        db.add(no_script_post)
        await db.flush()
        await process_campaign_posts(db, campaign2, [no_script_post], FakeAI(0.95), user=user)
        await db.commit()
        assert no_script_post.status == PostStatus.NEED_REVIEW.value
        assert await db.scalar(select(func.count(CommentAction.id))) == 0


async def _scenario_semi_auto():
    _configure()
    from sqlalchemy import func, select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.campaign import Campaign
    from app.models.enums import CampaignMode, PaymentStatus, PostStatus
    from app.models.post import CommentAction, DiscoveredPost
    from app.models.user import Subscription, User
    from app.services.pipeline import process_campaign_posts

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    async with get_session_factory()() as db:
        user = User(email="semi-auto-owner@example.test", hashed_password="x")
        db.add(user)
        await db.flush()
        db.add(Subscription(user_id=user.id, payment_status=PaymentStatus.ACTIVE.value, max_comments_per_day=20))
        campaign = Campaign(
            user_id=user.id,
            name="semi-auto",
            mode=CampaignMode.SEMI_AUTO.value,
            is_active=True,
            min_relevance_score=0.7,
            review_floor=0.5,
        )
        db.add(campaign)
        await db.flush()
        post = DiscoveredPost(
            campaign_id=campaign.id,
            content_hash="lead-mode-semi-auto",
            post_url="https://www.facebook.com/groups/synthetic/posts/4",
            content_text="Toi can nguoi viet bai gioi thieu san pham",
            status=PostStatus.NEW.value,
        )
        db.add(post)
        await db.flush()
        result = await process_campaign_posts(db, campaign, [post], FakeAI(0.95), user=user)
        await db.commit()
        assert result["notified"] == 1
        assert post.status == PostStatus.NOTIFICATION_PENDING.value
        assert await db.scalar(select(func.count(CommentAction.id))) == 0
