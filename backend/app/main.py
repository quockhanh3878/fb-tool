"""
CommHunter AI — FastAPI entry point (Phase 2+).

Chạy dev:
    uvicorn app.main:app --reload --port 8000
Chạy production: xem docker-compose.yaml (api + worker + beat + db + redis).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import get_settings
from app.database import dispose_engine, get_session_factory, init_models
from app.middleware import BodyLimitMiddleware
from app.services.migrations import migrate_database, schema_ready
from app.routers import (
    auth,
    billing,
    campaigns,
    clones,
    health,
    leads,
    mentions,
    posts,
    settings as settings_router,
    stats,
    telegram_webhook,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.app_env == "test":
        await init_models()
    elif "sqlite" in settings.database_url:
        await migrate_database()

    if settings.run_mode == "desktop":
        from app.services.app_settings_service import apply_to_runtime_settings
        from app.workers.scheduler import start_scheduler, stop_scheduler
        from app.workers.telegram_poller import telegram_poller

        # Nạp cấu hình DB (OpenAI key, Telegram token, khoá mã hoá cookie bền)
        # vào Settings singleton TRƯỚC khi bật scheduler / nhận request đầu tiên.
        async with get_session_factory()() as db:
            await apply_to_runtime_settings(db)

        start_scheduler()
        # Máy local không có URL public cho webhook -> nhận nút bấm qua long-polling.
        telegram_poller.start()

    try:
        yield
    finally:
        if settings.run_mode == "desktop":
            await telegram_poller.stop()
            await stop_scheduler()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "API nền tảng săn khách hàng & tự động tương tác nhóm Facebook. "
            "Mọi endpoint riêng tư đều yêu cầu Bearer access token."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        errors = [
            {"loc": error["loc"], "type": error["type"], "msg": error["msg"]}
            for error in exc.errors()
        ]
        return JSONResponse({"detail": errors}, status_code=422)

    for module in (
        auth,
        campaigns,
        clones,
        posts,
        mentions,
        leads,
        stats,
        health,
        billing,
        telegram_webhook,
        settings_router,
    ):
        app.include_router(module.router)

    @app.get("/health", tags=["system"])
    @app.get("/live", tags=["system"])
    async def healthcheck():
        return {"status": "ok", "version": settings.app_version}

    @app.get("/ready", tags=["system"])
    async def readiness():
        scheduler_state = None
        try:
            async with get_session_factory()() as db:
                if not await schema_ready(db):
                    raise RuntimeError("Schema not ready")
            if settings.run_mode == "desktop":
                from app.workers.scheduler import readiness_snapshot

                scheduler_state = readiness_snapshot()
                if scheduler_state["status"] != "ready":
                    raise RuntimeError("Desktop scheduler is not ready")
            if settings.run_mode == "saas" and settings.app_env != "test":
                from redis.asyncio import Redis

                async with Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2) as redis:
                    await redis.ping()
        except Exception:
            body = {"status": "not_ready"}
            if scheduler_state is not None:
                body["scheduler"] = scheduler_state
            return JSONResponse(body, status_code=503)
        body = {"status": "ready"}
        if scheduler_state is not None:
            body["scheduler"] = scheduler_state
        return body

    return app


app = create_app()
