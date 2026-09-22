"""Feed bài viết đã phát hiện + nộp bài từ Scout + ứng tuyển thủ công."""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user, owned_campaign, rate_limit
from app.models.base import utcnow
from app.models.campaign import Campaign, CampaignGroup
from app.models.clone_account import CloneAccount
from app.models.enums import CloneRole, CommentStatus, PostStatus, PublishStatus
from app.models.post import (
    CommentAction,
    DiscoveredPost,
    PostPublish,
    PostPublishHistory,
    PublishingMedia,
)
from app.models.user import User
from app.schemas import (
    ApplyRequest,
    CommentActionOut,
    CommentHistoryListOut,
    CommentHistoryOut,
    IngestCommentsRequest,
    IngestCommentsResultOut,
    IngestPostsRequest,
    IngestResultOut,
    PostListOut,
    PostOut,
    PostPublishCreate,
    PostPublishListOut,
    PostPublishHistoryListOut,
    PostPublishHistoryOut,
    PostPublishOut,
    PostPublishUpdate,
    PublishingMediaOut,
)
from app.services.ai_service import AIService
from app.services.lead_service import detect_leads, notify_leads
from app.services.mention_service import detect_mentions, notify_mentions
from app.services.notification_service import NotificationService
from app.services.pipeline import (
    build_comment,
    count_today_actions,
    ingest_raw_posts,
    process_campaign_posts,
    queue_comment,
)
from app.services.publishing_media import (
    MAX_MEDIA_BYTES,
    media_reference,
    parse_media_reference,
    save_media,
)
from app.services.execution_policy import lock_user, require_comment_policy, require_entitlement, require_owned_clone
from app.services.publishing_defaults import (
    DEFAULT_BUMP_HOURS,
    DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS,
)
from app.services.script_engine import ScriptError, validate_comment

router = APIRouter(prefix="/api", tags=["posts"])


