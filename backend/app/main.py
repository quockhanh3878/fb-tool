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
from app.database import dispose_engine, init_models
from app.routers import (
    auth,
    billing,
    campaigns,
    clones,
    health,
    mentions,
    posts,
    stats,
    telegram_webhook,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # SQLite (dev/test) tự tạo bảng; PostgreSQL dùng Alembic để có lịch sử migration.
    if "sqlite" in settings.database_url:
        await init_models()
    yield
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
    ):
        app.include_router(module.router)

    @app.get("/health", tags=["system"])
    async def healthcheck():
        return {"status": "ok", "version": settings.app_version}

    return app


app = create_app()
