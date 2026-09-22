"""Strict destinations for browser navigation and requests."""
from urllib.parse import unquote, urlsplit, urlunsplit


FACEBOOK_HOSTS = frozenset({"facebook.com", "www.facebook.com", "m.facebook.com", "mbasic.facebook.com", "web.facebook.com"})
RESOURCE_DOMAINS = ("facebook.com", "fbcdn.net", "fbsbx.com")


def facebook_url(value: str, *, group: bool = False) -> str:
    if not isinstance(value, str) or not 5 <= len(value) <= 500:
        raise ValueError("URL Facebook không hợp lệ")
    if any(ord(character) < 33 for character in value) or "\\" in value:
        raise ValueError("URL contains invalid characters")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or parsed.hostname not in FACEBOOK_HOSTS
        or parsed.username is not None or parsed.password is not None
        or parsed.port not in (None, 443) or parsed.fragment
    ):
        raise ValueError("Chỉ chấp nhận HTTPS tới Facebook")
    path = unquote(parsed.path)
    if path.startswith("//") or "\\" in path or any(part in (".", "..") for part in path.split("/")):
        raise ValueError("Invalid Facebook path")
    if group and not path.startswith("/groups/"):
        raise ValueError("Cần URL nhóm Facebook")
    if path in ("/l.php", "/flx/warn/"):
        raise ValueError("Redirect URLs are not supported")
    return urlunsplit(("https", parsed.hostname, parsed.path, parsed.query, ""))


def browser_request_allowed(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        return (
            parsed.scheme == "https" and parsed.port in (None, 443)
            and parsed.username is None and parsed.password is None
            and any(host == domain or host.endswith("." + domain) for domain in RESOURCE_DOMAINS)
        )
    except (TypeError, ValueError):
        return False