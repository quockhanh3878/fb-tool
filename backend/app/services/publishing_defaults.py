# plan: docs/plans/phase2_dashboard_detail.md
"""Các giá trị mặc định cho luồng đăng bài và auto-bump.

Giá trị này chỉ là fallback. Campaign và từng bài đăng có thể ghi đè.
"""

DEFAULT_PUBLISH_REPEAT_INTERVAL_DAYS = 14
DEFAULT_BUMP_HOURS = (10, 17, 19, 21)
DEFAULT_SCHEDULE_TIMEZONE = "Asia/Ho_Chi_Minh"
DEFAULT_BUMP_JITTER_ENABLED = True
DEFAULT_BUMP_JITTER_MIN_MINUTES = 5
DEFAULT_BUMP_JITTER_MAX_MINUTES = 10


def default_bump_hours() -> list[int]:
    return list(DEFAULT_BUMP_HOURS)
