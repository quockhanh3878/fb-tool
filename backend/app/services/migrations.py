"""Versioned startup migrations; unversioned customer DBs require explicit adoption."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.config import get_settings
from app.database import get_engine

SCHEMA_VERSION = "0017"


async def migrate_database():
    async with get_engine().begin() as connection:
        def upgrade(sync_connection):
            tables = set(inspect(sync_connection).get_table_names())
            if tables and "alembic_version" not in tables:
                raise RuntimeError(
                    "Unversioned database: back up and verify the existing schema before an explicit Alembic stamp; refusing automatic adoption"
                )
            config = Config()
            config.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
            config.attributes["connection"] = sync_connection
            command.upgrade(config, "head")

        await connection.run_sync(upgrade)


async def schema_ready(db) -> bool:
    await db.execute(text("SELECT 1"))
    if get_settings().app_env == "test":
        return True
    return await db.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_VERSION
