"""Quản lý clone: CRUD, upload cookie, kiểm tra session, chuyển trạng thái."""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, owned_clone
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, AccountTransition, HealthEventType
from app.models.user import User
from app.schemas import (
    CheckAllOut,
    CloneCreate,
    CloneDiagnosisOut,
    CloneHealthOut,
    CloneOut,
    CloneUpdate,
    CookieUploadOut,
    TransitionRequest,
)
from app.services.account_check import (
    diagnose,
    diagnose_many,
    has_backup,
    read_cookie_health,
    rollup,
)
from app.services.account_manager import AccountManager, InvalidTransitionError
from app.services.crypto import encrypt_cookies
from app.services.facebook_utils import (
    InvalidCookieFile,
    parse_cookie_payload,
    summarize_cookies,
)
from app.services.notification_service import NotificationService
from app.services.proxy_manager import ProxyManager
from app.services.quota import QuotaExceeded, SubscriptionInactive, ensure_can_add_clone
from app.services.warmup_service import warmup_progress

router = APIRouter(prefix="/api/clones", tags=["clones"])

MAX_COOKIE_BYTES = 2 * 1024 * 1024  # cookie thật chỉ vài KB; chặn file rác


def _to_out(clone: CloneAccount) -> CloneOut:
    data = CloneOut.model_validate(clone)
    data.has_cookies = bool(clone.cookie_data_encrypted)
    return data


async def _notifier(db: AsyncSession):
    """Callable gửi Telegram theo user_id — dùng cho AccountManager."""
    service = NotificationService()

    async def send(user_id: str, message: str) -> None:
        user = await db.get(User, user_id)
        if user and user.telegram_chat_id:
            await service.send_text(user.telegram_chat_id, message)

    return send


async def _sync_state_from_cookie(
    manager: AccountManager, clone: CloneAccount, cookie: dict
) -> bool:
    """Đối chiếu trạng thái clone với sức khoẻ cookie thật.

    Cookie hỏng mà clone vẫn ở ACTIVE/WARMING_UP là tình huống nguy hiểm nhất:
    scheduler cứ giao việc, worker cứ bị đá về trang đăng nhập, và lỗi chỉ lộ ra
    sau hàng chục lượt hỏng. Ở đây ta hạ trạng thái ngay khi phát hiện.

    Returns:
        True nếu clone vừa bị chuyển trạng thái.
    """
    running = (AccountState.ACTIVE.value, AccountState.WARMING_UP.value)
    if not cookie["ok"] and clone.status in running:
        await manager.transition(
            clone,
            AccountTransition.CHECKPOINT_DETECTED,
            f"Kiểm tra tài khoản: {cookie['reason'] or 'cookie không dùng được'}",
        )
        return True

    if cookie["ok"]:
        days = cookie["days_left"]
        note = "cookie hợp lệ"
        if days is not None:
            note += f", còn {days:g} ngày"
        await manager.log_event(clone, HealthEventType.LOGIN_OK, "Kiểm tra: " + note)
    else:
        await manager.log_event(
            clone, HealthEventType.CHECKPOINT, "Kiểm tra: " + cookie["reason"]
        )
    return False


@router.get("", response_model=list[CloneOut])
async def list_clones(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CloneAccount)
        .where(CloneAccount.user_id == user.id)
        .order_by(CloneAccount.created_at.asc())
    )
    return [_to_out(clone) for clone in result.scalars().all()]


