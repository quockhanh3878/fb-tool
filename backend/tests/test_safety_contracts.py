"""Offline contracts requiring only the preinstalled Python/web stack."""
import asyncio
import base64
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.middleware import BodyLimitMiddleware
from app.services.ai_service import AIService, Evaluation
from app.services.url_policy import browser_request_allowed, facebook_url
from app.workers.job_queue import SerialJobQueue

TEST_JWT = "synthetic-tests-only-not-for-deployment-123456789"
TEST_FERNET = base64.urlsafe_b64encode(bytes(range(32))).decode()


def settings(**changes):
    values = {
        "jwt_secret": TEST_JWT, "cookie_encryption_key": TEST_FERNET,
        "app_env": "test", "run_mode": "saas", "telegram_bot_token": "",
        "browser_cdp_endpoint": "",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("url", [
    "http://www.facebook.com/groups/demo", "https://127.0.0.1/test",
    "https://169.254.169.254/latest", "file:///etc/passwd",
    "https://facebook.com.evil.invalid/groups/demo", "https://facebook.com@evil.invalid/demo",
    "https://user:pass@www.facebook.com/groups/demo", "https://www.facebook.com:8080/groups/demo",
    "https://www.facebook.com/groups/../l.php", "https://www.facebook.com/%2e%2e/l.php",
    "https://www.facebook.com/l.php?u=https://evil.invalid", "https://www.facebook.com/groups/demo#fragment",
    "https://www.facebook.com\\@evil.invalid/demo", "https://www.facebook.com\n/groups/demo",
    "javascript:alert(1)", "https://[::1]/test",
])
def test_navigation_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        facebook_url(url)


@pytest.mark.parametrize("host", ["www.facebook.com", "facebook.com", "m.facebook.com"])
def test_navigation_accepts_facebook_group(host):
    url = f"https://{host}/groups/synthetic/posts/123"
    assert facebook_url(url, group=True) == url


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/", "https://facebook.com.evil.invalid/",
    "https://fbcdn.net.evil.invalid/", "http://www.facebook.com/",
    "https://169.254.169.254/", "https://user:pass@www.facebook.com/",
    "https://www.facebook.com:444/", "file:///test",
])
def test_browser_resource_policy_denies_external_destinations(url):
    assert not browser_request_allowed(url)


def test_browser_resource_policy_accepts_known_cdn():
    assert browser_request_allowed("https://static.xx.fbcdn.net/test.png")
    assert browser_request_allowed("https://www.facebook.com/groups/demo")


def test_security_settings_require_persistent_secrets():
    assert settings().cookie_encryption_key == TEST_FERNET
    for changes in ({"jwt_secret": ""}, {"jwt_secret": "dev-secret-doi-truoc-khi-len-production"}, {"cookie_encryption_key": ""}):
        with pytest.raises(ValidationError):
            settings(**changes)


def test_browser_automation_requires_explicit_enablement(monkeypatch):
    monkeypatch.delenv("BROWSER_AUTOMATION_ENABLED", raising=False)
    assert settings().browser_automation_enabled is False
    assert settings(browser_automation_enabled=True).browser_automation_enabled is True


def test_security_settings_fail_closed_for_deployment_modes():
    for changes in (
        {"run_mode": "desktop"}, {"run_mode": "unknown"},
        {"telegram_bot_token": "synthetic-token", "telegram_webhook_secret": ""},
        {"browser_cdp_endpoint": "http://localhost:9222"},
        {"app_env": "production", "debug": True}, {"cors_origins": ["*"]},
    ):
        with pytest.raises(ValidationError):
            settings(**changes)
    assert settings(run_mode="desktop", auth_required=False).auth_required is False
    with pytest.raises(ValidationError):
        settings(run_mode="saas", auth_required=False)


