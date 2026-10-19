"""Enqueue notifications in the same transaction as their business event."""
import hashlib

from sqlalchemy import select

from app.config import get_settings
from app.models.operations import NotificationOutbox
from app.services.notification_service import build_post_keyboard, build_post_message


def bot_scope(token: str | None = None) -> str:
    actual = get_settings().telegram_bot_token if token is None else token
    return hashlib.sha256(actual.encode()).hexdigest()[:32]


def delivery_scope(channel: str) -> str:
    settings = get_settings()
    if channel == "telegram":
        return bot_scope(settings.telegram_bot_token)
    credential = settings.discord_webhook_url
    return hashlib.sha256(f"{channel}:{credential}".encode()).hexdigest()[:32]


async def queue_text(db, chat_id: str, text: str, *, key=None, channel: str = "telegram"):
    if not chat_id:
        return
    db.add(NotificationOutbox(
        chat_id=chat_id, channel=channel, bot_scope=delivery_scope(channel),
        dedup_key=f"{channel}:{chat_id}:{key}" if key else None,
        payload={"chat_id": chat_id, "text": text[:4000]},
    ))


async def queue_notification(db, *, channel: str, recipient_id: str, payload: dict, key=None):
    if not recipient_id:
        return
    dedup_key = f"{channel}:{recipient_id}:{key}" if key else None
    if dedup_key and await db.scalar(
        select(NotificationOutbox.id).where(NotificationOutbox.dedup_key == dedup_key)
    ):
        return
    db.add(NotificationOutbox(
        chat_id=recipient_id,
        channel=channel,
        bot_scope=delivery_scope(channel),
        dedup_key=dedup_key,
        payload=payload,
    ))


async def queue_post_notification(db, chat_id, post, campaign_name):
    db.add(NotificationOutbox(
        dedup_key=f"post:{post.id}", chat_id=chat_id, bot_scope=bot_scope(), post_id=post.id,
        payload={
            "chat_id": chat_id,
            "text": build_post_message(post, campaign_name),
            "parse_mode": "MarkdownV2",
            "reply_markup": build_post_keyboard(post.id, post.post_url),
        },
    ))
