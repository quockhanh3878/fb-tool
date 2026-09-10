"""
Chẩn đoán tài khoản clone — trả lời một câu hỏi duy nhất:
**"Clone này có chạy được ngay bây giờ không, và nếu không thì vì sao?"**

Vì sao cần một module riêng thay vì rải if/else trong router: cùng một bộ luật
được ba nơi dùng lại — nút "Kiểm tra" trên dashboard, task Celery chạy nền, và
bảng tổng quan sức khoẻ. Ba nơi mà ba bộ luật thì sớm muộn cũng nói khác nhau.

Toàn bộ `diagnose()` là hàm THUẦN: nhận clone + kết quả đọc cookie, không chạm
database, không mở browser. Nhờ vậy mọi ngưỡng ở đây đều test được offline.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models.base import as_utc
from app.models.clone_account import CloneAccount
from app.models.enums import AccountState
from app.services.warmup_service import TOTAL_WARMUP_DAYS

# ── Ngưỡng ─────────────────────────────────────────────────────────────────
QUOTA_NEAR_LIMIT = 0.9          # dùng ≥90% quota ngày thì coi như sắp hết
FAILURE_WARNING = 3             # khớp SHADOWBAN_COOLDOWN_THRESHOLD
FAILURE_CRITICAL = 5            # khớp SHADOWBAN_ALERT_THRESHOLD
WARMUP_STALL_DAYS = 2           # ủ ấm trễ hơn lịch ngần này ngày là có sự cố
COOLDOWN_OVERDUE_HOURS = 1      # hết nghỉ quá lâu mà chưa dậy → Beat có vấn đề
IDLE_ALERT_DAYS = 7             # active nhưng im lặng cả tuần

SEVERITY_RANK = {"critical": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Issue:
    """Một vấn đề tìm thấy, kèm cách xử lý cụ thể."""

    code: str
    severity: str  # critical | warning | info
    message: str
    hint: str
    penalty: int  # trừ bao nhiêu điểm sức khoẻ

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "hint": self.hint,
        }


def grade(score: int) -> str:
    """Quy điểm về ba mức để tô màu — người dùng đọc màu nhanh hơn đọc số."""
    if score >= 80:
        return "good"
    if score >= 50:
        return "warn"
    return "bad"


def _days_since(value, now: datetime) -> float | None:
    stamp = as_utc(value)
    if stamp is None:
        return None
    return (now - stamp).total_seconds() / 86400


def diagnose(
    clone: CloneAccount,
    *,
    cookie: dict,
    now: datetime | None = None,
    backup_available: bool = True,
) -> dict:
    """Soi một clone và trả về phiếu chẩn đoán.

    Args:
        cookie: kết quả `facebook_utils.cookie_health()` của clone này.
        backup_available: tài khoản còn clone nào khác gánh việc được không —
            thông tin cấp tài khoản nên phải truyền từ ngoài vào.

    Returns:
        dict gồm `score` (0-100), `grade`, `ready` (nhận việc được ngay không),
        `issues` (đã sắp xếp: nặng trước) và vài số liệu để hiển thị.
    """
    now = now or datetime.now(timezone.utc)
    issues: list[Issue] = []
    state = clone.status

    # ── Vòng đời ───────────────────────────────────────────────────────
    if state == AccountState.BANNED.value:
        issues.append(Issue(
            "state_banned", "critical",
            "Tài khoản đã bị khoá vĩnh viễn.",
            "Xoá clone này và thêm clone mới; đừng cố đăng nhập lại vì càng "
            "làm Facebook gắn cờ thiết bị.",
            100,
        ))
    elif state == AccountState.CHECKPOINT.value:
        issues.append(Issue(
            "state_checkpoint", "critical",
            "Đang bị checkpoint, mọi task đã dừng.",
            "Đăng nhập tay bằng đúng proxy của clone, xác minh xong rồi bấm "
            "«Đã xác minh xong».",
            70,
        ))
    elif state == AccountState.ONBOARDING.value:
        issues.append(Issue(
            "state_onboarding", "info",
            "Chưa hoàn tất thiết lập — clone chưa vào vòng ủ ấm.",
            "Nạp file cookie để bắt đầu 7 ngày ủ ấm.",
            10,
        ))

    # ── Cookie ─────────────────────────────────────────────────────────
    if not cookie.get("cookie_count"):
        issues.append(Issue(
            "cookie_missing", "critical",
            "Chưa có cookie đăng nhập.",
            "Xuất cookie từ trình duyệt đã đăng nhập (Cookie-Editor) rồi nạp lên.",
            60,
        ))
    elif cookie.get("missing"):
        issues.append(Issue(
            "cookie_broken", "critical",
            "Thiếu cookie phiên: " + ", ".join(cookie["missing"]) + ".",
            "File cookie xuất thiếu hoặc đã bị Facebook thu hồi — nạp lại file mới.",
            60,
        ))
    elif cookie.get("expired"):
        issues.append(Issue(
            "cookie_expired", "critical",
            "Cookie đã hết hạn: " + ", ".join(cookie["expired"]) + ".",
            "Đăng nhập lại trên trình duyệt rồi xuất cookie mới.",
            50,
        ))
    else:
        days_left = cookie.get("days_left")
        if days_left is not None and days_left <= 3:
            issues.append(Issue(
                "cookie_expiring", "warning",
                f"Cookie chỉ còn {days_left:g} ngày là hết hạn.",
                "Chuẩn bị cookie mới trước khi clone bị đá về trang đăng nhập.",
                15,
            ))

    # ── Độ tin cậy ─────────────────────────────────────────────────────
    failures = clone.consecutive_failures or 0
    if failures >= FAILURE_CRITICAL:
        issues.append(Issue(
            "failures_critical", "critical",
            f"Hỏng {failures} lượt comment liên tiếp — nhiều khả năng bị hạn chế.",
            "Ngừng dùng clone này vài ngày, kiểm tra xem comment có thật sự "
            "hiển thị với người ngoài không.",
            35,
        ))
    elif failures >= FAILURE_WARNING:
        issues.append(Issue(
            "failures_warning", "warning",
            f"Hỏng {failures} lượt comment liên tiếp.",
            "Giảm trần comment/ngày và xem lại nội dung kịch bản.",
            15,
        ))

    # ── Quota hôm nay ──────────────────────────────────────────────────
    limit = max(1, clone.daily_comment_limit or 1)
    used = clone.daily_comment_count or 0
    ratio = used / limit
    if ratio >= 1:
        issues.append(Issue(
            "quota_exhausted", "info",
            f"Đã dùng hết quota hôm nay ({used}/{limit}).",
            "Bình thường — quota tự đặt lại vào ngày mới.",
            5,
        ))
    elif ratio >= QUOTA_NEAR_LIMIT:
        issues.append(Issue(
            "quota_near", "info",
            f"Sắp hết quota hôm nay ({used}/{limit}).",
            "Thêm clone nếu cần bắn nhiều hơn — đừng nâng trần của một clone.",
            0,
        ))

    # ── Hạ tầng ────────────────────────────────────────────────────────
    if not (clone.proxy_address or "").strip():
        issues.append(Issue(
            "no_proxy", "warning",
            "Chưa gán proxy — clone đang dùng chung IP với máy chủ.",
            "Gán proxy dân cư riêng; nhiều clone chung một IP là dấu hiệu "
            "Facebook bắt rất nhanh.",
            10,
        ))

    if not backup_available and state in (
        AccountState.ACTIVE.value,
        AccountState.WARMING_UP.value,
    ):
        issues.append(Issue(
            "no_backup", "warning",
            "Không còn clone dự phòng nào để thay khi clone này gặp sự cố.",
            "Thêm ít nhất một clone và bật «dùng làm clone dự phòng».",
            10,
        ))

    # ── Lịch trình bị kẹt ──────────────────────────────────────────────
    if state == AccountState.WARMING_UP.value:
        elapsed = _days_since(clone.warmup_started_at, now)
        done = clone.warmup_day or 0
        if elapsed is not None and done < TOTAL_WARMUP_DAYS:
            behind = elapsed - done
            if behind >= WARMUP_STALL_DAYS:
                issues.append(Issue(
                    "warmup_stalled", "warning",
                    f"Ủ ấm bị kẹt ở ngày {done}/{TOTAL_WARMUP_DAYS} "
                    f"dù đã bắt đầu {elapsed:.0f} ngày trước.",
                    "Kiểm tra Celery Beat còn chạy không — task ủ ấm hằng ngày "
                    "có vẻ không được kích hoạt.",
                    20,
                ))

    if state == AccountState.COOLDOWN.value:
        due = as_utc(clone.cooldown_until)
        if due is not None and due + timedelta(hours=COOLDOWN_OVERDUE_HOURS) <= now:
            issues.append(Issue(
                "cooldown_overdue", "warning",
                "Đã hết giờ nghỉ nhưng clone vẫn chưa được đánh thức.",
                "Bấm «Đánh thức ngay», và kiểm tra task wake_cooldowns của Beat.",
                20,
            ))

    if state == AccountState.ACTIVE.value:
        idle = _days_since(clone.last_activity_at, now)
        if idle is not None and idle >= IDLE_ALERT_DAYS:
            issues.append(Issue(
                "idle_long", "info",
                f"Đang bật nhưng {idle:.0f} ngày rồi chưa làm gì.",
                "Kiểm tra clone đã được gán vào chiến dịch nào chưa.",
                5,
            ))

    issues.sort(key=lambda item: (SEVERITY_RANK[item.severity], -item.penalty))
    score = max(0, 100 - sum(item.penalty for item in issues))
    blocking = [item for item in issues if item.severity == "critical"]

    return {
        "clone_id": clone.id,
        "display_name": clone.display_name,
        "status": state,
        "score": score,
        "grade": grade(score),
        # "Sẵn sàng" = đang Active, cookie dùng được, còn quota, không lỗi nặng.
        "ready": (
            state == AccountState.ACTIVE.value
            and not blocking
            and used < limit
        ),
        "cookie_ok": bool(cookie.get("ok")),
        "cookie_expires_at": cookie.get("expires_at"),
        "cookie_days_left": cookie.get("days_left"),
        "daily_comment_count": used,
        "daily_comment_limit": limit,
        "consecutive_failures": failures,
        "proxy_address": clone.proxy_address,
        "issues": [item.as_dict() for item in issues],
        "checked_at": now,
    }


def rollup(reports: list[dict]) -> dict:
    """Gộp nhiều phiếu chẩn đoán thành bức tranh cấp tài khoản.

    `capacity_left` mới là con số người dùng thực sự cần: "hôm nay còn bắn
    được bao nhiêu comment", chứ không phải "có mấy clone".
    """
    if not reports:
        return {
            "clone_count": 0,
            "ready_count": 0,
            "average_score": 0,
            "grade": "bad",
            "critical_count": 0,
            "warning_count": 0,
            "capacity_used": 0,
            "capacity_total": 0,
            "capacity_left": 0,
            "top_issues": [],
        }

    average = round(sum(item["score"] for item in reports) / len(reports))
    critical = warning = 0
    counter: dict[str, dict] = {}
    for report in reports:
        for issue in report["issues"]:
            if issue["severity"] == "critical":
                critical += 1
            elif issue["severity"] == "warning":
                warning += 1
            slot = counter.setdefault(
                issue["code"],
                {"code": issue["code"], "severity": issue["severity"],
                 "message": issue["message"], "hint": issue["hint"], "count": 0},
            )
            slot["count"] += 1

    used = sum(item["daily_comment_count"] for item in reports)
    # Clone không sẵn sàng thì quota của nó chỉ là con số trên giấy.
    total = sum(item["daily_comment_limit"] for item in reports if item["ready"])
    left = sum(
        max(0, item["daily_comment_limit"] - item["daily_comment_count"])
        for item in reports
        if item["ready"]
    )

    top = sorted(
        counter.values(),
        key=lambda item: (SEVERITY_RANK[item["severity"]], -item["count"]),
    )[:5]

    return {
        "clone_count": len(reports),
        "ready_count": sum(1 for item in reports if item["ready"]),
        "average_score": average,
        "grade": grade(average),
        "critical_count": critical,
        "warning_count": warning,
        "capacity_used": used,
        "capacity_total": total,
        "capacity_left": left,
        "top_issues": top,
    }


# ── Cầu nối sang dữ liệu thật ──────────────────────────────────────────────
# Hai hàm dưới đây là phần DUY NHẤT chạm vào cookie đã mã hoá; giữ chúng tách
# khỏi `diagnose()` để phần luật vẫn test được mà không cần khoá Fernet.
def read_cookie_health(clone: CloneAccount) -> dict:
    """Giải mã cookie của clone rồi chấm sức khoẻ. Hỏng khoá = coi như chưa có."""
    from app.services.crypto import decrypt_cookies
    from app.services.facebook_utils import cookie_health

    try:
        cookies = decrypt_cookies(clone.cookie_data_encrypted)
    except Exception:
        cookies = None
    return cookie_health(cookies)


def is_role_compatible(r1: str, r2: str) -> bool:
    if r1 == r2:
        return True
    if "all" in (r1, r2):
        return True
    if "both" in (r1, r2) and {r1, r2}.issubset({"scout", "shooter", "both"}):
        return True
    return False


def has_backup(clone: CloneAccount, others: list[CloneAccount]) -> bool:
    """Còn clone nào khác gánh việc thay được không?"""
    usable = (AccountState.ACTIVE.value, AccountState.COOLDOWN.value)
    return any(
        other.id != clone.id
        and other.status in usable
        and is_role_compatible(other.role, clone.role)
        for other in others
    )


def diagnose_many(clones: list[CloneAccount], now: datetime | None = None) -> list[dict]:
    """Chẩn đoán cả đàn clone — dùng chung cho nút «Kiểm tra tất cả» và Celery."""
    now = now or datetime.now(timezone.utc)
    return [
        diagnose(
            clone,
            cookie=read_cookie_health(clone),
            now=now,
            backup_available=has_backup(clone, clones),
        )
        for clone in clones
    ]
