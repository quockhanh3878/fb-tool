# plan: docs/plans/community_job_runner_plan.md
"""Offline verification for Discord DM registration commands."""

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
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'discord_bot.db'}",
        JWT_SECRET="offline-discord-bot-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-discord-bot-desktop-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


def test_discord_dm_registration_is_one_time_and_revocable():
    asyncio.run(_scenario())


async def _scenario():
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.operations import NotificationRecipient
    from app.models.user import User
    from app.services.discord_registration import (
        create_discord_link_code,
        handle_discord_dm,
    )

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)

    async with get_session_factory()() as db:
        owner = User(email="discord-owner@example.test", hashed_password="x")
        db.add(owner)
        await db.flush()
        code, expires_at = await create_discord_link_code(db, owner.id, now=now)
        assert expires_at == now + timedelta(minutes=15)

        reply = await handle_discord_dm(
            db,
            discord_user_id="123456789",
            display_name="Test Discord User",
            content=f"/dangky {code}",
            now=now,
        )
        await db.commit()
        assert "Đã liên kết" in reply
        recipient = await db.scalar(select(NotificationRecipient).where(
            NotificationRecipient.user_id == owner.id,
            NotificationRecipient.channel == "discord_dm",
        ))
        assert recipient is not None
        assert recipient.source == "bot_registered"
        assert recipient.event_types == ["all"]

        reused = await handle_discord_dm(
            db,
            discord_user_id="987654321",
            display_name="Another User",
            content=f"/dangky {code}",
            now=now,
        )
        assert "không đúng" in reused or "hết hạn" in reused

        cancelled = await handle_discord_dm(
            db,
            discord_user_id="123456789",
            display_name="Test Discord User",
            content="/huy",
            now=now,
        )
        await db.commit()
        assert "huỷ" in cancelled
        await db.refresh(recipient)
        assert recipient.is_active is False
