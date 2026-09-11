# plan: docs/plans/phase2_dashboard_detail.md
"""Hộp thư "Nhắc tới" — bài Scout quét được có nhắc tên thương hiệu của khách."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.base import utcnow
from app.models.campaign import Campaign
from app.models.enums import MentionStatus
from app.models.mention import Mention
from app.models.user import User
from app.schemas import MentionListOut, MentionOut, MentionUnreadOut

router = APIRouter(prefix="/api/mentions", tags=["mentions"])


async def _owned_mention(mention_id: str, user: User, db: AsyncSession) -> Mention:
    mention = await db.get(Mention, mention_id)
    if mention is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt nhắc")
    campaign = await db.get(Campaign, mention.campaign_id)
    # 404 (không phải 403) cho tài nguyên của người khác — không lộ id có tồn tại.
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt nhắc")
    return mention


@router.get("", response_model=MentionListOut)
async def list_mentions(
    campaign_id: str | None = None,
    mention_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Danh sách lượt nhắc của người dùng, lọc theo chiến dịch/trạng thái."""
    base = (
        select(Mention)
        .join(Campaign, Campaign.id == Mention.campaign_id)
        .where(Campaign.user_id == user.id)
    )
    if campaign_id:
        base = base.where(Mention.campaign_id == campaign_id)
    if mention_status:
        base = base.where(Mention.status == mention_status)

    total = await db.execute(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.order_by(Mention.discovered_at.desc()).limit(limit).offset(offset)
    )
    return MentionListOut(
        items=[MentionOut.model_validate(m) for m in result.scalars().all()],
        total=int(total.scalar_one() or 0),
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=MentionUnreadOut)
async def unread_count(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Số lượt nhắc chưa đọc — nuôi badge trên sidebar."""
    result = await db.execute(
        select(func.count(Mention.id))
        .join(Campaign, Campaign.id == Mention.campaign_id)
        .where(
            Campaign.user_id == user.id,
            Mention.status == MentionStatus.NEW.value,
        )
    )
    return MentionUnreadOut(count=int(result.scalar_one() or 0))


@router.post("/{mention_id}/read", response_model=MentionOut)
async def mark_read(
    mention_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mention = await _owned_mention(mention_id, user, db)
    if mention.status == MentionStatus.NEW.value:
        mention.status = MentionStatus.READ.value
        mention.seen_at = utcnow()
    await db.commit()
    await db.refresh(mention)
    return mention


@router.post("/{mention_id}/archive", response_model=MentionOut)
async def archive(
    mention_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mention = await _owned_mention(mention_id, user, db)
    mention.status = MentionStatus.ARCHIVED.value
    if mention.seen_at is None:
        mention.seen_at = utcnow()
    await db.commit()
    await db.refresh(mention)
    return mention


@router.delete("/{mention_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mention(
    mention_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    mention = await _owned_mention(mention_id, user, db)
    await db.delete(mention)
    await db.commit()
