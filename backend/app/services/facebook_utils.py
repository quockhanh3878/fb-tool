"""
Tiện ích Facebook thuần logic: chuẩn hoá URL group và nạp cookie.

Kế thừa nguyên tắc kiểm tra chặt của fbn/extractor.py và fbn/auth.py
(xem NOTICE ở thư mục gốc), viết lại gọn cho nhu cầu của backend.
Không phụ thuộc Playwright nên test được offline.
"""
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

FACEBOOK_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "m.facebook.com",
    "mbasic.facebook.com",
    "web.facebook.com",
}

_GROUP_KEY = r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}"
_GROUP_PATH_RE = re.compile(rf"^/groups/(?P<group>{_GROUP_KEY})(?:/.*)?$")


class InvalidGroupURL(ValueError):
    """URL không phải là link group Facebook hợp lệ."""


class InvalidCookieFile(ValueError):
    """File cookie sai định dạng hoặc không chứa cookie Facebook nào."""


def parse_group_ref(value: str) -> tuple[str, str]:
    """Chuẩn hoá tham chiếu group thành (group_key, canonical_url).

    Chấp nhận:
      • "https://www.facebook.com/groups/123456/"
      • "https://m.facebook.com/groups/ten.group/posts/999/"  (lấy phần group)
      • "123456" hoặc "ten.group"   (chỉ mã group)

    Raises:
        InvalidGroupURL: nếu không nhận diện được.
    """
    raw = (value or "").strip()
    if not raw:
        raise InvalidGroupURL("URL group đang trống")

    if "/" not in raw and re.fullmatch(_GROUP_KEY, raw):
        return raw, f"https://www.facebook.com/groups/{raw}/"

    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")

    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if host not in FACEBOOK_HOSTS:
        raise InvalidGroupURL(f"Không phải tên miền Facebook: {host or raw}")

    match = _GROUP_PATH_RE.match(parts.path or "")
    if not match:
        raise InvalidGroupURL(f"Đường dẫn không phải link group: {parts.path!r}")

    group_key = match.group("group")
    return group_key, f"https://www.facebook.com/groups/{group_key}/"


def extract_post_id(url: str) -> str:
    """Rút post_id Facebook từ URL (dùng chung logic với Phase 1 scout_worker)."""
    if not url:
        return ""
    for pattern in (
        r"/(?:posts|permalink)/(\d+)",
        r"[?&](?:story_fbid|fbid)=(\d+)",
        r"/(\d+)/?$",
    ):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _is_facebook_domain(domain: str) -> bool:
    host = (domain or "").strip().lower().lstrip(".").rstrip(".")
    return host == "facebook.com" or host.endswith(".facebook.com")


