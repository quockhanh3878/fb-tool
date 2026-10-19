# plan: docs/plans/phase2_dashboard_detail.md
"""Kiểm chứng hợp đồng lịch đăng/bump tùy biến và mặc định theo brief khách."""

import base64
import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("RUN_MODE", "saas")
os.environ["DEBUG"] = "false"
os.environ.setdefault("JWT_SECRET", "offline-schedule-test-secret-32-bytes-2026")
os.environ.setdefault("DESKTOP_INSTANCE_SECRET", "offline-desktop-secret-32-bytes-minimum-2026")
os.environ.setdefault(
    "COOKIE_ENCRYPTION_KEY", base64.urlsafe_b64encode(bytes(range(32))).decode()
)

from app.schemas import CampaignCreate, CampaignUpdate
from app.services.publishing_defaults import DEFAULT_BUMP_HOURS
from app.workers.bump_task import bump_jitter_seconds


def test_customer_defaults_and_custom_values():
    defaults = CampaignCreate(name="Nyatymita")
    assert defaults.publish_repeat_interval_days == 14
    assert defaults.publish_bump_hours == list(DEFAULT_BUMP_HOURS)

    custom = CampaignUpdate(
        publish_repeat_interval_days=23,
        publish_bump_hours=[19, 10, 19],
        schedule_timezone="Asia/Tokyo",
        bump_jitter_enabled=False,
        bump_jitter_min_minutes=0,
        bump_jitter_max_minutes=0,
    )
    assert custom.publish_bump_hours == [10, 19]
    assert custom.schedule_timezone == "Asia/Tokyo"


def test_jitter_can_be_disabled_or_customized():
    assert bump_jitter_seconds("bump", "2026-09-22", 10, enabled=False) == 0
    value = bump_jitter_seconds(
        "bump", "2026-09-22", 10, min_minutes=2, max_minutes=3
    )
    assert 120 <= abs(value) <= 180
