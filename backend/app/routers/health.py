"""Health Monitor (Phase 3 — Task 3.7): sức khoẻ clone, cảnh báo, pool proxy."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.clone_account import AccountHealthLog, CloneAccount, Proxy
from app.models.enums import HealthEventType, ProxyStatus
from app.models.user import User
from app.schemas import (
    CloneDiagnosisOut,
    CloneHealthOut,
    HealthEventOut,
    HealthSummaryOut,
    ProxyCreate,
    ProxyOut,
)
from app.services.account_check import diagnose_many, rollup
from app.services.proxy_manager import NoProxyAvailable, ProxyManager
from app.services.warmup_service import warmup_progress

router = APIRouter(prefix="/api/health", tags=["health"])

# Sự kiện đáng để người dùng phải ngó tới ngay.
ALERT_EVENTS = (
    HealthEventType.CHECKPOINT.value,
    HealthEventType.BANNED.value,
    HealthEventType.SHADOWBAN.value,
    HealthEventType.RATE_LIMITED.value,
    HealthEventType.COMMENT_BLOCKED.value,
)


async def _user_clone_ids(db: AsyncSession, user_id: str) -> list[str]:
    result = await db.execute(
        select(CloneAccount.id).where(CloneAccount.user_id == user_id)
    )
    return [row[0] for row in result.all()]


@router.get("/overview", response_model=list[CloneHealthOut])
async def overview(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CloneAccount)
        .where(CloneAccount.user_id == user.id)
        .order_by(CloneAccount.created_at.asc())
    )
    return [
        CloneHealthOut(
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
        for clone in result.scalars().all()
    ]


@router.get("/summary", response_model=HealthSummaryOut)
async def summary(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Một màn hình duy nhất trả lời: "hệ thống của tôi hôm nay có ổn không?"

    Chỉ đọc — không đụng vào trạng thái clone. Muốn vừa kiểm tra vừa sửa trạng
    thái thì dùng `POST /api/clones/check-all`.
    """
    result = await db.execute(
        select(CloneAccount)
        .where(CloneAccount.user_id == user.id)
        .order_by(CloneAccount.created_at.asc())
    )
    data = rollup(diagnose_many(list(result.scalars().all())))

    clone_ids = await _user_clone_ids(db, user.id)
    pending = 0
    if clone_ids:
        rows = await db.execute(
            select(func.count(AccountHealthLog.id)).where(
                AccountHealthLog.clone_account_id.in_(clone_ids),
                AccountHealthLog.event_type.in_(ALERT_EVENTS),
                AccountHealthLog.acknowledged.is_(False),
            )
        )
        pending = int(rows.scalar_one() or 0)
    data["unacknowledged_alerts"] = pending
    return data


@router.get("/diagnostics", response_model=list[CloneDiagnosisOut])
async def diagnostics(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Phiếu chẩn đoán của từng clone — nguồn dữ liệu cho bảng «Tình trạng»."""
    result = await db.execute(
        select(CloneAccount)
        .where(CloneAccount.user_id == user.id)
        .order_by(CloneAccount.created_at.asc())
    )
    return diagnose_many(list(result.scalars().all()))


@router.get("/clone/{clone_id}/timeline", response_model=list[HealthEventOut])
async def clone_timeline(
    clone_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clone = await db.get(CloneAccount, clone_id)
    if clone is None or clone.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy clone")

    result = await db.execute(
        select(AccountHealthLog)
        .where(AccountHealthLog.clone_account_id == clone_id)
        .order_by(AccountHealthLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.get("/alerts", response_model=list[HealthEventOut])
async def alerts(
    limit: int = Query(default=30, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cảnh báo chưa xử lý của toàn bộ clone thuộc người dùng."""
    clone_ids = await _user_clone_ids(db, user.id)
    if not clone_ids:
        return []
    result = await db.execute(
        select(AccountHealthLog)
        .where(
            AccountHealthLog.clone_account_id.in_(clone_ids),
            AccountHealthLog.event_type.in_(ALERT_EVENTS),
            AccountHealthLog.acknowledged.is_(False),
        )
        .order_by(AccountHealthLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/alerts/ack-all")
async def acknowledge_all(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Đánh dấu đã xử lý toàn bộ cảnh báo đang treo."""
    clone_ids = await _user_clone_ids(db, user.id)
    if not clone_ids:
        return {"acknowledged": 0}
    result = await db.execute(
        select(AccountHealthLog).where(
            AccountHealthLog.clone_account_id.in_(clone_ids),
            AccountHealthLog.event_type.in_(ALERT_EVENTS),
            AccountHealthLog.acknowledged.is_(False),
        )
    )
    rows = list(result.scalars().all())
    for row in rows:
        row.acknowledged = True
    await db.commit()
    return {"acknowledged": len(rows)}


@router.post("/alerts/{alert_id}/ack", response_model=HealthEventOut)
async def acknowledge_alert(
    alert_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    alert = await db.get(AccountHealthLog, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    clone = await db.get(CloneAccount, alert.clone_account_id)
    if clone is None or clone.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy cảnh báo")
    alert.acknowledged = True
    await db.commit()
    await db.refresh(alert)
    return alert


# ── Proxy pool ─────────────────────────────────────────────────────────────
@router.get("/proxies", response_model=list[ProxyOut])
async def list_proxies(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Proxy)
        .where((Proxy.owner_user_id == user.id) | (Proxy.owner_user_id.is_(None)))
        .order_by(Proxy.created_at.asc())
    )
    return list(result.scalars().all())


@router.post("/proxies", response_model=ProxyOut, status_code=status.HTTP_201_CREATED)
async def add_proxy(
    payload: ProxyCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Proxy).where(Proxy.address == payload.address))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Proxy này đã có trong pool")

    proxy = Proxy(
        address=payload.address,
        type=payload.type,
        country=payload.country,
        owner_user_id=user.id,
        status=ProxyStatus.AVAILABLE.value,
    )
    db.add(proxy)
    await db.commit()
    await db.refresh(proxy)
    return proxy


@router.post("/proxies/assign/{clone_id}", response_model=ProxyOut)
async def assign_proxy(
    clone_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clone = await db.get(CloneAccount, clone_id)
    if clone is None or clone.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy clone")
    try:
        proxy = await ProxyManager(db).assign_proxy(clone)
    except NoProxyAvailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(proxy)
    return proxy


@router.post("/proxies/rotate/{clone_id}", response_model=ProxyOut)
async def rotate_proxy(
    clone_id: str,
    reason: str = Query(default="manual_rotation", max_length=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    clone = await db.get(CloneAccount, clone_id)
    if clone is None or clone.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy clone")
    try:
        proxy = await ProxyManager(db).rotate_proxy(clone, reason)
    except NoProxyAvailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(proxy)
    return proxy


@router.get("/proxies/overview")
async def proxy_overview(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    return await ProxyManager(db).pool_overview(user.id)