def test_cors_environment_is_json(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["http://localhost:3000"]')
    assert settings().cors_origins == ["http://localhost:3000"]
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    with pytest.raises(ValueError):
        settings()


def test_settings_do_not_render_secrets():
    rendered = repr(settings())
    assert TEST_JWT not in rendered
    assert TEST_FERNET not in rendered


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
def test_ai_score_is_finite_and_bounded(score):
    with pytest.raises(ValidationError):
        Evaluation(relevance_score=score)


def test_ai_rejects_malformed_extracted_data():
    with pytest.raises(ValidationError):
        Evaluation(relevance_score=0.8, extracted={"budget": {"instruction": "untrusted"}})


def test_ai_unconfigured_is_not_a_blanket_approval():
    async def scenario():
        result = await AIService().filter_post("Synthetic unrelated content", SimpleNamespace(
            whitelist_keywords=[], blacklist_keywords=[], min_relevance_score=0.7,
        ))
        assert result["relevance_score"] == 0
        assert "keyword_only" in result["reason"]
    asyncio.run(scenario())


def test_queue_coalesces_and_limits_backlog():
    async def scenario():
        queue = SerialJobQueue(maxsize=1)
        calls = []

        async def job():
            calls.append("done")

        assert await queue.enqueue(job, key="job:1")
        assert not await queue.enqueue(job, key="job:1")
        assert not await queue.enqueue(job, key="job:2")
        queue.start()
        await asyncio.wait_for(queue._queue.join(), 1)
        assert calls == ["done"]
        assert await queue.enqueue(job, key="job:1")
        await queue.stop()
        assert not queue._pending
        assert queue._queue.empty()
    asyncio.run(scenario())


def test_queue_failure_does_not_stop_worker():
    async def scenario():
        queue = SerialJobQueue()
        calls = []

        async def bad_job():
            raise RuntimeError("synthetic failure")

        async def good_job():
            calls.append(True)

        queue.start()
        await queue.enqueue(bad_job, key="bad")
        await queue.enqueue(good_job, key="good")
        await asyncio.wait_for(queue._queue.join(), 1)
        await queue.stop()
        assert calls == [True]
    asyncio.run(scenario())


def test_queue_timeout_releases_key_and_runs_next_job():
    async def scenario():
        queue = SerialJobQueue(default_timeout_seconds=0.01)
        calls = []
        never = asyncio.Event()

        async def stuck_job():
            await never.wait()

        async def next_job():
            calls.append("next")

        queue.start()
        assert await queue.enqueue(stuck_job, key="stuck")
        assert await queue.enqueue(next_job, key="next")
        await asyncio.wait_for(queue._queue.join(), 1)
        metrics = queue.readiness()
        await queue.stop()
        assert calls == ["next"]
        assert not queue._pending
        assert metrics["last_error_kind"] == "timeout"
        assert metrics["last_error_key"] == "stuck"

    asyncio.run(scenario())


@pytest.mark.parametrize("headers,chunks,expected", [
    ([(b"content-length", b"99")], [], 413),
    ([], [b"1234", b"5678"], 413),
    ([(b"content-length", b"invalid")], [], 400),
    ([], [b"12", b"34"], 200),
])
def test_body_limits_before_handler(headers, chunks, expected):
    async def scenario():
        messages = []
        incoming = [
            {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
            for index, chunk in enumerate(chunks)
        ]
        handler_calls = []

        async def receive():
            return incoming.pop(0) if incoming else {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        async def app(scope, receiver, sender):
            handler_calls.append(await receiver())
            await sender({"type": "http.response.start", "status": 200, "headers": []})
            await sender({"type": "http.response.body", "body": b"ok"})

        await BodyLimitMiddleware(app, max_bytes=6)({"type": "http", "headers": headers}, receive, send)
        assert messages[0]["status"] == expected
        assert bool(handler_calls) == (expected == 200)
    asyncio.run(scenario())


def test_input_schemas_reject_unsafe_data():
    pytest.importorskip("email_validator")
    from app.schemas import IngestPostsRequest, PostPublishCreate, RegisterRequest

    with pytest.raises(ValidationError) as error:
        RegisterRequest(email="user@example.com", password="é" * 37)
    assert error.value.errors()[0]["loc"] == ("password",)
    assert RegisterRequest(email="user@example.com", password="é" * 36).password == "é" * 36
    with pytest.raises(ValidationError):
        IngestPostsRequest(group_id="synthetic", posts=[{"text": "Synthetic", "url": "https://127.0.0.1/private"}])
    with pytest.raises(ValidationError):
        PostPublishCreate(content_template="Synthetic content", target_groups=[{"group_url": "https://example.invalid/group"}])
    with pytest.raises(ValidationError):
        PostPublishCreate(
            content_template="Synthetic content", target_groups=[{"group_url": "https://www.facebook.com/groups/demo"}],
            media_urls=["https://example.invalid/image.png"],
        )


def test_compose_private_dependencies_and_migration_gate():
    yaml = pytest.importorskip("yaml")
    root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((root / "backend/docker-compose.yaml").read_text())
    services = compose["services"]
    assert "ports" not in services["db"]
    assert "ports" not in services["redis"]
    assert services["api"]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert services["worker"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert "/ready" in services["api"]["healthcheck"]["test"][1]


def test_comment_input_preserves_identity_and_source():
    pytest.importorskip("email_validator")
    from app.schemas import IngestCommentsRequest

    request = IngestCommentsRequest(comments=[{
        "text": "Synthetic comment", "authorId": "123", "id": "456",
        "url": "https://www.facebook.com/groups/demo/posts/789",
    }])
    assert request.comments[0]["author_fb_id"] == "123"
    assert request.comments[0]["fbCommentId"] == "456"
    assert request.comments[0]["post_url"].endswith("/789")


def test_profile_cannot_self_assign_admin_or_unverified_telegram_chat():
    pytest.importorskip("email_validator")
    from app.schemas import UserUpdate

    with pytest.raises(ValidationError):
        UserUpdate(is_admin=True)
    with pytest.raises(ValidationError):
        UserUpdate(telegram_chat_id="12345")
    assert UserUpdate(telegram_chat_id=None).telegram_chat_id is None
