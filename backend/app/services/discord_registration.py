# plan: docs/plans/community_job_runner_plan.md
"""One-time Discord DM registration for desktop bot users."""
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import as_utc, utcnow
from app.models.operations import NotificationRecipient
from app.models.user import User

CODE_TTL = timedelta(minutes=15)
DEFAULT_EVENT_TYPES = ["all"]


def _new_code() -> str:
    return secrets.token_urlsafe(8).replace("-", "").replace("_", "").upper()[:12]


async def create_discord_link_code(
    db: AsyncSession,
    user_id: str,
    *,
    now: datetime | None = None,
    ttl: timedelta = CODE_TTL,
) -> tuple[str, datetime]:
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise ValueError("user_not_found")
    expires_at = (now or utcnow()) + ttl
    user.discord_link_code = _new_code()
    user.discord_link_expires_at = expires_at
    await db.flush()
    return user.discord_link_code, expires_at


async def handle_discord_dm(
    db: AsyncSession,
    *,
    discord_user_id: str,
    display_name: str,
    content: str,
    now: datetime | None = None,
) -> str:
    """Handle only explicit DM commands; no command performs Facebook work."""
    current = now or utcnow()
    parts = (content or "").strip().split(maxsplit=1)
    command = parts[0].lower() if parts else ""
    argument = parts[1].strip().upper() if len(parts) == 2 else ""

    if command in {"/huy", "/cancel"}:
        await db.execute(update(NotificationRecipient).where(
            NotificationRecipient.channel == "discord_dm",
            NotificationRecipient.recipient_id == discord_user_id,
        ).values(is_active=False))
        return "Đã huỷ nhận thông báo Discord cho tài khoản đã liên kết."

    if command not in {"/dangky", "/register"} or not argument:
        return "Dùng /dangky <mã> để liên kết hoặc /huy để huỷ nhận thông báo."

    user = await db.scalar(select(User).where(
        User.discord_link_code == argument,
        User.is_active.is_(True),
    ))
    if user is None or not user.discord_link_expires_at or as_utc(user.discord_link_expires_at) <= current:
        return "Mã liên kết không đúng hoặc đã hết hạn."

    existing_owner = await db.scalar(select(NotificationRecipient).where(
        NotificationRecipient.channel == "discord_dm",
        NotificationRecipient.recipient_id == discord_user_id,
        NotificationRecipient.user_id != user.id,
        NotificationRecipient.is_active.is_(True),
    ))
    if existing_owner is not None:
        return "Discord user này đã liên kết với tài khoản khác."

    recipient = await db.scalar(select(NotificationRecipient).where(
        NotificationRecipient.user_id == user.id,
        NotificationRecipient.channel == "discord_dm",
        NotificationRecipient.recipient_id == discord_user_id,
    ))
    if recipient is None:
        recipient = NotificationRecipient(
            user_id=user.id,
            channel="discord_dm",
            recipient_id=discord_user_id,
            display_name=display_name[:120],
            event_types=DEFAULT_EVENT_TYPES.copy(),
            source="bot_registered",
            verified_at=current,
        )
        db.add(recipient)
    else:
        recipient.display_name = display_name[:120]
        recipient.event_types = DEFAULT_EVENT_TYPES.copy()
        recipient.source = "bot_registered"
        recipient.is_active = True
        recipient.verified_at = current
    user.discord_link_code = None
    user.discord_link_expires_at = None
    await db.flush()
    return f"Đã liên kết Discord với tài khoản {user.email}."
