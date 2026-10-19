# plan: docs/plans/community_job_runner_plan.md
"""Kiểm chứng offline cho M1a Notification Gateway."""

import asyncio
import base64
import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest


def _configure():
    os.environ.update(
        APP_ENV="test",
        DEBUG="false",
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'notification_gateway.db'}",
        JWT_SECRET="offline-notification-gateway-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-notification-gateway-desktop-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


def test_gateway_builds_scoped_discord_and_telegram_outbox():
    asyncio.run(_gateway_scenario())


async def _gateway_scenario():
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.operations import NotificationOutbox, NotificationRecipient
    from app.models.user import User
    from app.services.notification_service import notify_error, notify_handoff

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    async with get_session_factory()() as db:
        owner = User(email="gateway-owner@example.test", hashed_password="x")
        other = User(email="gateway-other@example.test", hashed_password="x")
        db.add_all([owner, other])
        await db.flush()
        db.add_all([
            NotificationRecipient(
                user_id=owner.id, channel="discord_webhook", recipient_id="123456789",
                display_name="Discord", event_types=["lead"], source="manual",
            ),
            NotificationRecipient(
                user_id=owner.id, channel="telegram", recipient_id="987654321",
                display_name="Telegram", event_types=["error"], source="manual",
            ),
            NotificationRecipient(
                user_id=other.id, channel="discord_webhook", recipient_id="111111111",
                display_name="Other", event_types=["lead"], source="manual",
            ),
        ])
        await notify_handoff(
            db,
            user_id=owner.id,
            event_type="lead",
            summary="Có @everyone cần tư vấn",
            source="PAGE_MONITOR",
            occurred_at="2026-09-23T10:00:00+00:00",
            link="https://www.facebook.com/groups/synthetic/posts/1",
            dedup_key="lead:1",
        )
        await notify_handoff(
            db,
            user_id=other.id,
            event_type="lead",
            summary="Không được gửi sang tenant khác",
            source="PAGE_MONITOR",
            occurred_at="2026-09-23T10:00:00+00:00",
            dedup_key="lead:1",
        )
        await notify_error(
            db,
            user_id=owner.id,
            summary="Job lỗi",
            source="HEALTH_CHECK",
            occurred_at="2026-09-23T10:00:00+00:00",
            dedup_key="error:1",
        )
        await db.commit()

        rows = list((await db.scalars(select(NotificationOutbox).order_by(NotificationOutbox.chat_id))).all())
        assert len(rows) == 3
        owner_rows = [row for row in rows if row.chat_id in {"123456789", "987654321"}]
        assert len(owner_rows) == 2
        discord = next(row for row in owner_rows if row.channel == "discord_webhook")
        telegram = next(row for row in owner_rows if row.channel == "telegram")
        assert discord.payload["allowed_mentions"] == {"parse": [], "users": ["123456789"]}
        assert discord.payload["content"] == "<@123456789>"
        fields = {field["name"]: field["value"] for field in discord.payload["embeds"][0]["fields"]}
        assert set(fields) == {"Loại sự kiện", "Tóm tắt", "Nguồn", "Thời gian", "Người tiếp nhận", "Link trực tiếp"}
        assert "@everyone" not in fields["Tóm tắt"]
        assert telegram.payload["text"] == "Job lỗi"

        await notify_handoff(
            db,
            user_id=owner.id,
            event_type="lead",
            summary="Trùng dedup",
            source="PAGE_MONITOR",
            occurred_at="2026-09-23T10:00:00+00:00",
            dedup_key="lead:1",
        )
        await db.commit()
        assert len((await db.scalars(select(NotificationOutbox))).all()) == 3


def test_discord_rate_limit_keeps_outbox_pending():
    asyncio.run(_rate_limit_scenario())


def test_discord_service_parses_rate_limit_and_rejects_untrusted_url():
    from app.services.discord_service import DiscordService, validate_webhook_url

    with pytest.raises(ValueError):
        validate_webhook_url("https://evil.invalid/api/webhooks/1/token")

    class Response:
        status_code = 429
        content = b'{"retry_after": 3.5}'

        def json(self):
            return {"retry_after": 3.5}

    class Client:
        async def post(self, _url, *, json):
            assert json == {"embeds": []}
            return Response()

    async def scenario():
        service = DiscordService(
            webhook_url="https://discord.com/api/webhooks/synthetic/token",
            client=Client(),
        )
        assert await service.send_payload({"embeds": []}) == {
            "ok": False,
            "status": 429,
            "body": {"retry_after": 3.5},
            "retry_after": 3.5,
        }

    asyncio.run(scenario())


async def _rate_limit_scenario():
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.base import as_utc, utcnow
    from app.models.operations import NotificationOutbox
    from app.services.outbox_service import bot_scope, delivery_scope
    from app.workers.maintenance_task import deliver_notifications

    get_settings.cache_clear()
    reset_engine_cache()
    assert delivery_scope("telegram") == bot_scope("")
    await init_models()

    async with get_session_factory()() as db:
        db.add(NotificationOutbox(
            channel="discord_webhook",
            chat_id="123456789",
            bot_scope=delivery_scope("discord_webhook"),
            payload={"embeds": []},
            next_attempt_at=utcnow() - timedelta(seconds=1),
        ))
        await db.commit()

    class DisabledTelegram:
        enabled = False

    class RateLimitedDiscord:
        enabled = True

        async def send_payload(self, _payload):
            return {"ok": False, "status": 429, "retry_after": 17}

    result = await deliver_notifications(notifier=DisabledTelegram(), discord=RateLimitedDiscord())
    assert result["sent"] == 0
    async with get_session_factory()() as db:
        row = (await db.scalars(select(NotificationOutbox))).one()
        assert row.status == "pending"
        assert row.attempts == 1
        assert row.last_error == "discord_rate_limited"
        assert as_utc(row.next_attempt_at) > utcnow() + timedelta(seconds=10)
