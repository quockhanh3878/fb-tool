# plan: docs/plans/community_job_runner_plan.md
"""Discord webhook delivery with strict mention and URL handling."""
from datetime import datetime
from urllib.parse import urlparse

import httpx

from app.config import get_settings

DISCORD_WEBHOOK_HOSTS = {"discord.com", "discordapp.com", "canary.discord.com", "ptb.discord.com"}
EVENT_FIELD = "Loại sự kiện"


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in DISCORD_WEBHOOK_HOSTS:
        raise ValueError("Discord webhook URL must use an approved HTTPS Discord host")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Discord webhook URL must not contain credentials or a custom port")
    if not parsed.path.startswith("/api/webhooks/"):
        raise ValueError("Invalid Discord webhook path")
    return url


def _safe_text(value: object, limit: int = 1024) -> str:
    text = str(value or "").replace("@everyone", "@ everyone").replace("@here", "@ here")
    return text[:limit]


def build_webhook_payload(
    *,
    event_type: str,
    summary: str,
    source: str,
    occurred_at: datetime | str,
    recipient_id: str = "",
    link: str = "",
) -> dict:
    timestamp = occurred_at.isoformat() if isinstance(occurred_at, datetime) else str(occurred_at)
    fields = [
        {"name": EVENT_FIELD, "value": _safe_text(event_type)},
        {"name": "Tóm tắt", "value": _safe_text(summary)},
        {"name": "Nguồn", "value": _safe_text(source)},
        {"name": "Thời gian", "value": _safe_text(timestamp)},
        {"name": "Người tiếp nhận", "value": _safe_text(f"<@{recipient_id}>" if recipient_id else "Chưa cấu hình")},
        {"name": "Link trực tiếp", "value": _safe_text(link or "Không có", 1024)},
    ]
    payload = {
        "embeds": [{"title": "CommHunter", "fields": fields}],
        "allowed_mentions": {"parse": [], "users": []},
    }
    if recipient_id.isdigit():
        payload["content"] = f"<@{recipient_id}>"
        payload["allowed_mentions"]["users"] = [recipient_id]
    return payload


class DiscordService:
    def __init__(self, webhook_url: str | None = None, client: httpx.AsyncClient | None = None):
        self.webhook_url = webhook_url if webhook_url is not None else get_settings().discord_webhook_url
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)

    async def send_payload(self, payload: dict) -> dict:
        if not self.enabled:
            return {"ok": False, "error": "discord_not_configured"}
        validate_webhook_url(self.webhook_url)
        client = self._client or httpx.AsyncClient(timeout=15)
        try:
            response = await client.post(self.webhook_url, json=payload)
            if response.status_code in (200, 204):
                return {"ok": True, "status": response.status_code}
            body = response.json() if response.content else {}
            result = {"ok": False, "status": response.status_code, "body": body}
            if response.status_code == 429:
                result["retry_after"] = max(1.0, float(body.get("retry_after", 30)))
            return result
        except Exception:
            return {"ok": False, "error": "discord_transport_error"}
        finally:
            if self._client is None:
                await client.aclose()
