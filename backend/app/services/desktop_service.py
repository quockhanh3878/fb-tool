# plan: docs/plans/desktop_packaging.md
"""
Seed user mặc định + auto-login cho chế độ desktop (RUN_MODE=desktop).

Máy khách chỉ có 1 người dùng — không bắt khách đăng ký/gõ email-password.
Lần đầu chạy: tạo sẵn 1 user + subscription hạn mức rộng (Studio, hết hạn xa)
để không bao giờ chặn quota; các lần sau tái dùng đúng user đó.
"""
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utcnow
from app.models.campaign import Campaign, CommentScript
from app.models.enums import PaymentStatus, PublishStatus, ScriptType, SubscriptionPlan
from app.models.post import PostPublish
from app.models.user import Subscription, User
from app.security import hash_password
from app.services.plans import get_plan
from app.services.publishing_defaults import (
    DEFAULT_BUMP_HOURS,
    DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS,
)

DESKTOP_USER_EMAIL = "khach@local.commhunter"
DESKTOP_SUBSCRIPTION_YEARS = 100

DEFAULT_POST_TITLE = "TIỆM CƠM ĐẦU TIÊN MỞ WEBSITE WRITING COMMISSION CHUYÊN NGHIỆP"

DEFAULT_POST_CONTENT = """Dịch vụ chấp bút của Nyatymita là dịch vụ chuyên nghiệp nyatymita.com đầu tiên trong giới writing commission thực hiện website riêng tư dành cho việc đặt chấp bút. Khách hàng sẽ có đủ sự riêng tư và thoải mái khi nhận được bản thảo được trình bày chỉn chu trên trình duyệt Chrome và Safari, nhận thông báo cập nhật đơn hàng nhanh chóng và tiện lợi, cùng nhiều ưu đãi dành riêng cho khách hàng đặt writing comm qua web.


Độ bảo mật cao và luôn tạo sự thoải mái cho khách hàng là tiêu chí hàng đầu của nyatymita.com. Khi đăng ký tài khoản và đặt hàng qua web, bạn có thể nhận được các ưu đãi sau đây:


❤ Khuyến mãi khách mới:

 Với khách lần đầu đặt dịch vụ của t qua web sẽ được tặng FREE 500w

❤ Mốc son vạn dặm:

Có 2 ưu đãi mốc son dành cho đơn thường và tính theo số từ long fic, quà tặng có giá trị tăng tiến theo quá trình tích luỹ đơn hàng và số từ. Chi tiết vui lòng xem tại website.

❤ Ưu đãi thăng hạng:

Khi đăng ký tài khoản và đặt đơn qua web, khách hàng sẽ được tích luỹ điểm để thăng hạng. Mỗi hạng sẽ được cung cấp ưu đãi theo quý/event/đơn hàng khác nhau. 

❤ Gacha mỗi ngày, vận may tăng tiến:

Checkin daily để nhận ticket quay gacha với nhiều phần thưởng tặng từ, giảm giá và oneshot giá trị cao.

❤ Event collab Nyatymita’s Writing Commission x Hải Lam Audio:

Đặt gói combo fiction 5kw trở lên kèm gói chuyển thể audio cho OPT của bạn để được giảm đến 5%.

❤ Coupon Meow Paws Circle:

Chọn 1 trong 6 gian hàng circle của Meow Paws Circle để nhận coupon tặng 500w miễn phí.

❤ Khách hàng đặt lại lần thứ 2 trở đi: 

Tặng 500w cho đơn hàng thứ 2; tặng 1000w cho đơn hàng thứ 3; tặng 1500w cho đơn hàng thứ 4; giảm 5% cho đơn hàng thứ 5 và cố định giảm 5% cho các đơn hàng kế tiếp.

Cùng nhiều ưu đãi hấp dẫn khách cho khách mới, khách quay lại đặt lần nữa, khách đặt qua website…

Dịch vụ Chấp bút của Nyatymita là tiệm cơm chuyên nhận long fic đa dạng thể loại và đề tài, với ngòi bút linh hoạt và dịch vụ khách hàng chất lượng sẽ mang lại trải nghiệm tốt nhất có thể cho khách hàng.

Vui lòng đọc samples SFW và NSFW tại website nyatymita.com.


Lưu ý: Không khuyến khích, cổ suý người dưới 18 tuổi tham khảo nội dung comm NSFW.


Không nhận đơn NSFW đối với người dưới 18 tuổi và chưa có khả năng tự chủ tài chính.""".strip()

