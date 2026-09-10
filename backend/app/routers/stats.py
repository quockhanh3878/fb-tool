"""Thống kê dashboard + báo cáo hiệu quả group."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.campaign import Campaign, CampaignGroup
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState, CommentStatus, PostStatus
from app.models.post import CommentAction, DiscoveredPost
from app.models.user import User
from app.schemas import DailyPoint, DashboardStats, GroupPerformance

router = APIRouter(prefix="/api/stats", tags=["stats"])

MATCHED_STATUSES = (
    PostStatus.NOTIFIED.value,
    PostStatus.COMMENTED.value,
)


def _day_bounds(days_ago: int) -> tuple[datetime, datetime]:
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - timedelta(days=days_ago)
    return start, start + timedelta(days=1)


async def _scalar(db: AsyncSession, stmt) -> int:
    return int((await db.execute(stmt)).scalar_one() or 0)


def _user_posts_stmt(user_id: str):
    return (
        select(func.count(DiscoveredPost.id))
        .join(Campaign, Campaign.id == DiscoveredPost.campaign_id)
        .where(Campaign.user_id == user_id)
    )


def _user_actions_stmt(user_id: str):
    return (
        select(func.count(CommentAction.id))
        .join(DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id)
        .join(Campaign, Campaign.id == DiscoveredPost.campaign_id)
        .where(Campaign.user_id == user_id)
    )


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(
    days: int = Query(default=7, ge=1, le=90),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Số liệu tổng quan + xu hướng N ngày cho trang Dashboard."""
    start_today, end_today = _day_bounds(0)

    posts_today = await _scalar(
        db,
        _user_posts_stmt(user.id).where(
            DiscoveredPost.discovered_at >= start_today,
            DiscoveredPost.discovered_at < end_today,
        ),
    )
    matched_today = await _scalar(
        db,
        _user_posts_stmt(user.id).where(
            DiscoveredPost.discovered_at >= start_today,
            DiscoveredPost.discovered_at < end_today,
            DiscoveredPost.status.in_(MATCHED_STATUSES),
        ),
    )
    comments_today = await _scalar(
        db,
        _user_actions_stmt(user.id).where(
            CommentAction.executed_at >= start_today,
            CommentAction.executed_at < end_today,
            CommentAction.status == CommentStatus.SUCCESS.value,
        ),
    )
    attempts_today = await _scalar(
        db,
        _user_actions_stmt(user.id).where(
            CommentAction.executed_at >= start_today,
            CommentAction.executed_at < end_today,
        ),
    )

    active_campaigns = await _scalar(
        db,
        select(func.count(Campaign.id)).where(
            Campaign.user_id == user.id, Campaign.is_active.is_(True)
        ),
    )
    total_groups = await _scalar(
        db,
        select(func.count(CampaignGroup.id))
        .join(Campaign, Campaign.id == CampaignGroup.campaign_id)
        .where(Campaign.user_id == user.id),
    )
    clones_total = await _scalar(
        db, select(func.count(CloneAccount.id)).where(CloneAccount.user_id == user.id)
    )
    clones_healthy = await _scalar(
        db,
        select(func.count(CloneAccount.id)).where(
            CloneAccount.user_id == user.id,
            CloneAccount.status.in_(
                (AccountState.ACTIVE.value, AccountState.WARMING_UP.value)
            ),
        ),
    )

    trend: list[DailyPoint] = []
    for offset in range(days - 1, -1, -1):
        start, end = _day_bounds(offset)
        trend.append(
            DailyPoint(
                date=start.date().isoformat(),
                posts=await _scalar(
                    db,
                    _user_posts_stmt(user.id).where(
                        DiscoveredPost.discovered_at >= start,
                        DiscoveredPost.discovered_at < end,
                    ),
                ),
                matched=await _scalar(
                    db,
                    _user_posts_stmt(user.id).where(
                        DiscoveredPost.discovered_at >= start,
                        DiscoveredPost.discovered_at < end,
                        DiscoveredPost.status.in_(MATCHED_STATUSES),
                    ),
                ),
                comments=await _scalar(
                    db,
                    _user_actions_stmt(user.id).where(
                        CommentAction.executed_at >= start,
                        CommentAction.executed_at < end,
                        CommentAction.status == CommentStatus.SUCCESS.value,
                    ),
                ),
            )
        )

    return DashboardStats(
        posts_today=posts_today,
        matched_today=matched_today,
        comments_today=comments_today,
        success_rate=round(comments_today / attempts_today, 3) if attempts_today else 0.0,
        active_campaigns=active_campaigns,
        total_groups=total_groups,
        clones_healthy=clones_healthy,
        clones_total=clones_total,
        trend=trend,
    )


@router.get("/groups", response_model=list[GroupPerformance])
async def group_performance(
    limit: int = Query(default=5, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Top group hiệu quả nhất theo tỉ lệ bài phù hợp / bài quét."""
    result = await db.execute(
        select(CampaignGroup)
        .join(Campaign, Campaign.id == CampaignGroup.campaign_id)
        .where(Campaign.user_id == user.id)
    )
    rows: list[GroupPerformance] = []
    for group in result.scalars().all():
        posts = await _scalar(
            db,
            select(func.count(DiscoveredPost.id)).where(
                DiscoveredPost.campaign_group_id == group.id
            ),
        )
        matched = await _scalar(
            db,
            select(func.count(DiscoveredPost.id)).where(
                DiscoveredPost.campaign_group_id == group.id,
                DiscoveredPost.status.in_(MATCHED_STATUSES),
            ),
        )
        rows.append(
            GroupPerformance(
                group_id=group.id,
                group_name=group.group_name or group.group_key,
                posts=posts,
                matched=matched,
                match_rate=round(matched / posts, 3) if posts else 0.0,
            )
        )

    rows.sort(key=lambda r: (r.match_rate, r.matched), reverse=True)
    return rows[:limit]


@router.get("/status-breakdown")
async def status_breakdown(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Phân bố trạng thái bài viết — dữ liệu cho biểu đồ tròn."""
    breakdown = {}
    for status_value in PostStatus:
        breakdown[status_value.value] = await _scalar(
            db, _user_posts_stmt(user.id).where(DiscoveredPost.status == status_value.value)
        )
    return breakdown