def parse_cookie_payload(raw: str) -> list[dict]:
    """Nạp cookie từ chuỗi JSON hoặc Netscape cookies.txt.

    Chỉ giữ cookie thuộc miền facebook.com và bắt buộc phải có cookie phiên
    (`c_user` + `xs`) — thiếu chúng thì session chắc chắn không đăng nhập được,
    tốt hơn là báo lỗi ngay lúc upload thay vì để worker chết lúc 3 giờ sáng.

    Returns:
        Danh sách cookie theo định dạng Playwright add_cookies().
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidCookieFile("File cookie rỗng")

    cookies = (
        _parse_json_cookies(text)
        if text[0] in "[{"
        else _parse_netscape_cookies(text)
    )

    if not cookies:
        raise InvalidCookieFile("Không tìm thấy cookie Facebook nào trong file")

    names = {c["name"] for c in cookies}
    missing = {"c_user", "xs"} - names
    if missing:
        raise InvalidCookieFile(
            "Thiếu cookie phiên bắt buộc: " + ", ".join(sorted(missing))
        )
    return cookies


def _coerce_expiry(raw) -> float:
    """Chuẩn hoá hạn dùng về unix giây; ``-1`` = cookie phiên (không hạn).

    Mỗi công cụ xuất cookie gọi trường này một kiểu (``expirationDate`` của
    Cookie-Editor là float, ``expiry`` của Netscape là int, có nơi ghi
    mili-giây). Giữ lại được hạn dùng là điều kiện để cảnh báo TRƯỚC khi
    clone chết, thay vì phát hiện lúc worker bị đá về trang đăng nhập.
    """
    if raw is None or isinstance(raw, bool):
        return -1
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return -1
    if value <= 0:
        return -1
    # Mốc 1e11 giây ≈ năm 5138 — quá xa để là giây thật, chắc chắn là mili-giây.
    if value > 1e11:
        value /= 1000.0
    return value


def _normalize(name, value, domain, path="/", expires=None) -> dict | None:
    if not name or value is None:
        return None
    if not _is_facebook_domain(domain):
        return None
    domain = domain.strip().lower()
    return {
        "name": str(name),
        "value": str(value),
        "domain": domain if domain.startswith(".") else f".{domain.lstrip('.')}",
        "path": path or "/",
        "expires": _coerce_expiry(expires),
    }


def _parse_json_cookies(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidCookieFile(f"JSON không hợp lệ: {exc}") from exc

    # Hỗ trợ:
    # 1. {"cookies": [...]}
    # 2. Mảng phẳng [...] (J2TEAM Cookies, Cookie-Editor, extension chuẩn)
    # 3. Object mapping {name: value} hoặc {name: {value: ...}}
    if isinstance(data, dict):
        if "cookies" in data and isinstance(data["cookies"], list):
            data = data["cookies"]
        elif not any(k in ("name", "value") for k in data.keys()):
            # Chuyển object key-value { "c_user": "...", "xs": "..." } thành mảng chuẩn
            flattened = []
            for k, v in data.items():
                if isinstance(v, dict):
                    cookie_dict = dict(v)
                    cookie_dict.setdefault("name", k)
                    cookie_dict.setdefault("domain", ".facebook.com")
                    flattened.append(cookie_dict)
                elif isinstance(v, (str, int, float)):
                    flattened.append({
                        "name": k,
                        "value": str(v),
                        "domain": ".facebook.com",
                    })
            data = flattened
    if not isinstance(data, list):
        raise InvalidCookieFile("JSON cookie phải là mảng hoặc có khoá 'cookies'")

    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        domain = item.get("domain") or ""
        if not domain and item.get("url"):
            domain = (urlsplit(str(item["url"])).hostname or "")
        cookie = _normalize(
            item.get("name"),
            item.get("value"),
            domain,
            item.get("path", "/"),
            item.get("expirationDate", item.get("expires", item.get("expiry"))),
        )
        if cookie:
            out.append(cookie)
    return out



def _parse_netscape_cookies(text: str) -> list[dict]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            fields = re.split(r"\s+", line)
        if len(fields) < 7:
            continue
        domain, _flag, path, _secure, expiry, name, value = fields[:7]
        cookie = _normalize(name, value, domain, path, expiry)
        if cookie:
            out.append(cookie)
    return out


def summarize_cookies(cookies: list[dict]) -> dict:
    """Tóm tắt cookie để trả về API mà KHÔNG lộ giá trị nhạy cảm."""
    names = sorted({c.get("name", "") for c in cookies if c.get("name")})
    account_id = ""
    for cookie in cookies:
        if cookie.get("name") == "c_user":
            account_id = str(cookie.get("value", ""))
            break
    health = cookie_health(cookies)
    return {
        "cookie_count": len(cookies),
        "cookie_names": names,
        "fb_user_id": account_id,
        "expires_at": health["expires_at"],
        "days_left": health["days_left"],
    }


def parse_query_group_key(url: str) -> str:
    """Lấy group key từ tham số ?set=gm.<id> nếu có (link ảnh trong group)."""
    query = parse_qs(urlsplit(url).query)
    value = (query.get("set") or [""])[0]
    match = re.match(r"^gm\.(\d+)$", value)
    return match.group(1) if match else ""


# ── Sức khoẻ cookie ────────────────────────────────────────────────────────
# Cookie Facebook hết hạn thì clone chết im lặng: worker vẫn chạy, vẫn mở
# browser, chỉ là bị đá về trang đăng nhập. Vì vậy hạn dùng phải được giữ lại
# từ lúc nạp file chứ không thể suy ra sau.
ESSENTIAL_COOKIES = ("c_user", "xs")

# Còn dưới ngần này ngày thì phải báo trước để người dùng kịp lấy cookie mới.
EXPIRY_WARNING_DAYS = 3


def cookie_expiry(cookies: list[dict]) -> datetime | None:
    """Thời điểm hết hạn SỚM NHẤT trong các cookie phiên bắt buộc.

    Trả về ``None`` khi cookie không mang hạn dùng (cookie phiên) — trường hợp
    này không kết luận được gì, và im lặng vẫn tốt hơn là báo động giả.
    """
    stamps = [
        c["expires"]
        for c in cookies or []
        if c.get("name") in ESSENTIAL_COOKIES and isinstance(c.get("expires"), (int, float))
        and c["expires"] > 0
    ]
    if not stamps:
        return None
    return datetime.fromtimestamp(min(stamps), tz=timezone.utc)


def cookie_health(cookies: list[dict] | None, now: datetime | None = None) -> dict:
    """Chẩn đoán bộ cookie của một clone (hàm thuần — test offline được).

    Returns:
        dict với ``ok`` (dùng được ngay không), ``reason`` (lý do hỏng, rỗng
        nếu ổn), ``missing`` / ``expired`` (tên cookie), ``expires_at`` và
        ``days_left`` (``None`` = cookie phiên, không có hạn).
    """
    now = now or datetime.now(timezone.utc)
    items = [c for c in (cookies or []) if isinstance(c, dict)]

    if not items:
        return {
            "ok": False,
            "reason": "Chưa nạp cookie",
            "missing": list(ESSENTIAL_COOKIES),
            "expired": [],
            "expires_at": None,
            "days_left": None,
            "cookie_count": 0,
        }

    names = {c.get("name") for c in items}
    missing = [name for name in ESSENTIAL_COOKIES if name not in names]

    expired = []
    for cookie in items:
        stamp = cookie.get("expires")
        if cookie.get("name") in ESSENTIAL_COOKIES and isinstance(stamp, (int, float)):
            if 0 < stamp <= now.timestamp():
                expired.append(str(cookie.get("name")))

    expires_at = cookie_expiry(items)
    days_left = (
        round((expires_at - now).total_seconds() / 86400, 1) if expires_at else None
    )

    if missing:
        reason = "Thiếu cookie phiên: " + ", ".join(missing)
    elif expired:
        reason = "Cookie đã hết hạn: " + ", ".join(sorted(set(expired)))
    else:
        reason = ""

    return {
        "ok": not missing and not expired,
        "reason": reason,
        "missing": missing,
        "expired": sorted(set(expired)),
        "expires_at": expires_at,
        "days_left": days_left,
        "cookie_count": len(items),
    }
