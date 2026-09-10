"""CRUD chiến dịch + group + kịch bản comment + bump (tài nguyên lồng nhau)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import (
    get_current_user,
    owned_campaign,
    owned_group,
    owned_script,
)
from app.models.campaign import BumpSchedule, Campaign, CampaignGroup, CommentScript
from app.models.enums import GroupStatus, ScriptType
from app.models.user import User
from app.schemas import (
    BumpCreate,
    BumpOut,
    BumpUpdate,
    CampaignCreate,
    CampaignOut,
    CampaignUpdate,
    GroupCreate,
    GroupOut,
    GroupUpdate,
    ExpandOut,
    LintOut,
    LintRequest,
    ScriptCreate,
    ScriptOut,
    ScriptPreviewOut,
    ScriptUpdate,
)
from app.services.facebook_utils import InvalidGroupURL, parse_group_ref
from app.services.quota import (
    QuotaExceeded,
    SubscriptionInactive,
    ensure_bump_enabled,
    ensure_can_add_group,
    require_active_subscription,
)
from app.services.script_engine import (
    ScriptError,
    count_variants,
    expand_all,
    lint_template,
    preview_variants,
)

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


def _quota_error(exc: Exception) -> HTTPException:
    code = 402 if isinstance(exc, SubscriptionInactive) else 403
    return HTTPException(status_code=code, detail=str(exc))


# ── Campaign ───────────────────────────────────────────────────────────────
@router.get("", response_model=list[CampaignOut])
async def list_campaigns(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Campaign)
        .where(Campaign.user_id == user.id)
        .order_by(Campaign.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await require_active_subscription(db, user)
    except SubscriptionInactive as exc:
        raise _quota_error(exc) from exc

    campaign = Campaign(user_id=user.id, **payload.model_dump())
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.get("/{campaign_id}", response_model=CampaignOut)
async def get_campaign(campaign: Campaign = Depends(owned_campaign)):
    return campaign


@router.put("/{campaign_id}", response_model=CampaignOut)
async def update_campaign(
    payload: CampaignUpdate,
    campaign: Campaign = Depends(owned_campaign),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    delay_min = data.get("delay_min_seconds", campaign.delay_min_seconds)
    delay_max = data.get("delay_max_seconds", campaign.delay_max_seconds)
    if delay_max < delay_min:
        raise HTTPException(
            status_code=422, detail="delay_max_seconds phải >= delay_min_seconds"
        )
    for field, value in data.items():
        setattr(campaign, field, value)
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign: Campaign = Depends(owned_campaign), db: AsyncSession = Depends(get_db)
):
    await db.delete(campaign)
    await db.commit()


@router.post("/{campaign_id}/activate", response_model=CampaignOut)
async def activate_campaign(
    campaign: Campaign = Depends(owned_campaign),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bật chiến dịch. Không có group thì bật cũng vô nghĩa nên chặn sớm."""
    try:
        await require_active_subscription(db, user)
    except SubscriptionInactive as exc:
        raise _quota_error(exc) from exc

    groups = await db.execute(
        select(CampaignGroup.id).where(CampaignGroup.campaign_id == campaign.id)
    )
    if not groups.scalars().first():
        raise HTTPException(
            status_code=422, detail="Chiến dịch chưa có group nào để quét"
        )

    campaign.is_active = True
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/pause", response_model=CampaignOut)
async def pause_campaign(
    campaign: Campaign = Depends(owned_campaign), db: AsyncSession = Depends(get_db)
):
    campaign.is_active = False
    await db.commit()
    await db.refresh(campaign)
    return campaign


