# plan: docs/plans/phase2_dashboard_detail.md
"""
Gộp danh sách nhóm cào từ hồ sơ clone Scout vào một chiến dịch.

Việc cào là thao tác đọc trên Facebook (`scout_worker.scrape_joined_groups`
qua `browser_runtime.scrape_joined_groups_raw`). File này chỉ lo phần thuần
DB: chuẩn hoá tham chiếu group, loại trùng, tôn trọng hạn mức gói cước.
Không phụ thuộc Playwright nên test offline được.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignGroup
from app.models.enums import GroupStatus
from app.models.user import User
from app.services.facebook_utils import InvalidGroupURL, parse_group_ref
from app.services.quota import remaining_group_slots


async def merge_discovered_groups(
    db: AsyncSession, campaign: Campaign, user: User, raw_groups: list[dict]
) -> dict:
    """Nạp các nhóm cào được vào chiến dịch với trạng thái `paused` (chờ duyệt).

    - Chuẩn hoá mọi tham chiếu qua ``parse_group_ref``; bỏ cái không hợp lệ.
    - Bỏ nhóm đã có trong chiến dịch (so theo ``group_key``).
    - Chỉ thêm tới khi chạm hạn mức group của gói cước; phần dư tính vào
      ``skipped_quota`` (không ném lỗi — anh Ber tự nâng gói nếu muốn thêm).

    Không commit — nhánh gọi tự quyết.

    Returns:
        dict: discovered, added, skipped_duplicate, skipped_invalid,
        skipped_quota, added_groups (list {group_key, group_name}).
    """
    # 1. Chuẩn hoá + loại trùng ngay trong input
    normalized: dict[str, str] = {}  # group_key -> group_name
    skipped_invalid = 0
    for item in raw_groups or []:
        item = item or {}
        ref = item.get("url") or item.get("key") or ""
        try:
            group_key, _canonical = parse_group_ref(ref)
        except InvalidGroupURL:
            skipped_invalid += 1
            continue
        name = (item.get("name") or "").strip() or group_key
        normalized.setdefault(group_key, name)

    discovered = len(normalized)

    # 2. Nhóm đã có trong chiến dịch
    existing = await db.execute(
        select(CampaignGroup.group_key).where(
            CampaignGroup.campaign_id == campaign.id
        )
    )
    existing_keys = set(existing.scalars().all())

    candidates = [
        (key, name) for key, name in normalized.items() if key not in existing_keys
    ]
    skipped_duplicate = discovered - len(candidates)

    # 3. Hạn mức gói cước
    slots = await remaining_group_slots(db, user)
    to_add = candidates[:slots]
    skipped_quota = len(candidates) - len(to_add)

    added_groups = []
    for group_key, group_name in to_add:
        db.add(
            CampaignGroup(
                campaign_id=campaign.id,
                group_url=f"https://www.facebook.com/groups/{group_key}/",
                group_key=group_key,
                group_name=group_name,
                status=GroupStatus.PAUSED.value,
            )
        )
        added_groups.append({"group_key": group_key, "group_name": group_name})

    return {
        "discovered": discovered,
        "added": len(added_groups),
        "skipped_duplicate": skipped_duplicate,
        "skipped_invalid": skipped_invalid,
        "skipped_quota": skipped_quota,
        "added_groups": added_groups,
    }
