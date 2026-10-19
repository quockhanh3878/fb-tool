# plan: docs/plans/community_job_runner_plan.md
"""Optional Discord Gateway worker for desktop DM registration."""
import asyncio
import logging

from app.config import get_settings
from app.database import get_session_factory
from app.services.discord_registration import handle_discord_dm

logger = logging.getLogger("commhunter.discord_bot")

try:
    import discord
except ImportError:  # pragma: no cover - exercised only in incomplete installations
    discord = None


class DiscordBot:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._client = None

    @property
    def configured(self) -> bool:
        return bool(get_settings().discord_bot_token.strip())

    def start(self) -> None:
        if self._task is not None or not self.configured:
            return
        if discord is None:
            logger.error("Discord bot da cau hinh nhung thieu dependency discord.py")
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.close()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._client = None

    async def _run(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_message(message) -> None:
            if message.author.bot or message.guild is not None:
                return
            async with get_session_factory()() as db:
                reply = await handle_discord_dm(
                    db,
                    discord_user_id=str(message.author.id),
                    display_name=str(message.author),
                    content=message.content,
                )
                await db.commit()
            await message.channel.send(reply)

        try:
            await client.start(get_settings().discord_bot_token, reconnect=True)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Discord bot gateway stopped")
        finally:
            self._client = None


discord_bot = DiscordBot()
