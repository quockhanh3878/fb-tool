"""Enqueue notifications in the same transaction as their business event."""
import hashlib

from app.config import get_settings
from app.models.operations import NotificationOutbox
from app.services.notification_service import build_post_keyboard, build_post_message


def bot_scope(token: str | None = None) -> str:
    actual = get_settings().telegram_bot_token if token is None else token
    return hashlib.sha256(actual.encode()).hexdigest()[:32]


async def queue_text(db, chat_id: str, text: str, *, key=None):
    if not chat_id:
        return
    db.add(NotificationOutbox(
        chat_id=chat_id, bot_scope=bot_scope(), dedup_key=key,
        payload={"chat_id": chat_id, "text": text[:4000]},
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