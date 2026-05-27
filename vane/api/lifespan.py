from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from vane.core.config import settings
from vane.scheduler import SchedulerManager
from vane.telegram.bot import TelegramBot

logger = logging.getLogger(__name__)


class LifespanManager:
    """Manages startup/shutdown lifecycle: migrations + scheduler + Telegram bot."""

    def __init__(self) -> None:
        self._scheduler = SchedulerManager()
        self._telegram_bot = TelegramBot()
        self._telegram_app: Any = None

    async def startup(self) -> None:
        logger.info("Starting Vane services...")

        # ── Database migrations (after Infisical secrets are injected) ──
        await self._run_migrations()

        await self._scheduler.start()

        if settings.telegram_bot_token:
            try:
                self._telegram_app = await self._telegram_bot.initialize()
                logger.info("Telegram bot initialized")
            except Exception as exc:
                logger.warning("Telegram bot init failed: %s", exc)
        else:
            logger.info("No TELEGRAM_BOT_TOKEN set; Telegram disabled")

    async def shutdown(self) -> None:
        logger.info("Shutting down Vane services...")
        await self._scheduler.stop()
        logger.info("Shutdown complete")

    @staticmethod
    async def _run_migrations() -> None:
        """Run alembic migrations in a subprocess.

        Uses a subprocess to avoid event-loop conflicts (alembic uses
        asyncio.run() internally). The subprocess inherits os.environ
        including DATABASE_URL injected by Infisical in this process.

        Failure is non-fatal — local dev with SQLite may not have
        alembic configured, or the DB may not be reachable yet.
        """
        import subprocess
        import sys

        try:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Database migrations applied successfully")
                if result.stderr:
                    logger.debug("alembic stderr: %s", result.stderr.strip())
            else:
                logger.warning(
                    "Database migration returned %d: %s",
                    result.returncode,
                    result.stderr.strip()[:200] if result.stderr else "no output",
                )
        except Exception as exc:
            logger.warning("Database migration skipped (non-fatal): %s", exc)

    @property
    def scheduler_status(self) -> dict[str, Any]:
        return self._scheduler.get_status()

    @property
    def scheduler(self) -> SchedulerManager:
        return self._scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = LifespanManager()
    await manager.startup()
    app.state.scheduler = manager.scheduler
    yield
    await manager.shutdown()
