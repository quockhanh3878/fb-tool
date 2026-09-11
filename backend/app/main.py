"""
CommHunter AI — FastAPI entry point (Phase 2+).

Chạy dev:
    uvicorn app.main:app --reload --port 8000
Chạy production: xem docker-compose.yaml (api + worker + beat + db + redis).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import dispose_engine, get_session_factory, init_models
from app.routers import (
    auth,
    billing,
    campaigns,
    clones,
    health,
    mentions,
    posts,
    settings as settings_router,
    stats,
    telegram_webhook,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # SQLite (dev/test) tự tạo bảng; PostgreSQL dùng Alembic để có lịch sử migration.
    if "sqlite" in settings.database_url:
        await init_models()

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

    yield

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (
        auth,
        campaigns,
        clones,
        posts,
        mentions,
        stats,
        health,
        billing,
        telegram_webhook,
        settings_router,
    ):
        app.include_router(module.router)

    @app.get("/health", tags=["system"])
    async def healthcheck():
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