@router.post("/publishing/media", response_model=PublishingMediaOut, status_code=status.HTTP_201_CREATED)
async def upload_publishing_media(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw = await file.read(MAX_MEDIA_BYTES + 1)
    media = save_media(
        user_id=user.id,
        filename=file.filename or "image",
        content_type=file.content_type or "",
        raw=raw,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return PublishingMediaOut(
        **{key: getattr(media, key) for key in ("id", "original_filename", "content_type", "size_bytes", "created_at")},
        reference=media_reference(media.id),
    )


@router.get("/publishing/media/{media_id}")
async def download_publishing_media(
    media_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    media = await db.get(PublishingMedia, media_id)
    if media is None or media.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy ảnh")
    return FileResponse(media.storage_path, media_type=media.content_type, filename=media.original_filename)


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


@router.post("/posts/{post_id}/apply", response_model=CommentActionOut, dependencies=[Depends(rate_limit("apply", 20))])
async def apply_to_post(
    post_id: str,
    payload: ApplyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ứng tuyển bài viết: sinh comment (hoặc dùng nội dung người dùng gõ) và xếp hàng."""
    post = await _owned_post(post_id, user, db)
    campaign = await db.get(Campaign, post.campaign_id)
    if payload.clone_id:
        await require_owned_clone(db, payload.clone_id, user.id)
    existing = await db.scalar(select(CommentAction).where(CommentAction.idempotency_key == post.id))
    if existing is not None:
        return existing
    await require_comment_policy(db, campaign, post, payload.clone_id)

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
            if not getattr(campaign, "ai_comments_enabled", False):
                detail = (
                    "Chiến dịch đang tắt tính năng AI comment và chưa có kịch bản Spintax hợp lệ. "
                    "Vui lòng thêm kịch bản trong tab Kịch bản hoặc tự nhập nội dung bình luận."
                )
            else:
                detail = "Không sinh được comment — kiểm tra kịch bản hoặc OpenAI API key."
            raise HTTPException(status_code=422, detail=detail)

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
    await lock_user(db, user.id)
    await db.execute(update(CommentAction).where(
        CommentAction.discovered_post_id == post.id,
        CommentAction.status == CommentStatus.QUEUED.value,
    ).values(status=CommentStatus.CANCELLED.value, error_message="post_skipped"))
    post.status = PostStatus.SKIPPED.value
    post.ai_reason = "user_skipped"
    await db.commit()
    await db.refresh(post)
    return post


@router.post(
    "/campaigns/{campaign_id}/ingest",
    response_model=IngestResultOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("ingest", 10))],
)
async def ingest_posts(
    payload: IngestPostsRequest,
    campaign: Campaign = Depends(owned_campaign),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Scout worker nộp bài thô; API chạy trọn pipeline lọc → thông báo/xếp hàng."""
    await require_entitlement(db, user.id, campaign)
    group = await db.get(CampaignGroup, payload.group_id)
    if group is None or group.campaign_id != campaign.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy group")

    fresh = await ingest_raw_posts(db, campaign, group, payload.posts)
    stats = await process_campaign_posts(
        db, campaign, fresh, _ai_service(), notifier=NotificationService(), user=user
    )
    mentions = await detect_mentions(db, campaign, group, fresh)
    await notify_mentions(user, campaign.name, mentions, db=db)
    await db.commit()
    return IngestResultOut(ingested=len(fresh), mentions=len(mentions), **stats)


@router.post(
    "/campaigns/{campaign_id}/ingest-comments",
    response_model=IngestCommentsResultOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("ingest-comments", 10))],
)
async def ingest_comments(
    payload: IngestCommentsRequest,
    campaign: Campaign = Depends(owned_campaign),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Nộp comment thô bóc dưới một bài; săn lead theo `campaign.lead_keywords`.

    `clone_id` (nếu có) dùng để loại trừ chính nick đang quét khỏi kết quả —
    so `CloneAccount.fb_user_id` với `author_fb_id` của từng comment.
    """
    await require_entitlement(db, user.id, campaign)
    group = None
    if payload.group_id:
        group = await db.get(CampaignGroup, payload.group_id)
        if group is None or group.campaign_id != campaign.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy group")

    own_fb_id = ""
    if payload.clone_id:
        clone = await db.get(CloneAccount, payload.clone_id)
        if clone is None or clone.user_id != user.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản clone")
        own_fb_id = clone.fb_user_id or ""

    leads = await detect_leads(
        db, campaign, group, payload.comments, own_fb_id=own_fb_id
    )
    await notify_leads(user, campaign.name, leads, db=db)
    await db.commit()
    return IngestCommentsResultOut(ingested=len(payload.comments), leads=len(leads))


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


@router.get("/comment-history", response_model=CommentHistoryListOut)
async def comment_history(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lịch sử comment đã xếp hàng/thực thi, kèm link bài gốc và link comment."""
    base = (
        select(CommentAction, DiscoveredPost.post_url)
        .join(DiscoveredPost, DiscoveredPost.id == CommentAction.discovered_post_id)
        .join(Campaign, Campaign.id == DiscoveredPost.campaign_id)
        .where(Campaign.user_id == user.id)
    )
    if status_filter:
        base = base.where(CommentAction.status == status_filter)
    total = await db.execute(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.order_by(CommentAction.created_at.desc()).limit(limit).offset(offset)
    )
    items = [
        CommentHistoryOut(
            id=action.id,
            discovered_post_id=action.discovered_post_id,
            post_url=post_url,
            comment_content=action.comment_content,
            fb_comment_id=action.fb_comment_id,
            comment_url=action.comment_url,
            status=action.status,
            error_message=action.error_message,
            scheduled_at=action.scheduled_at,
            executed_at=action.executed_at,
        )
        for action, post_url in result.all()
    ]
    return CommentHistoryListOut(
        items=items, total=int(total.scalar_one() or 0), limit=limit, offset=offset
    )


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
    await lock_user(db, user.id)
    await db.refresh(action)
    if action.status != CommentStatus.QUEUED.value:
        raise HTTPException(
            status_code=409,
            detail=f"Chỉ huỷ được lượt đang chờ (hiện tại: {action.status})",
        )
    action.status = CommentStatus.CANCELLED.value
    action.error_message = "cancelled_by_user"
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


@router.get("/publishing/history", response_model=PostPublishHistoryListOut)
@router.get("/posts/publishing/history", response_model=PostPublishHistoryListOut)
async def list_publish_history(
    campaign_id: str | None = None,
    publish_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lịch sử bất biến theo từng group; không phụ thuộc snapshot JSON của job."""
    base = select(PostPublishHistory).where(PostPublishHistory.user_id == user.id)
    if campaign_id:
        base = base.where(PostPublishHistory.campaign_id == campaign_id)
    if publish_status:
        base = base.where(PostPublishHistory.status == publish_status)
    total = await db.execute(select(func.count()).select_from(base.subquery()))
    result = await db.execute(
        base.order_by(PostPublishHistory.created_at.desc()).limit(limit).offset(offset)
    )
    return PostPublishHistoryListOut(
        items=[PostPublishHistoryOut.model_validate(item) for item in result.scalars().all()],
        total=int(total.scalar_one() or 0),
        limit=limit,
        offset=offset,
    )


@router.post("/publishing", response_model=PostPublishOut, status_code=status.HTTP_201_CREATED)
@router.post("/posts/publishing", response_model=PostPublishOut, status_code=status.HTTP_201_CREATED)
async def create_published_post(
    payload: PostPublishCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tạo bài đăng mới vào nhóm với kịch bản Spintax."""
    await lock_user(db, user.id)
    subscription = await require_entitlement(db, user.id)
    campaign = None
    if payload.campaign_id:
        campaign = await db.get(Campaign, payload.campaign_id)
        if campaign is None or campaign.user_id != user.id:
            raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    for reference in payload.media_urls:
        media_id = parse_media_reference(reference)
        media = await db.get(PublishingMedia, media_id) if media_id else None
        if media is None or media.user_id != user.id:
            raise HTTPException(status_code=422, detail="Ảnh đính kèm không hợp lệ hoặc không thuộc tài khoản")
    effective_auto_bump = (
        payload.auto_bump
        if payload.auto_bump is not None
        else (campaign.publish_auto_bump if campaign else True)
    )
    effective_repeat_days = (
        payload.repeat_interval_days
        if payload.repeat_interval_days is not None
        else (
            campaign.publish_repeat_interval_days
            if campaign
            else DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS
        )
    )
    effective_bump_hours = list(
        payload.bump_hours
        if payload.bump_hours is not None
        else (campaign.publish_bump_hours if campaign else DEFAULT_BUMP_HOURS)
    )
    if effective_auto_bump and not subscription.bump_enabled:
        raise HTTPException(status_code=403, detail="Gói cước không có tính năng bump")
    pending = int(await db.scalar(select(func.count(PostPublish.id)).where(
        PostPublish.user_id == user.id,
        PostPublish.status.in_((PublishStatus.SCHEDULED.value, PublishStatus.PUBLISHING.value)),
    )) or 0)
    if pending >= get_settings().max_pending_per_user:
        raise HTTPException(status_code=429, detail="Hàng đợi đăng bài đã đầy")
    if campaign:
        await require_entitlement(db, user.id, campaign)

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
        repeat_interval_days=effective_repeat_days,
        auto_bump=effective_auto_bump,
        bump_hours=effective_bump_hours,
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


@router.post("/publishing/{publish_id}/publish-now", response_model=PostPublishOut, status_code=202)
@router.post("/posts/publishing/{publish_id}/publish-now", response_model=PostPublishOut, status_code=202)
async def publish_post_now(
    publish_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Đăng bài ngay lập tức không cần đợi lịch Celery Beat."""
    post_pub = await db.get(PostPublish, publish_id)
    if post_pub is None or post_pub.user_id != user.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài đăng")
    await lock_user(db, user.id)
    await db.refresh(post_pub)
    campaign = await db.get(Campaign, post_pub.campaign_id) if post_pub.campaign_id else None
    await require_entitlement(db, user.id, campaign)
    if post_pub.status not in (PublishStatus.DRAFT.value, PublishStatus.SCHEDULED.value):
        raise HTTPException(status_code=409, detail="Chỉ xếp lịch bản nháp hoặc bài đang chờ; không tự gửi lại")
    post_pub.status = PublishStatus.SCHEDULED.value
    post_pub.scheduled_at = utcnow()
    await db.commit()
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
    await lock_user(db, user.id)
    await db.refresh(post_pub)
    if post_pub.status == PublishStatus.PUBLISHING.value:
        raise HTTPException(status_code=409, detail="Không thể xoá bài đăng đang thực hiện")
    await db.delete(post_pub)
    await db.commit()
    return None


@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _owned_post(post_id, user, db)
