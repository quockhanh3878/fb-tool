"""Recover uncertain jobs and deliver the transactional notification outbox."""
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from app.database import get_session_factory
from app.models.base import utcnow
from app.models.enums import CommentStatus, PostStatus, PublishStatus
from app.models.operations import NotificationOutbox, RefreshSession, ResourceLease, TelegramUpdate
from app.models.post import CommentAction, DiscoveredPost, PostPublish
from app.services.notification_service import NotificationService, strip_markdown
from app.services.discord_service import DiscordService
from app.services.outbox_service import bot_scope, delivery_scope
from app.workers.celery_app import celery_app, run_async


async def recover_stale_jobs() -> dict:
    now = utcnow()
    counts = {}
    async with get_session_factory()() as db:
        for model, running, uncertain in (
            (CommentAction, CommentStatus.IN_PROGRESS.value, CommentStatus.UNKNOWN_OUTCOME.value),
            (PostPublish, PublishStatus.PUBLISHING.value, PublishStatus.UNKNOWN_OUTCOME.value),
        ):
            result = await db.execute(update(model).where(
                model.status == running,
                or_(model.lease_expires_at.is_(None), model.lease_expires_at <= now),
            ).values(status=uncertain, lease_expires_at=None, error_message="Worker interrupted; review before retry"))
            counts[model.__tablename__] = result.rowcount
        await db.execute(update(NotificationOutbox).where(
            NotificationOutbox.status == "sending", NotificationOutbox.lease_expires_at <= now,
        ).values(status="pending", lease_expires_at=None, next_attempt_at=now))
        await db.execute(delete(ResourceLease).where(ResourceLease.expires_at <= now))
        await db.execute(delete(RefreshSession).where(RefreshSession.expires_at < now))
        await db.execute(delete(TelegramUpdate).where(TelegramUpdate.received_at < now - timedelta(days=30)))
        await db.commit()
    return counts


async def deliver_notifications(notifier=None, discord=None) -> dict:
    notifier = notifier or NotificationService()
    discord = discord or DiscordService()
    enabled_scopes = {}
    if notifier.enabled:
        enabled_scopes["telegram"] = bot_scope(notifier.bot_token)
    if discord.enabled:
        enabled_scopes["discord_webhook"] = delivery_scope("discord_webhook")
    if not enabled_scopes:
        return {"sent": 0, "disabled": True}
    async with get_session_factory()() as db:
        ids = list((await db.scalars(select(NotificationOutbox.id).where(
            NotificationOutbox.status == "pending",
            NotificationOutbox.next_attempt_at <= utcnow(),
            NotificationOutbox.attempts < 5,
            NotificationOutbox.channel.in_(list(enabled_scopes)),
        ).order_by(NotificationOutbox.next_attempt_at).limit(20))).all())
    sent = 0
    for notification_id in ids:
        async with get_session_factory()() as db:
            message = await db.get(NotificationOutbox, notification_id)
            if message is None or message.channel not in enabled_scopes:
                continue
            claim = await db.execute(update(NotificationOutbox).where(
                NotificationOutbox.id == notification_id, NotificationOutbox.status == "pending",
                NotificationOutbox.next_attempt_at <= utcnow(), NotificationOutbox.attempts < 5,
                NotificationOutbox.bot_scope == enabled_scopes[message.channel],
            ).execution_options(synchronize_session=False).values(
                status="sending", attempts=NotificationOutbox.attempts + 1,
                lease_expires_at=utcnow() + timedelta(minutes=2),
            ))
            if claim.rowcount != 1:
                await db.rollback()
                continue
            await db.commit()
            await db.refresh(message)
            payload = dict(message.payload)
            if message.channel == "discord_webhook":
                result = await discord.send_payload(payload)
            else:
                result = await notifier._call("sendMessage", payload)
            if message.channel == "telegram" and result and result.get("ok") is False and result.get("status") == 400 and payload.get("parse_mode"):
                payload.pop("parse_mode")
                payload["text"] = strip_markdown(payload["text"])
                result = await notifier._call("sendMessage", payload)
            message.lease_expires_at = None
            if result and result.get("ok") is True:
                message.status = "sent"
                message.last_error = None
                sent += 1
                if message.post_id:
                    await db.execute(update(DiscoveredPost).where(
                        DiscoveredPost.id == message.post_id,
                        DiscoveredPost.status == PostStatus.NOTIFICATION_PENDING.value,
                    ).values(status=PostStatus.NOTIFIED.value, notified_at=utcnow()))
            elif message.channel == "discord_webhook" and result and result.get("status") == 429:
                message.status = "pending"
                message.last_error = "discord_rate_limited"
                message.next_attempt_at = utcnow() + timedelta(seconds=result.get("retry_after", 30))
            else:
                message.status = "failed" if message.attempts >= 5 else "pending"
                message.last_error = f"{message.channel}_delivery_failed"
                message.next_attempt_at = utcnow() + timedelta(seconds=min(3600, 30 * 2 ** message.attempts))
            await db.commit()
    return {"sent": sent}


@celery_app.task(name="app.workers.maintenance_task.maintain")
def maintain():
    return {"recovery": run_async(recover_stale_jobs()), "delivery": run_async(deliver_notifications())}
