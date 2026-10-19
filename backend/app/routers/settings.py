# plan: docs/plans/desktop_packaging.md
"""Màn "Cài đặt" cho chế độ desktop: nhập OpenAI key / Telegram bot token qua
UI thay vì sửa .env. CHỈ hoạt động khi RUN_MODE=desktop — ở chế độ SaaS mọi
route trả 404, vì Settings là singleton toàn tiến trình và việc 1 khách ghi
đè cấu hình sẽ rò rỉ sang khách khác (xem app_settings_service.py)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import utcnow
from app.models.operations import NotificationRecipient
from app.models.user import User
from app.schemas import (
    AppSettingsOut,
    AppSettingsUpdate,
    DiscordLinkCodeOut,
    NotificationRecipientCreate,
    NotificationRecipientOut,
    NotificationRecipientUpdate,
)
from app.services import app_settings_service as svc
from app.services.discord_registration import create_discord_link_code

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _require_desktop_mode() -> None:
    if get_settings().run_mode != "desktop":
        raise HTTPException(status_code=404, detail="Not Found")


@router.get("", response_model=AppSettingsOut)
async def get_app_settings(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _require_desktop_mode()
    return AppSettingsOut(
        openai_api_key_set=bool(await svc.get_value(db, svc.OPENAI_API_KEY)),
        telegram_bot_token_set=bool(await svc.get_value(db, svc.TELEGRAM_BOT_TOKEN)),
        discord_webhook_url_set=bool(await svc.get_value(db, svc.DISCORD_WEBHOOK_URL)),
        discord_bot_token_set=bool(await svc.get_value(db, svc.DISCORD_BOT_TOKEN)),
    )


@router.put("", response_model=AppSettingsOut)
async def update_app_settings(
    payload: AppSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_desktop_mode()
    if payload.discord_webhook_url is not None:
        from app.services.discord_service import validate_webhook_url

        validate_webhook_url(payload.discord_webhook_url.strip())
    if payload.openai_api_key is not None:
        await svc.set_value(db, svc.OPENAI_API_KEY, payload.openai_api_key.strip())

    if payload.telegram_bot_token is not None:
        await svc.set_value(db, svc.TELEGRAM_BOT_TOKEN, payload.telegram_bot_token.strip())
    if payload.discord_webhook_url is not None:
        await svc.set_value(db, svc.DISCORD_WEBHOOK_URL, payload.discord_webhook_url.strip())
    if payload.discord_bot_token is not None:
        await svc.set_value(db, svc.DISCORD_BOT_TOKEN, payload.discord_bot_token.strip())

    await db.commit()
    settings = get_settings()
    if payload.openai_api_key is not None:
        settings.openai_api_key = payload.openai_api_key.strip()
    if payload.telegram_bot_token is not None:
        settings.telegram_bot_token = payload.telegram_bot_token.strip()
    if payload.discord_webhook_url is not None:
        settings.discord_webhook_url = payload.discord_webhook_url.strip()
    if payload.discord_bot_token is not None:
        settings.discord_bot_token = payload.discord_bot_token.strip()
    return AppSettingsOut(
        openai_api_key_set=bool(await svc.get_value(db, svc.OPENAI_API_KEY)),
        telegram_bot_token_set=bool(await svc.get_value(db, svc.TELEGRAM_BOT_TOKEN)),
        discord_webhook_url_set=bool(await svc.get_value(db, svc.DISCORD_WEBHOOK_URL)),
        discord_bot_token_set=bool(await svc.get_value(db, svc.DISCORD_BOT_TOKEN)),
    )


@router.post("/discord-link-code", response_model=DiscordLinkCodeOut)
async def create_discord_link_code_endpoint(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _require_desktop_mode()
    code, expires_at = await create_discord_link_code(db, user.id)
    await db.commit()
    return DiscordLinkCodeOut(code=code, expires_at=expires_at)


@router.post("/discord-test")
async def send_discord_test(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Send one explicit, non-mentioning probe to the configured webhook."""
    _require_desktop_mode()
    webhook_url = await svc.get_value(db, svc.DISCORD_WEBHOOK_URL)
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Chưa cấu hình Discord webhook")
    from app.services.discord_service import DiscordService, build_webhook_payload

    result = await DiscordService(webhook_url).send_payload(
        build_webhook_payload(
            event_type="error",
            summary="Tin thử Discord từ CommHunter",
            source="SETTINGS",
            occurred_at=utcnow(),
            link="",
        )
    )
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail="Discord webhook không nhận được tin thử")
    return {"sent": True, "status": result.get("status")}


@router.get("/discord-recipients", response_model=list[NotificationRecipientOut])
async def list_discord_recipients(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    _require_desktop_mode()
    result = await db.execute(
        select(NotificationRecipient)
        .where(NotificationRecipient.user_id == user.id)
        .order_by(NotificationRecipient.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/discord-recipients",
    response_model=NotificationRecipientOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_discord_recipient(
    payload: NotificationRecipientCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_desktop_mode()
    recipient = NotificationRecipient(user_id=user.id, source="manual", **payload.model_dump())
    db.add(recipient)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Người nhận đã tồn tại") from exc
    await db.refresh(recipient)
    return recipient


@router.patch("/discord-recipients/{recipient_id}", response_model=NotificationRecipientOut)
async def update_discord_recipient(
    recipient_id: str,
    payload: NotificationRecipientUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_desktop_mode()
    recipient = await db.get(NotificationRecipient, recipient_id)
    if recipient is None or recipient.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy người nhận")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(recipient, field, value)
    await db.commit()
    await db.refresh(recipient)
    return recipient


@router.delete("/discord-recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_discord_recipient(
    recipient_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_desktop_mode()
    recipient = await db.get(NotificationRecipient, recipient_id)
    if recipient is None or recipient.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy người nhận")
    await db.delete(recipient)
    await db.commit()
