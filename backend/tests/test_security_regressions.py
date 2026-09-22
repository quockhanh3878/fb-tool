"""Synthetic integration tests; never contact Facebook, Telegram or AI."""
import asyncio
import base64
import importlib
import os
from datetime import timedelta
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

for dependency in ("sqlalchemy", "aiosqlite", "alembic", "jwt", "bcrypt", "cryptography", "celery", "redis", "email_validator"):
    if os.environ.get("REQUIRE_INTEGRATION_TESTS") == "1":
        importlib.import_module(dependency)
    else:
        pytest.importorskip(dependency)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.database import dispose_engine, get_session_factory, init_models, reset_engine_cache
from app.models import Campaign, CloneAccount, CommentAction, CommentScript, CommentLead, DiscoveredPost, PostPublish, PostPublishHistory, Subscription, User
from app.models.base import utcnow
from app.security import create_access_token


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    values = {
        "APP_ENV": "test", "RUN_MODE": "saas",
        "DATABASE_URL": "sqlite+aiosqlite:///" + (tmp_path / "synthetic.db").as_posix(),
        "JWT_SECRET": "synthetic-integration-test-secret-not-for-deployment",
        "COOKIE_ENCRYPTION_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode(),
        "DESKTOP_INSTANCE_SECRET": "synthetic-local-instance-not-for-deployment",
        "TELEGRAM_WEBHOOK_SECRET": "synthetic-webhook-secret", "TELEGRAM_BOT_TOKEN": "",
        "OPENAI_API_KEY": "", "BROWSER_CDP_ENDPOINT": "", "AUTH_RATE_LIMIT_PER_MINUTE": "1000",
        "CORS_ORIGINS": '["http://localhost:3000"]',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    reset_engine_cache()
    from app.dependencies import reset_rate_limits
    from app.services.crypto import _fernet
    from app.main import create_app
    from app.services.ai_service import AIService
    from app.services.notification_service import NotificationService
    from app.workers import browser_runtime

    _fernet.cache_clear()
    reset_rate_limits()

    def forbidden(*args, **kwargs):
        raise AssertionError("External service access is forbidden in tests")

    async def forbidden_async(*args, **kwargs):
        raise AssertionError("External service access is forbidden in tests")

    monkeypatch.setattr(AIService, "_get_client", forbidden)
    monkeypatch.setattr(NotificationService, "_call", forbidden_async)
    monkeypatch.setattr(browser_runtime, "load_phase1_modules", forbidden)
    yield create_app()
    get_settings.cache_clear()
    _fernet.cache_clear()


def exercise(scenario, *, initialize=True):
    async def run():
        try:
            if initialize:
                await init_models()
            await scenario()
        finally:
            await dispose_engine()
    asyncio.run(run())


def client(application):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test")


def auth(user_id):
    return {"Authorization": "Bearer " + create_access_token(user_id)}


async def seed():
    async with get_session_factory()() as db:
        owner = User(email="owner@example.com", hashed_password="synthetic-unused-hash")
        other = User(email="other@example.com", hashed_password="synthetic-unused-hash")
        admin = User(email="admin@example.com", hashed_password="synthetic-unused-hash", is_admin=True)
        db.add_all([owner, other, admin])
        await db.flush()
        db.add(Subscription(
            user_id=owner.id, plan="studio", max_groups=100, max_clones=20,
            max_comments_per_day=100, ai_comments_enabled=True, bump_enabled=True,
            payment_status="active", expires_at=utcnow() + timedelta(days=10),
        ))
        campaign = Campaign(user_id=owner.id, name="Synthetic campaign", is_active=True, max_comments_per_day=20)
        db.add(campaign)
        await db.flush()
        clone = CloneAccount(user_id=owner.id, display_name="Synthetic own clone", role="all", status="active")
        foreign = CloneAccount(user_id=other.id, display_name="Synthetic foreign clone", role="all", status="active")
        post = DiscoveredPost(
            campaign_id=campaign.id, content_hash="synthetic-post", post_url="https://www.facebook.com/groups/synthetic/posts/123",
            content_text="Synthetic offline content", status="new",
        )
        db.add_all([clone, foreign, post, CommentScript(
            campaign_id=campaign.id, name="Synthetic script", type="spintax", is_active=True,
            template_content="Đây là nội dung thử nghiệm hoàn toàn giả lập không gửi thật.",
        )])
        await db.commit()
        return SimpleNamespace(owner=owner.id, other=other.id, admin=admin.id, campaign=campaign.id, clone=clone.id, foreign=foreign.id, post=post.id)


def test_cross_tenant_clone_rejected_by_api_and_worker(application, monkeypatch):
    async def scenario():
        from app.workers import shooter_task

        data = await seed()
        calls = []

        async def browser(*args):
            calls.append(args)
            return "success"

        monkeypatch.setattr(shooter_task, "post_comment_real", browser)
        async with client(application) as api:
            response = await api.post(f"/api/posts/{data.post}/apply", headers=auth(data.owner), json={
                "clone_id": data.foreign, "comment_text": "Nội dung thử nghiệm hoàn toàn giả lập.",
            })
            assert response.status_code == 404
        async with get_session_factory()() as db:
            action = CommentAction(discovered_post_id=data.post, clone_account_id=data.foreign, status="queued", scheduled_at=utcnow())
            db.add(action)
            await db.commit()
            action_id = action.id
        assert (await shooter_task._execute(action_id))["skipped"] == "policy_denied"
        assert calls == []
        async with get_session_factory()() as db:
            assert (await db.get(CloneAccount, data.foreign)).daily_comment_count == 0
    exercise(scenario)


def test_payment_requires_admin_and_preserves_active_subscription(application):
    async def scenario():
        data = await seed()
        async with client(application) as api:
            order = await api.post("/api/billing/subscribe", headers=auth(data.owner), json={"plan": "pro", "months": 1})
            assert order.status_code == 200
            payload = {"order_id": order.json()["reference_code"], "transaction_reference": "synthetic-tx-0001", "amount_vnd": order.json()["amount_vnd"]}
            subscription = await api.get("/api/billing/subscription", headers=auth(data.owner))
            assert subscription.json()["payment_status"] == "active"
            assert (await api.post("/api/billing/confirm", headers=auth(data.owner), json=payload)).status_code == 403
            approved = await api.post("/api/billing/confirm", headers=auth(data.admin), json=payload)
            assert approved.status_code == 200
            repeated = await api.post("/api/billing/confirm", headers=auth(data.admin), json=payload)
            assert repeated.json()["expires_at"] == approved.json()["expires_at"]
            another = await api.post("/api/billing/subscribe", headers=auth(data.owner), json={"plan": "pro", "months": 1})
            payload["order_id"] = another.json()["reference_code"]
            assert (await api.post("/api/billing/confirm", headers=auth(data.admin), json=payload)).status_code == 409
    exercise(scenario)


def test_queue_is_idempotent_and_pause_cancels_pending_work(application):
    async def scenario():
        data = await seed()
        async with client(application) as api:
            path = f"/api/posts/{data.post}/apply"
            payload = {"clone_id": data.clone, "comment_text": "Nội dung thử nghiệm hoàn toàn giả lập."}
            first = await api.post(path, headers=auth(data.owner), json=payload)
            second = await api.post(path, headers=auth(data.owner), json=payload)
            assert first.status_code == second.status_code == 200
            assert first.json()["id"] == second.json()["id"]
            assert (await api.post(f"/api/campaigns/{data.campaign}/pause", headers=auth(data.owner))).status_code == 200
        async with get_session_factory()() as db:
            assert (await db.get(CommentAction, first.json()["id"])).status == "cancelled"
    exercise(scenario)


def test_worker_executes_once_and_releases_clone(application, monkeypatch):
    async def scenario():
        from app.workers import shooter_task
        from app.models.operations import ResourceLease

        data = await seed()
        calls = []

        async def browser(*args):
            calls.append(True)
            return "success"

        monkeypatch.setattr(shooter_task, "post_comment_real", browser)
        async with client(application) as api:
            response = await api.post(f"/api/posts/{data.post}/apply", headers=auth(data.owner), json={"clone_id": data.clone, "comment_text": "Đây là comment thử nghiệm không gửi thật."})
            assert response.status_code == 200
        action_id = response.json()["id"]
        assert (await shooter_task._execute(action_id))["status"] == "success"
        assert (await shooter_task._execute(action_id))["skipped"] == "action_not_queued"
        assert calls == [True]
        async with get_session_factory()() as db:
            assert await db.scalar(select(func.count(ResourceLease.resource))) == 0
    exercise(scenario)


def test_recovery_does_not_blindly_requeue_browser_side_effects(application):
    async def scenario():
        from app.workers.maintenance_task import recover_stale_jobs

        data = await seed()
        async with get_session_factory()() as db:
            action = CommentAction(discovered_post_id=data.post, status="in_progress", lease_expires_at=utcnow() - timedelta(seconds=1))
            publish = PostPublish(user_id=data.owner, content_template="Synthetic", status="publishing", lease_expires_at=utcnow() - timedelta(seconds=1))
            db.add_all([action, publish])
            await db.commit()
            ids = action.id, publish.id
        await recover_stale_jobs()
        async with get_session_factory()() as db:
            assert (await db.get(CommentAction, ids[0])).status == "unknown_outcome"
            assert (await db.get(PostPublish, ids[1])).status == "unknown_outcome"
    exercise(scenario)


def test_refresh_rotation_detects_reuse(application):
    async def scenario():
        async with client(application) as api:
            registered = await api.post("/api/auth/register", json={"email": "refresh@example.com", "password": "SyntheticPassword123"})
            assert registered.status_code == 201
            old = registered.json()["refresh_token"]
            rotated = await api.post("/api/auth/refresh", json={"refresh_token": old})
            assert rotated.status_code == 200
            assert rotated.json()["refresh_token"] != old
            assert (await api.post("/api/auth/refresh", json={"refresh_token": old})).status_code == 401
            assert (await api.post("/api/auth/refresh", json={"refresh_token": rotated.json()["refresh_token"]})).status_code == 401
    exercise(scenario)


def test_webhook_requires_secret_and_deduplicates_updates(application):
    async def scenario():
        from app.models.operations import TelegramUpdate

        data = await seed()
        async with get_session_factory()() as db:
            owner = await db.get(User, data.owner)
            owner.telegram_chat_id = "12345"
            await db.commit()
        update = {"update_id": 42, "callback_query": {"message": {"chat": {"id": 12345, "type": "private"}}, "data": f"apply:{data.post}"}}
        async with client(application) as api:
            assert (await api.post("/api/webhook/telegram", json=update)).status_code == 403
            headers = {"X-Telegram-Bot-Api-Secret-Token": "synthetic-webhook-secret"}
            first = await api.post("/api/webhook/telegram", headers=headers, json=update)
            second = await api.post("/api/webhook/telegram", headers=headers, json=update)
            assert first.status_code == second.status_code == 200
            assert second.json()["handled"] == "duplicate"
            get_settings().telegram_webhook_secret = ""
            assert (await api.post("/api/webhook/telegram", headers=headers, json=update)).status_code == 403
        async with get_session_factory()() as db:
            assert await db.scalar(select(func.count(CommentAction.id))) == 1
            assert await db.scalar(select(func.count(TelegramUpdate.id))) == 1
    exercise(scenario)


def test_desktop_requires_instance_secret_and_encrypts_settings(application):
    async def scenario():
        from app.models.app_setting import AppSetting

        data = await seed()
        get_settings().run_mode = "desktop"
        headers = {"X-Desktop-Instance-Secret": get_settings().desktop_instance_secret}
        async with client(application) as api:
            assert (await api.post("/api/auth/desktop-session")).status_code == 403
            response = await api.post("/api/auth/desktop-session", headers=headers)
            assert response.status_code == 200
            desktop_headers = {**headers, "Authorization": "Bearer " + response.json()["access_token"]}
            assert (await api.get("/api/settings", headers={**headers, **auth(data.owner)})).status_code == 403
            response = await api.put("/api/settings", headers=desktop_headers, json={"openai_api_key": "synthetic-api-key"})
            assert response.status_code == 200
        async with get_session_factory()() as db:
            row = await db.get(AppSetting, "openai_api_key")
            assert row.value.startswith("fernet:v1:")
            assert "synthetic-api-key" not in row.value
            assert await db.get(AppSetting, "cookie_encryption_key") is None
    exercise(scenario)


def test_desktop_can_skip_login_when_auth_is_explicitly_disabled(application):
    async def scenario():
        from app.services.desktop_service import DESKTOP_USER_EMAIL

        get_settings().run_mode = "desktop"
        get_settings().auth_required = False
        get_settings().desktop_instance_secret = ""
        async with client(application) as api:
            session = await api.post("/api/auth/desktop-session")
            assert session.status_code == 200
            profile = await api.get("/api/auth/me")
            assert profile.status_code == 200
            assert profile.json()["email"] == DESKTOP_USER_EMAIL

    exercise(scenario)


def test_publishing_alias_and_publish_now_only_schedule(application):
    async def scenario():
        data = await seed()
        async with client(application) as api:
            response = await api.get("/api/posts/publishing", headers=auth(data.owner))
            assert response.status_code == 200 and response.json()["items"] == []
            created = await api.post("/api/publishing", headers=auth(data.owner), json={
                "content_template": "Synthetic publish content", "auto_bump": False,
                "target_groups": [{"group_url": "https://www.facebook.com/groups/synthetic"}],
            })
            assert created.status_code == 201
            scheduled = await api.post(f"/api/publishing/{created.json()['id']}/publish-now", headers=auth(data.owner))
            assert scheduled.status_code == 202
            assert scheduled.json()["status"] == "scheduled"
    exercise(scenario)


def test_publish_comment_and_lead_history_are_queryable(application):
    async def scenario():
        data = await seed()
        async with get_session_factory()() as db:
            db.add(CommentAction(
                discovered_post_id=data.post,
                status="success",
                comment_content="Synthetic comment history",
                fb_comment_id="comment-001",
                comment_url="https://www.facebook.com/groups/synthetic/posts/123?comment_id=comment-001",
                executed_at=utcnow(),
            ))
            db.add(PostPublishHistory(
                user_id=data.owner,
                campaign_id=data.campaign,
                group_id="synthetic",
                group_name="Synthetic group",
                group_url="https://www.facebook.com/groups/synthetic",
                post_url="https://www.facebook.com/groups/synthetic/posts/999",
                status="published",
                content_snapshot="Synthetic publish history",
                published_at=utcnow(),
            ))
            db.add(CommentLead(
                campaign_id=data.campaign,
                fb_comment_id="lead-comment-001",
                content_hash="lead-hash-001",
                matched_keywords=["tim viet"],
                author_name="Synthetic lead",
                comment_text="Tôi đang tìm người viết truyện",
                post_url="https://www.facebook.com/groups/synthetic/posts/999",
                comment_url="https://www.facebook.com/groups/synthetic/posts/999?comment_id=lead-comment-001",
                status="new",
            ))
            await db.commit()

        async with client(application) as api:
            comments = await api.get("/api/comment-history", headers=auth(data.owner))
            assert comments.status_code == 200
            assert comments.json()["items"][0]["comment_url"].endswith("comment-001")
            publishes = await api.get("/api/publishing/history", headers=auth(data.owner))
            assert publishes.status_code == 200
            assert publishes.json()["items"][0]["post_url"].endswith("/999")
            leads = await api.get("/api/leads", headers=auth(data.owner))
            assert leads.status_code == 200
            lead = leads.json()["items"][0]
            assert lead["comment_url"].endswith("lead-comment-001")
            marked = await api.post(f"/api/leads/{lead['id']}/read", headers=auth(data.owner))
            assert marked.status_code == 200 and marked.json()["status"] == "read"
    exercise(scenario)


def test_sqlite_migration_is_versioned_and_idempotent(application):
    async def scenario():
        from sqlalchemy import text
        from app.services.migrations import migrate_database

        await migrate_database()
        await migrate_database()
        async with get_session_factory()() as db:
            assert await db.scalar(text("SELECT version_num FROM alembic_version")) == "0013"
    exercise(scenario, initialize=False)


def test_unversioned_database_is_not_silently_adopted(application):
    async def scenario():
        from app.services.migrations import migrate_database

        with pytest.raises(RuntimeError, match="Unversioned database"):
            await migrate_database()
    exercise(scenario)