# ── Group ──────────────────────────────────────────────────────────────────
@router.get("/{campaign_id}/groups", response_model=list[GroupOut])
async def list_groups(
    campaign: Campaign = Depends(owned_campaign), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CampaignGroup)
        .where(CampaignGroup.campaign_id == campaign.id)
        .order_by(CampaignGroup.created_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/{campaign_id}/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED
)
async def add_group(
    payload: GroupCreate,
    campaign: Campaign = Depends(owned_campaign),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        group_key, canonical_url = parse_group_ref(payload.group_url)
    except InvalidGroupURL as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        await ensure_can_add_group(db, user)
    except (QuotaExceeded, SubscriptionInactive) as exc:
        raise _quota_error(exc) from exc

    duplicate = await db.execute(
        select(CampaignGroup.id).where(
            CampaignGroup.campaign_id == campaign.id,
            CampaignGroup.group_key == group_key,
        )
    )
    if duplicate.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Group đã có trong chiến dịch này")

    group = CampaignGroup(
        campaign_id=campaign.id,
        group_url=canonical_url,
        group_key=group_key,
        group_name=payload.group_name or group_key,
        scan_interval_minutes=payload.scan_interval_minutes,
        status=GroupStatus.ACTIVE.value,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group


@router.put("/{campaign_id}/groups/{group_id}", response_model=GroupOut)
async def update_group(
    payload: GroupUpdate,
    group: CampaignGroup = Depends(owned_group),
    db: AsyncSession = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(group, field, value)
    await db.commit()
    await db.refresh(group)
    return group


@router.delete(
    "/{campaign_id}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_group(
    group: CampaignGroup = Depends(owned_group), db: AsyncSession = Depends(get_db)
):
    await db.delete(group)
    await db.commit()


# ── Script ─────────────────────────────────────────────────────────────────
@router.get("/{campaign_id}/scripts", response_model=list[ScriptOut])
async def list_scripts(
    campaign: Campaign = Depends(owned_campaign), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(CommentScript)
        .where(CommentScript.campaign_id == campaign.id)
        .order_by(CommentScript.is_default.desc(), CommentScript.created_at.asc())
    )
    return list(result.scalars().all())


async def _clear_other_defaults(db: AsyncSession, campaign_id: str, keep_id: str) -> None:
    result = await db.execute(
        select(CommentScript).where(
            CommentScript.campaign_id == campaign_id,
            CommentScript.id != keep_id,
            CommentScript.is_default.is_(True),
        )
    )
    for script in result.scalars().all():
        script.is_default = False


@router.post(
    "/{campaign_id}/scripts",
    response_model=ScriptOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_script(
    payload: ScriptCreate,
    campaign: Campaign = Depends(owned_campaign),
    db: AsyncSession = Depends(get_db),
):
    if payload.type == ScriptType.SPINTAX.value:
        try:
            preview_variants(payload.template_content, count=1)
        except ScriptError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    script = CommentScript(campaign_id=campaign.id, **payload.model_dump())
    db.add(script)
    await db.flush()
    if script.is_default:
        await _clear_other_defaults(db, campaign.id, script.id)
    await db.commit()
    await db.refresh(script)
    return script


@router.put("/{campaign_id}/scripts/{script_id}", response_model=ScriptOut)
async def update_script(
    payload: ScriptUpdate,
    script: CommentScript = Depends(owned_script),
    db: AsyncSession = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(script, field, value)
    if script.is_default:
        await _clear_other_defaults(db, script.campaign_id, script.id)
    await db.commit()
    await db.refresh(script)
    return script


@router.delete(
    "/{campaign_id}/scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_script(
    script: CommentScript = Depends(owned_script), db: AsyncSession = Depends(get_db)
):
    await db.delete(script)
    await db.commit()


EXPAND_LIMIT = 300


def _lint_payload(template: str, samples: int, max_per_day: int) -> LintOut:
    report = lint_template(template)
    report["samples"] = report["samples"][:samples]
    # Bao nhiêu ngày chạy hết công suất mà chưa phải lặp lại một câu nào?
    # Đây là con số khách quan tâm nhất khi cân nhắc "mẫu này đã đủ đa dạng chưa".
    per_day = max(1, max_per_day)
    return LintOut(**report, days_without_repeat=round(report["total_variants"] / per_day, 1))


@router.post("/{campaign_id}/scripts/lint", response_model=LintOut)
async def lint_draft_script(
    payload: LintRequest, campaign: Campaign = Depends(owned_campaign)
):
    """Soi mẫu spintax CHƯA lưu, phục vụ ô soạn thảo trực tiếp.

    Không ném 422 khi mẫu sai: trả về danh sách lỗi/cảnh báo để người dùng
    thấy hết vấn đề cùng lúc trong lúc gõ.
    """
    return _lint_payload(
        payload.template_content, payload.sample_count, campaign.max_comments_per_day
    )


@router.post("/{campaign_id}/scripts/{script_id}/lint", response_model=LintOut)
async def lint_saved_script(
    campaign: Campaign = Depends(owned_campaign),
    script: CommentScript = Depends(owned_script),
):
    """Soi mẫu của một kịch bản đã lưu."""
    return _lint_payload(script.template_content, 5, campaign.max_comments_per_day)


@router.post("/{campaign_id}/scripts/{script_id}/expand", response_model=ExpandOut)
async def expand_script(script: CommentScript = Depends(owned_script)):
    """Liệt kê toàn bộ biến thể để khách soi bằng mắt trước khi bật chiến dịch."""
    if script.type != ScriptType.SPINTAX.value:
        raise HTTPException(
            status_code=422, detail="Chỉ kịch bản spintax mới liệt kê được biến thể."
        )
    try:
        variants = expand_all(script.template_content, limit=EXPAND_LIMIT)
    except ScriptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    total = count_variants(script.template_content)
    return ExpandOut(variants=variants, total_variants=total, truncated=total > len(variants))


@router.post("/{campaign_id}/scripts/{script_id}/preview", response_model=ScriptPreviewOut)
async def preview_script(
    count: int = 3, script: CommentScript = Depends(owned_script)
):
    """Sinh thử vài mẫu comment để khách xem trước khi bật chiến dịch."""
    if script.type != ScriptType.SPINTAX.value:
        raise HTTPException(
            status_code=422,
            detail="Chỉ kịch bản spintax mới xem trước offline được; "
            "kịch bản AI sinh nội dung theo từng bài viết cụ thể.",
        )
    try:
        variants = preview_variants(script.template_content, count=max(1, min(count, 10)))
    except ScriptError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ScriptPreviewOut(
        variants=variants, total_variants=count_variants(script.template_content)
    )


# ── Bump schedule ──────────────────────────────────────────────────────────
@router.get("/{campaign_id}/bumps", response_model=list[BumpOut])
async def list_bumps(
    campaign: Campaign = Depends(owned_campaign), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(BumpSchedule)
        .where(BumpSchedule.campaign_id == campaign.id)
        .order_by(BumpSchedule.created_at.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/{campaign_id}/bumps", response_model=BumpOut, status_code=status.HTTP_201_CREATED
)
async def create_bump(
    payload: BumpCreate,
    campaign: Campaign = Depends(owned_campaign),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await ensure_bump_enabled(db, user)
    except (QuotaExceeded, SubscriptionInactive) as exc:
        raise _quota_error(exc) from exc

    if not payload.bump_messages:
        raise HTTPException(status_code=422, detail="Cần ít nhất 1 nội dung bump")

    bump = BumpSchedule(campaign_id=campaign.id, **payload.model_dump())
    db.add(bump)
    await db.commit()
    await db.refresh(bump)
    return bump


async def _owned_bump(bump_id: str, campaign: Campaign, db: AsyncSession) -> BumpSchedule:
    bump = await db.get(BumpSchedule, bump_id)
    if bump is None or bump.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch bump")
    return bump


@router.put("/{campaign_id}/bumps/{bump_id}", response_model=BumpOut)
async def update_bump(
    bump_id: str,
    payload: BumpUpdate,
    campaign: Campaign = Depends(owned_campaign),
    db: AsyncSession = Depends(get_db),
):
    bump = await _owned_bump(bump_id, campaign, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(bump, field, value)
    await db.commit()
    await db.refresh(bump)
    return bump


@router.delete(
    "/{campaign_id}/bumps/{bump_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_bump(
    bump_id: str,
    campaign: Campaign = Depends(owned_campaign),
    db: AsyncSession = Depends(get_db),
):
    bump = await _owned_bump(bump_id, campaign, db)
    await db.delete(bump)
    await db.commit()