DEFAULT_COMMENT_TEXT = """Chào bạn, 

Mình chuyên nhận long fic, shortfic, đơn n5fw, build plot/OC đa dạng thể loại và đề tài, bạn có thể tham khảo danh sách comm đã hoàn thành làm samples, thống kê theo thể loại được đăng tải tại nyatymita.wordpress.com. Xem các thông tin khuyến mãi và bảng giá tại: FB Xưởng Chữ Nyatymita hoặc nyatymita.com nha.

Để đọc các bản thảo thể loại NSFW, vui lòng nhắn tin cho Xưởng Chữ Nyatymita để được tư vấn kỹ hơn.

Không cổ xuý, chia sẻ bản thảo NSFW cho người dưới tuổi trưởng thành. 

Samples được đăng tải tại: nyatymita.com.""".strip()


async def seed_desktop_defaults(db: AsyncSession, user_id: str) -> None:
    """Tạo sẵn chiến dịch và bài đăng mẫu mặc định nếu tài khoản desktop chưa có."""
    res_c = await db.execute(select(Campaign).where(Campaign.user_id == user_id))
    existing_campaign = res_c.scalars().first()
    campaign_id = existing_campaign.id if existing_campaign else None

    if existing_campaign is None:
        campaign = Campaign(
            user_id=user_id,
            name="Chiến dịch Writing Commission (Nyatymita)",
            service_name="Nyatymita's Writing Commission",
            service_specialties="Chuyên nhận long fic, shortfic, đơn nsfw, build plot/OC đa dạng thể loại và đề tài",
            landing_page_note="nyatymita.com",
            ai_filter_prompt="Tìm bài viết tìm người viết commission, viết truyện, longfic, shortfic, chấp bút truyện, build plot hoặc tuyển writer.",
            whitelist_keywords=["viết comm", "commission", "viết fic", "longfic", "shortfic", "chấp bút", "viết truyện", "writer", "plot", "nsfw", "sfw"],
            blacklist_keywords=["tuyển dụng thực tập", "không lương", "bẫy lừa đảo", "ctv nạp tiền"],
            is_active=True,
        )
        db.add(campaign)
        await db.flush()
        campaign_id = campaign.id

        script = CommentScript(
            campaign_id=campaign.id,
            name="Mẫu CMT chào khách & gửi portfolio",
            type=ScriptType.SPINTAX.value,
            template_content=DEFAULT_COMMENT_TEXT,
            is_default=True,
            is_active=True,
        )
        db.add(script)
        await db.flush()

    res_p = await db.execute(select(PostPublish).where(PostPublish.user_id == user_id))
    existing_post = res_p.scalars().first()
    if existing_post is None:
        post = PostPublish(
            user_id=user_id,
            campaign_id=campaign_id,
            title=DEFAULT_POST_TITLE,
            content_template=DEFAULT_POST_CONTENT,
            status=PublishStatus.DRAFT.value,
            target_groups=[],
            repeat_interval_days=DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS,
            auto_bump=True,
            bump_hours=list(DEFAULT_BUMP_HOURS),
        )
        db.add(post)
        await db.flush()


async def ensure_desktop_user(db: AsyncSession) -> User:
    """Trả về user desktop duy nhất, tạo mới nếu DB rỗng (idempotent)."""
    result = await db.execute(select(User).where(User.email == DESKTOP_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is not None:
        await seed_desktop_defaults(db, user.id)
        await db.commit()
        return user

    user = User(
        email=DESKTOP_USER_EMAIL,
        hashed_password=hash_password(secrets.token_urlsafe(32)),
        display_name="Khách",
        tier=SubscriptionPlan.STUDIO.value,
    )
    db.add(user)
    await db.flush()

    spec = get_plan(SubscriptionPlan.STUDIO.value)
    db.add(
        Subscription(
            user_id=user.id,
            plan=spec.plan.value,
            max_groups=spec.max_groups,
            max_clones=spec.max_clones,
            max_comments_per_day=spec.max_comments_per_day,
            ai_comments_enabled=spec.ai_comments_enabled,
            bump_enabled=spec.bump_enabled,
            started_at=utcnow(),
            expires_at=utcnow() + timedelta(days=365 * DESKTOP_SUBSCRIPTION_YEARS),
            payment_status=PaymentStatus.ACTIVE.value,
        )
    )
    await seed_desktop_defaults(db, user.id)
    await db.commit()
    await db.refresh(user)
    return user
