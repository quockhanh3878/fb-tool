# plan: docs/plans/phase2_dashboard_detail.md
"""Smoke test offline cho kho ảnh và hợp đồng media của bài đăng."""

import asyncio
import base64
import os
import tempfile
from pathlib import Path

import httpx
from httpx import ASGITransport


def test_upload_and_reference_media():
    asyncio.run(_run())


async def _run():
    media_root = Path(tempfile.mkdtemp()) / "media"
    os.environ.update(
        APP_ENV="test",
        RUN_MODE="saas",
        DEBUG="false",
        DATABASE_URL=f"sqlite+aiosqlite:///{Path(tempfile.mkdtemp()) / 'publishing_media.db'}",
        PUBLISHING_MEDIA_ROOT=str(media_root),
        JWT_SECRET="offline-media-test-secret-32-bytes-minimum-2026",
        COOKIE_ENCRYPTION_KEY=base64.urlsafe_b64encode(bytes(range(32))).decode(),
        TELEGRAM_BOT_TOKEN="",
        OPENAI_API_KEY="",
        AUTH_RATE_LIMIT_PER_MINUTE="100",
    )

    from app.config import get_settings
    from app.database import reset_engine_cache

    get_settings.cache_clear()
    reset_engine_cache()
    from app.database import init_models
    from app.main import app

    await init_models()
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        registered = await client.post(
            "/api/auth/register",
            json={"email": f"media-{Path(tempfile.mkdtemp()).name}@example.com", "password": "matkhau123", "display_name": "Media"},
        )
        assert registered.status_code == 201, registered.text
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        uploaded = await client.post(
            "/api/publishing/media",
            headers=headers,
            files={"file": ("anh.png", b"\x89PNG\r\n\x1a\nimage-bytes", "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text
        media = uploaded.json()
        assert media["reference"].startswith("media://")

        created = await client.post(
            "/api/publishing",
            headers=headers,
            json={
                "content_template": "Bai dang co anh",
                "media_urls": [media["reference"]],
                "target_groups": [{"group_url": "https://www.facebook.com/groups/media-test/"}],
                "auto_bump": False,
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["media_urls"] == [media["reference"]]

        poster = await client.post(
            "/api/clones",
            headers=headers,
            json={"display_name": "Poster media", "role": "poster", "daily_post_limit": 5},
        )
        assert poster.status_code == 201, poster.text
        poster_id = poster.json()["id"]
        cookie = b'[{"name":"c_user","value":"100012345","domain":".facebook.com","path":"/"},{"name":"xs","value":"abc:xyz","domain":".facebook.com","path":"/"}]'
        activated = await client.post(
            f"/api/clones/{poster_id}/upload-cookie",
            headers=headers,
            files={"file": ("cookies.json", cookie, "application/json")},
        )
        assert activated.status_code == 200, activated.text
        activated = await client.post(
            f"/api/clones/{poster_id}/transition",
            headers=headers,
            json={"event": "warmup_complete"},
        )
        assert activated.status_code == 200, activated.text

        publish_with_media = await client.post(
            "/api/publishing",
            headers=headers,
            json={
                "clone_account_id": poster_id,
                "content_template": "Bai dang co anh duoc gui sang composer",
                "media_urls": [media["reference"]],
                "target_groups": [{"group_url": "https://www.facebook.com/groups/media-test/"}],
                "auto_bump": False,
            },
        )
        assert publish_with_media.status_code == 201, publish_with_media.text

        from app.services import publisher_service

        captured_media_paths: list[list[str]] = []

        async def fake_publish(_clone, group_url, _content, _cookies=None, *, media_paths=None):
            captured_media_paths.append(list(media_paths or []))
            return {
                "status": "published",
                "post_url": f"{group_url}posts/offline-media-test",
                "error": None,
            }

        original_publish = publisher_service.publish_post_real
        publisher_service.publish_post_real = fake_publish
        try:
            from app.database import get_session_factory

            async with get_session_factory()() as db:
                published = await publisher_service.execute_publish(
                    db, publish_with_media.json()["id"]
                )
                await db.commit()
        finally:
            publisher_service.publish_post_real = original_publish
        assert published["published_count"] == 1
        assert len(captured_media_paths) == 1
        assert len(captured_media_paths[0]) == 1
        assert Path(captured_media_paths[0][0]).is_file()

        rejected = await client.post(
            "/api/publishing",
            headers=headers,
            json={
                "content_template": "Bai dang co anh",
                "media_urls": ["C:/secret/image.png"],
                "target_groups": [{"group_url": "https://www.facebook.com/groups/media-test/"}],
                "auto_bump": False,
            },
        )
        assert rejected.status_code == 422, rejected.text
