# plan: docs/plans/phase2_dashboard_detail.md
"""Săn lead qua comment — bình luận dưới bài có khớp từ khoá của khách."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import utcnow
from app.models.campaign import Campaign
from app.models.enums import LeadStatus
from app.models.lead import CommentLead
from app.models.user import User
from app.schemas import LeadListOut, LeadOut, LeadUnreadOut

router = APIRouter(prefix="/api/leads", tags=["leads"])


async def _owned_lead(lead_id: str, user: User, db: AsyncSession) -> CommentLead:
    lead = await db.get(CommentLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lead")
    campaign = await db.get(Campaign, lead.campaign_id)
    # 404 (không phải 403) cho tài nguyên của người khác — không lộ id có tồn tại.
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy lead")
    return lead


@router.get("", response_model=LeadListOut)
async def list_leads(
    campaign_id: str | None = None,
    lead_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Danh sách lead của người dùng, lọc theo chiến dịch/trạng thái."""
    base = (
        select(CommentLead)
        .join(Campaign, Campaign.id == CommentLead.campaign_id)
        .where(Campaign.user_id == user.id)
    )
    if campaign_id:
        base = base.where(CommentLead.campaign_id == campaign_id)
    if lead_status:
        base = base.where(CommentLead.status == lead_status)

    total = await db.execute(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.order_by(CommentLead.discovered_at.desc()).limit(limit).offset(offset)
    )
    return LeadListOut(
        items=[LeadOut.model_validate(m) for m in result.scalars().all()],
        total=int(total.scalar_one() or 0),
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=LeadUnreadOut)
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Số lead chưa đọc — nuôi badge trên sidebar."""
    result = await db.execute(
        select(func.count(CommentLead.id))
        .join(Campaign, Campaign.id == CommentLead.campaign_id)
        .where(
            Campaign.user_id == user.id,
            CommentLead.status == LeadStatus.NEW.value,
        )
    )
    return LeadUnreadOut(count=int(result.scalar_one() or 0))


@router.post("/{lead_id}/read", response_model=LeadOut)
async def mark_read(
    lead_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lead = await _owned_lead(lead_id, user, db)
    if lead.status == LeadStatus.NEW.value:
        lead.status = LeadStatus.READ.value
        lead.seen_at = utcnow()
    await db.commit()
    await db.refresh(lead)
    return lead


@router.post("/{lead_id}/archive", response_model=LeadOut)
async def archive(
    lead_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lead = await _owned_lead(lead_id, user, db)
    lead.status = LeadStatus.ARCHIVED.value
    if lead.seen_at is None:
        lead.seen_at = utcnow()
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    lead_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    lead = await _owned_lead(lead_id, user, db)
    await db.delete(lead)
    await db.commit()