@router.post("", response_model=CloneOut, status_code=status.HTTP_201_CREATED)
async def create_clone(
    payload: CloneCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await ensure_can_add_clone(db, user)
    except QuotaExceeded as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SubscriptionInactive as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    clone = CloneAccount(user_id=user.id, **payload.model_dump())
    db.add(clone)
    await db.flush()

    root = Path(get_settings().browser_profiles_root)
    clone.browser_profile_path = str(root / user.id / clone.id)
    await db.commit()
    await db.refresh(clone)
    return _to_out(clone)


@router.post("/check-all", response_model=CheckAllOut)
async def check_all(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Kiểm tra toàn bộ clone của người dùng trong một lần bấm.

    Cùng bộ luật với task Celery chạy nền, chỉ khác là chạy theo yêu cầu — để
    người dùng không phải chờ tới chu kỳ sau mới biết tài khoản của mình ra sao.
    """
    result = await db.execute(
        select(CloneAccount)
        .where(CloneAccount.user_id == user.id)
        .order_by(CloneAccount.created_at.asc())
    )
    clones = list(result.scalars().all())

    manager = AccountManager(db, notifier=await _notifier(db))
    transitioned: list[str] = []
    for clone in clones:
        cookie = read_cookie_health(clone)
        if await _sync_state_from_cookie(manager, clone, cookie):
            transitioned.append(clone.display_name)
    await db.commit()

    # Chẩn đoán SAU khi đã cập nhật trạng thái, nếu không báo cáo sẽ nói về
    # một hiện trạng vừa bị chính lệnh này thay đổi.
    reports = diagnose_many(clones)
    return CheckAllOut(
        summary=rollup(reports), reports=reports, transitioned=transitioned
    )


@router.get("/{clone_id}", response_model=CloneOut)
async def get_clone(clone: CloneAccount = Depends(owned_clone)):
    return _to_out(clone)


@router.put("/{clone_id}", response_model=CloneOut)
async def update_clone(
    payload: CloneUpdate,
    clone: CloneAccount = Depends(owned_clone),
    db: AsyncSession = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(clone, field, value)
    await db.commit()
    await db.refresh(clone)
    return _to_out(clone)


@router.delete("/{clone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_clone(
    clone: CloneAccount = Depends(owned_clone), db: AsyncSession = Depends(get_db)
):
    # Proxy phải được trả về pool trước khi xoá, nếu không nó "mất tích" mãi mãi.
    await ProxyManager(db).release_proxy(clone)
    await db.delete(clone)
    await db.commit()


@router.post("/{clone_id}/upload-cookie", response_model=CookieUploadOut)
async def upload_cookie(
    file: UploadFile = File(...),
    clone: CloneAccount = Depends(owned_clone),
    db: AsyncSession = Depends(get_db),
):
    """Nhận file cookie JSON hoặc Netscape, validate rồi lưu ở dạng mã hoá."""
    raw = await file.read(MAX_COOKIE_BYTES + 1)
    if len(raw) > MAX_COOKIE_BYTES:
        raise HTTPException(status_code=413, detail="File cookie lớn bất thường (>2MB)")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="File cookie không phải UTF-8") from exc

    try:
        cookies = parse_cookie_payload(text)
    except InvalidCookieFile as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    clone.cookie_data_encrypted = encrypt_cookies(cookies)
    summary = summarize_cookies(cookies)
    if summary.get("fb_user_id"):
        clone.fb_user_id = summary["fb_user_id"]
    manager = AccountManager(db, notifier=await _notifier(db))

    # Cookie hợp lệ = clone sẵn sàng bước vào chu kỳ ủ ấm.
    if clone.status == AccountState.ONBOARDING.value:
        await manager.transition(clone, AccountTransition.COOKIE_VALID, "Nạp cookie hợp lệ")
    await manager.log_event(clone, HealthEventType.LOGIN_OK, "Đã nạp cookie mới")

    Path(clone.browser_profile_path or ".").mkdir(parents=True, exist_ok=True)
    await db.commit()
    await db.refresh(clone)

    return CookieUploadOut(**summary, status=clone.status)


@router.get("/{clone_id}/health", response_model=CloneHealthOut)
async def clone_health(clone: CloneAccount = Depends(owned_clone)):
    return CloneHealthOut(
        id=clone.id,
        display_name=clone.display_name,
        status=clone.status,
        daily_comment_count=clone.daily_comment_count,
        daily_comment_limit=clone.daily_comment_limit,
        consecutive_failures=clone.consecutive_failures,
        warmup=warmup_progress(clone),
        cooldown_until=clone.cooldown_until,
        proxy_address=clone.proxy_address,
    )


@router.get("/{clone_id}/diagnose", response_model=CloneDiagnosisOut)
async def diagnose_clone(
    clone: CloneAccount = Depends(owned_clone), db: AsyncSession = Depends(get_db)
):
    """Phiếu chẩn đoán chi tiết — chỉ đọc, không thay đổi trạng thái gì."""
    return await _diagnosis_for(db, clone)


@router.post("/{clone_id}/check-session", response_model=CloneDiagnosisOut)
async def check_session(
    clone: CloneAccount = Depends(owned_clone), db: AsyncSession = Depends(get_db)
):
    """Kiểm tra tài khoản: cookie còn dùng được không, còn hạn bao lâu, vướng gì.

    Kiểm tra sâu (mở browser thật, dò checkpoint trên DOM) do Celery worker đảm
    nhiệm — API không được treo vài chục giây chỉ để chờ Chromium khởi động.
    """
    manager = AccountManager(db, notifier=await _notifier(db))
    cookie = read_cookie_health(clone)
    await _sync_state_from_cookie(manager, clone, cookie)
    await db.commit()
    await db.refresh(clone)
    return await _diagnosis_for(db, clone, cookie=cookie)


async def _diagnosis_for(
    db: AsyncSession, clone: CloneAccount, cookie: dict | None = None
) -> dict:
    """Chẩn đoán một clone, kèm bối cảnh "còn clone dự phòng không"."""
    siblings = await db.execute(
        select(CloneAccount).where(CloneAccount.user_id == clone.user_id)
    )
    return diagnose(
        clone,
        cookie=cookie if cookie is not None else read_cookie_health(clone),
        backup_available=has_backup(clone, list(siblings.scalars().all())),
    )


@router.post("/{clone_id}/transition", response_model=CloneOut)
async def transition_clone(
    payload: TransitionRequest,
    clone: CloneAccount = Depends(owned_clone),
    db: AsyncSession = Depends(get_db),
):
    """Chuyển trạng thái thủ công (ví dụ: đã xác minh xong checkpoint)."""
    try:
        event = AccountTransition(payload.event)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail=f"Sự kiện không hợp lệ: {payload.event}"
        ) from exc

    manager = AccountManager(db, notifier=await _notifier(db))
    try:
        await manager.transition(clone, event, payload.details)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(clone)
    return _to_out(clone)
