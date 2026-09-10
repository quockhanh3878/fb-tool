"""Feed bài viết đã phát hiện + nộp bài từ Scout + ứng tuyển thủ công."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, owned_campaign
from app.models.base import utcnow
from app.models.campaign import Campaign, CampaignGroup
from app.models.clone_account import CloneAccount
from app.models.enums import CloneRole, CommentStatus, PostStatus, PublishStatus
from app.models.post import CommentAction, DiscoveredPost, PostPublish
from app.models.user import User
from app.schemas import (
    ApplyRequest,
    CommentActionOut,
    IngestPostsRequest,
    IngestResultOut,
    PostListOut,
    PostOut,
    PostPublishCreate,
    PostPublishListOut,
    PostPublishOut,
    PostPublishUpdate,
)
from app.services.ai_service import AIService
from app.services.notification_service import NotificationService
from app.services.pipeline import (
    build_comment,
    count_today_actions,
    ingest_raw_posts,
    process_campaign_posts,
    queue_comment,
)
from app.services.publisher_service import execute_publish
from app.services.script_engine import ScriptError, validate_comment

router = APIRouter(prefix="/api", tags=["posts"])


def _ai_service() -> AIService:
    settings = get_settings()
    return AIService(settings.openai_api_key, settings.openai_model)


@router.get("/posts", response_model=PostListOut)
async def list_posts(
    campaign_id: str | None = None,
    group_id: str | None = None,
    post_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Feed bài viết của người dùng, lọc theo chiến dịch/group/trạng thái."""
    base = (
        select(DiscoveredPost)
        .join(Campaign, Campaign.id == DiscoveredPost.campaign_id)
        .where(Campaign.user_id == user.id)
    )
    if campaign_id:
        base = base.where(DiscoveredPost.campaign_id == campaign_id)
    if group_id:
        base = base.where(DiscoveredPost.campaign_group_id == group_id)
    if post_status:
        base = base.where(DiscoveredPost.status == post_status)

    total = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    result = await db.execute(
        base.order_by(DiscoveredPost.discovered_at.desc()).limit(limit).offset(offset)
    )
    return PostListOut(
        items=[PostOut.model_validate(p) for p in result.scalars().all()],
        total=int(total.scalar_one() or 0),
        limit=limit,
        offset=offset,
    )


