"""
Gói cước & hạn mức (Master Plan §8 — mô hình kinh doanh).

Đây là nguồn sự thật duy nhất cho quota. Router và worker đều phải hỏi
qua đây thay vì tự đoán con số, nếu không mỗi nơi một hạn mức khác nhau.
"""
from dataclasses import dataclass

from app.models.enums import SubscriptionPlan


@dataclass(frozen=True)
class PlanSpec:
    plan: SubscriptionPlan
    display_name: str
    price_vnd: int
    max_groups: int
    max_clones: int
    max_comments_per_day: int
    ai_comments_enabled: bool
    bump_enabled: bool


PLANS: dict[str, PlanSpec] = {
    SubscriptionPlan.STARTER.value: PlanSpec(
        plan=SubscriptionPlan.STARTER,
        display_name="Starter",
        price_vnd=199_000,
        max_groups=5,
        max_clones=1,
        max_comments_per_day=20,
        ai_comments_enabled=True,
        bump_enabled=False,
    ),
    SubscriptionPlan.PRO.value: PlanSpec(
        plan=SubscriptionPlan.PRO,
        display_name="Pro",
        price_vnd=399_000,
        max_groups=20,
        max_clones=3,
        max_comments_per_day=50,
        ai_comments_enabled=True,
        bump_enabled=True,
    ),
    SubscriptionPlan.STUDIO.value: PlanSpec(
        plan=SubscriptionPlan.STUDIO,
        display_name="Studio",
        price_vnd=799_000,
        max_groups=100,
        max_clones=10,
        max_comments_per_day=150,
        ai_comments_enabled=True,
        bump_enabled=True,
    ),
}

DEFAULT_PLAN = SubscriptionPlan.STARTER.value


def get_plan(plan_name: str) -> PlanSpec:
    """Trả về đặc tả gói; gói lạ thì rơi về Starter (an toàn nhất)."""
    return PLANS.get((plan_name or "").lower(), PLANS[DEFAULT_PLAN])
