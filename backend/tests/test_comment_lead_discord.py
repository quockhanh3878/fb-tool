# plan: docs/plans/community_job_runner_plan.md
"""Regression: comment lead notifications also enter the Discord gateway."""

import asyncio
import base64
import os
import tempfile
from pathlib import Path


def _configure() -> None:
    os.environ.update(
        APP_ENV="test",
        DEBUG="false",
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'comment_lead.db'}",
        JWT_SECRET="offline-comment-lead-discord-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-comment-lead-discord-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


def test_comment_lead_queues_discord_handoff_without_telegram():
    asyncio.run(_scenario())


async def _scenario() -> None:
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.operations import NotificationOutbox, NotificationRecipient
    from app.models.user import User
    from app.services.lead_service import notify_leads

    class Lead:
        matched_keywords = ["tim writer"]
        comment_url = "https://www.facebook.com/groups/synthetic/posts/1?comment_id=2"
        post_url = ""

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    async with get_session_factory()() as db:
        owner = User(email="comment-lead@example.test", hashed_password="x")
        db.add(owner)
        await db.flush()
        db.add(NotificationRecipient(
            user_id=owner.id,
            channel="discord_webhook",
            recipient_id="123456789",
            display_name="Discord lead",
            event_types=["lead"],
            source="manual",
        ))
        assert await notify_leads(owner, "PR comm ca nhan", [Lead()], db=db) is True
        await db.commit()

        row = (await db.scalars(select(NotificationOutbox))).one()
        assert row.channel == "discord_webhook"
        fields = {field["name"]: field["value"] for field in row.payload["embeds"][0]["fields"]}
        assert "COMMENT_LEAD" in fields.values()
        assert Lead.comment_url in fields.values()
