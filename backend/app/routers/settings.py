# plan: docs/plans/desktop_packaging.md
"""Màn "Cài đặt" cho chế độ desktop: nhập OpenAI key / Telegram bot token qua
UI thay vì sửa .env. CHỈ hoạt động khi RUN_MODE=desktop — ở chế độ SaaS mọi
route trả 404, vì Settings là singleton toàn tiến trình và việc 1 khách ghi
đè cấu hình sẽ rò rỉ sang khách khác (xem app_settings_service.py)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas import AppSettingsOut, AppSettingsUpdate
from app.services import app_settings_service as svc

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
    )


@router.put("", response_model=AppSettingsOut)
async def update_app_settings(
    payload: AppSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_desktop_mode()
    settings = get_settings()

    if payload.openai_api_key is not None:
        await svc.set_value(db, svc.OPENAI_API_KEY, payload.openai_api_key.strip())
        settings.openai_api_key = payload.openai_api_key.strip()

    if payload.telegram_bot_token is not None:
        await svc.set_value(db, svc.TELEGRAM_BOT_TOKEN, payload.telegram_bot_token.strip())
        settings.telegram_bot_token = payload.telegram_bot_token.strip()

    await db.commit()
    return AppSettingsOut(
        openai_api_key_set=bool(await svc.get_value(db, svc.OPENAI_API_KEY)),
        telegram_bot_token_set=bool(await svc.get_value(db, svc.TELEGRAM_BOT_TOKEN)),
    )