async def _owned_post(post_id: str, user: User, db: AsyncSession) -> DiscoveredPost:
    post = await db.get(DiscoveredPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
    campaign = await db.get(Campaign, post.campaign_id)
    if campaign is None or campaign.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
    return post


@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _owned_post(post_id, user, db)


@router.get("/posts/{post_id}/actions", response_model=list[CommentActionOut])
async def post_actions(
    post_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _owned_post(post_id, user, db)
    result = await db.execute(
        select(CommentAction)
        .where(CommentAction.discovered_post_id == post.id)
        .order_by(CommentAction.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/posts/{post_id}/apply", response_model=CommentActionOut)
async def apply_to_post(
    post_id: str,
    payload: ApplyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ứng tuyển bài viết: sinh comment (hoặc dùng nội dung người dùng gõ) và xếp hàng."""
    post = await _owned_post(post_id, user, db)
    campaign = await db.get(Campaign, post.campaign_id)

    quota = int(campaign.max_comments_per_day or 20)
    used = await count_today_actions(db, campaign.id)
    if used >= quota:
        raise HTTPException(
            status_code=429,
            detail=f"Đã dùng hết quota hôm nay ({used}/{quota}). Thử lại vào ngày mai.",
        )

    if payload.comment_text:
        try:
            comment_text = validate_comment(payload.comment_text)
        except ScriptError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        script = None
    else:
        comment_text, script = await build_comment(db, campaign, post, _ai_service())
        if not comment_text:
            raise HTTPException(
                status_code=422,
                detail="Không sinh được comment — kiểm tra kịch bản hoặc OpenAI API key.",
            )

    action = await queue_comment(
        db, campaign, post, comment_text, script, clone_id=payload.clone_id
    )
    await db.commit()
    await db.refresh(action)
    return action


@router.post("/posts/{post_id}/skip", response_model=PostOut)
async def skip_post(
    post_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post = await _owned_post(post_id, user, db)
    post.status = PostStatus.SKIPPED.value
    post.ai_reason = "user_skipped"
    await db.commit()
    await db.refresh(post)
    return post


@router.post(
    "/campaigns/{campaign_id}/ingest",
    response_model=IngestResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_posts(
    payload: IngestPostsRequest,
    campaign: Campaign = Depends(owned_campaign),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Scout worker nộp bài thô; API chạy trọn pipeline lọc → thông báo/xếp hàng."""
    group = await db.get(CampaignGroup, payload.group_id)
    if group is None or group.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy group")

    fresh = await ingest_raw_posts(db, campaign, group, payload.posts)
    stats = await process_campaign_posts(
        db, campaign, fresh, _ai_service(), notifier=NotificationService(), user=user
    )
    await db.commit()
    return IngestResultOut(ingested=len(fresh), **stats)


@router.get("/queue", response_model=list[CommentActionOut])
async def comment_queue(
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hàng đợi comment đang chờ Shooter xử lý."""
    result = await db.execute(
        select(CommentAction)
        .join(DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id)
        .join(Campaign, Campaign.id == DiscoveredPost.campaign_id)
        .where(
            Campaign.user_id == user.id,
            CommentAction.status == CommentStatus.QUEUED.value,
        )
        .order_by(CommentAction.scheduled_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("/queue/{action_id}/cancel", response_model=CommentActionOut)
async def cancel_action(
    action_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await db.get(CommentAction, action_id)
    if action is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy lượt comment")
    await _owned_post(action.discovered_post_id, user, db)
    if action.status != CommentStatus.QUEUED.value:
        raise HTTPException(
            status_code=409,
            detail=f"Chỉ huỷ được lượt đang chờ (hiện tại: {action.status})",
        )
    action.status = CommentStatus.FAILED.value
    action.error_message = "cancelled_by_user"
    action.executed_at = utcnow()
    await db.commit()
    await db.refresh(action)
    return action


# ── Đăng bài (Publishing / Seeding) ───────────────────────────────────────
@router.get("/publishing", response_model=PostPublishListOut)
@router.get("/posts/publishing", response_model=PostPublishListOut)
async def list_published_posts(
    campaign_id: str | None = None,
    publish_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Danh sách các bài đăng tự động / theo lịch của người dùng."""
    base = select(PostPublish).where(PostPublish.user_id == user.id)
    if campaign_id:
        base = base.where(PostPublish.campaign_id == campaign_id)
    if publish_status:
        base = base.where(PostPublish.status == publish_status)

    total = await db.execute(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.order_by(PostPublish.created_at.desc()).limit(limit).offset(offset)
    )
    return PostPublishListOut(
        items=[PostPublishOut.model_validate(p) for p in result.scalars().all()],
        total=int(total.scalar_one() or 0),
    )


@router.post("/publishing", response_model=PostPublishOut, status_code=status.HTTP_201_CREATED)
@router.post("/posts/publishing", response_model=PostPublishOut, status_code=status.HTTP_201_CREATED)
async def create_published_post(
    payload: PostPublishCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tạo bài đăng mới vào nhóm với kịch bản Spintax."""
    if payload.campaign_id:
        campaign = await db.get(Campaign, payload.campaign_id)
        if campaign is None or campaign.user_id != user.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")

    if payload.clone_account_id:
        clone = await db.get(CloneAccount, payload.clone_account_id)
        if clone is None or clone.user_id != user.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản clone")
        if clone.role not in (CloneRole.POSTER.value, CloneRole.ALL.value):
            raise HTTPException(
                status_code=422,
                detail=f"Tài khoản clone '{clone.display_name}' có vai trò '{clone.role}', không thể dùng để đăng bài (cần role 'poster' hoặc 'all').",
            )

    post_pub = PostPublish(
        user_id=user.id,
        campaign_id=payload.campaign_id,
        clone_account_id=payload.clone_account_id,
        title=payload.title,
        content_template=payload.content_template,
        media_urls=payload.media_urls,
        target_groups=payload.target_groups,
        status=PublishStatus.SCHEDULED.value,
        scheduled_at=payload.scheduled_at or utcnow(),
    )
    db.add(post_pub)
    await db.commit()
    await db.refresh(post_pub)
    return post_pub


@router.get("/publishing/{publish_id}", response_model=PostPublishOut)
@router.get("/posts/publishing/{publish_id}", response_model=PostPublishOut)
async def get_published_post(
    publish_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_pub = await db.get(PostPublish, publish_id)
    if post_pub is None or post_pub.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài đăng")
    return post_pub


@router.post("/publishing/{publish_id}/publish-now", response_model=PostPublishOut)
@router.post("/posts/publishing/{publish_id}/publish-now", response_model=PostPublishOut)
async def publish_post_now(
    publish_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Đăng bài ngay lập tức không cần đợi lịch Celery Beat."""
    post_pub = await db.get(PostPublish, publish_id)
    if post_pub is None or post_pub.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài đăng")
    if post_pub.status == PublishStatus.PUBLISHING.value:
        raise HTTPException(status_code=409, detail="Bài đăng đang được xử lý")

    await execute_publish(db, publish_id)
    await db.refresh(post_pub)
    return post_pub


@router.delete("/publishing/{publish_id}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete("/posts/publishing/{publish_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_published_post(
    publish_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    post_pub = await db.get(PostPublish, publish_id)
    if post_pub is None or post_pub.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài đăng")
    if post_pub.status == PublishStatus.PUBLISHING.value:
        raise HTTPException(status_code=409, detail="Không thể xoá bài đăng đang thực hiện")
    await db.delete(post_pub)
    await db.commit()
    return None

