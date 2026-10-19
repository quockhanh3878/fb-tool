# plan: docs/plans/community_job_runner_plan.md
"""Offline verification for M2 job runs, stale detection, and pause guard."""

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
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'job_registry.db'}",
        JWT_SECRET="offline-job-registry-secret-32-bytes",
        DESKTOP_INSTANCE_SECRET="offline-job-registry-desktop-secret-32",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/synthetic/token",
    )


def test_job_registry_pauses_after_three_failures_and_reports_stale_job():
    asyncio.run(_scenario())


async def _scenario():
    _configure()
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import get_session_factory, init_models, reset_engine_cache
    from app.models.job import JobRun
    from app.models.operations import NotificationOutbox, NotificationRecipient
    from app.models.user import User
    from app.services.job_registry import (
        JobName,
        check_job_health,
        fail_job,
        finish_job,
        start_job,
    )

    get_settings.cache_clear()
    reset_engine_cache()
    await init_models()
    now = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)

    async with get_session_factory()() as db:
        owner = User(email="job-owner@example.test", hashed_password="x")
        db.add(owner)
        await db.flush()
        db.add(NotificationRecipient(
            user_id=owner.id,
            channel="discord_webhook",
            recipient_id="123456789",
            display_name="Test receiver",
            event_types=["error"],
            source="manual",
        ))
        await db.flush()

        for index in range(3):
            run = await start_job(
                db,
                JobName.PR_BUMP,
                user_id=owner.id,
                started_at=now + timedelta(minutes=index),
            )
            await fail_job(
                db,
                run,
                f"synthetic failure {index}",
                finished_at=now + timedelta(minutes=index, seconds=1),
            )
        await db.commit()

        paused = list((await db.scalars(select(JobRun).where(
            JobRun.job_name == JobName.PR_BUMP,
            JobRun.user_id == owner.id,
        ).order_by(JobRun.started_at))).all())
        assert [row.status for row in paused] == ["error", "error", "paused"]
        assert len((await db.scalars(select(NotificationOutbox))).all()) == 1

        old_start = now - timedelta(hours=3)
        stale_run = await start_job(
            db,
            JobName.LEAD_SCAN,
            user_id=owner.id,
            started_at=old_start,
        )
        await finish_job(db, stale_run, counts={"scanned": 4}, finished_at=old_start + timedelta(minutes=1))
        await db.commit()

        first = await check_job_health(db, now=now)
        await db.commit()
        assert first["checked"] == 2
        assert {item["job_name"] for item in first["stale"]} == {"LEAD_SCAN"}
        assert {item["job_name"] for item in first["paused"]} == {"PR_BUMP"}
        assert len((await db.scalars(select(NotificationOutbox))).all()) == 2

        second = await check_job_health(db, now=now)
        await db.commit()
        assert second["stale"] == first["stale"]
        assert len((await db.scalars(select(NotificationOutbox))).all()) == 2
