from __future__ import annotations

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from vane.core.config import settings
from vane.trading.executor import TradeExecutor
from vane.trading.signals import SignalGenerator

logger = logging.getLogger(__name__)


class SchedulerManager:
    """Manages APScheduler instance and all recurring jobs."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._running = False

    async def start(self) -> None:
        """Register all jobs and start the scheduler."""
        self._scheduler.add_job(
            self._run_market_scan,
            "interval",
            minutes=settings.scan_interval_minutes,
            id="market_scan",
            name="Scan weather markets",
        )
        self._scheduler.add_job(
            self._run_forecast_fetch,
            "interval",
            minutes=settings.forecast_fetch_interval_minutes,
            id="forecast_fetch",
            name="Fetch ensemble forecasts",
        )
        self._scheduler.add_job(
            self._run_trade_scan,
            "cron",
            hour=11,
            minute=0,
            id="trade_scan",
            name="Daily trade scan",
        )
        self._scheduler.add_job(
            self._run_daily_pnl,
            "cron",
            hour=0,
            minute=5,
            id="daily_pnl",
            name="Daily P&L reset",
        )
        self._scheduler.start()
        self._running = True
        logger.info("Scheduler started with %d jobs", len(self._scheduler.get_jobs()))

        # Run initial market scan in background (non-blocking)
        asyncio.create_task(self._run_market_scan())

    async def stop(self) -> None:
        """Gracefully stop the scheduler."""
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("Scheduler stopped")

    def get_status(self) -> dict[str, Any]:
        """Current scheduler status for health/status endpoints."""
        jobs = [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            }
            for job in self._scheduler.get_jobs()
        ]
        return {
            "running": self._running,
            "job_count": len(jobs),
            "jobs": jobs,
        }

    # ── Job implementations ─────────────────────────────────────

    async def _run_market_scan(self) -> None:
        """Scan weather markets and log opportunities."""
        logger.info("Running market scan...")
        try:
            generator = SignalGenerator()
            signals = await generator.generate_signals()
            await generator.close()
            logger.info("Market scan complete: %d signals", len(signals))
        except Exception as exc:
            logger.error("Market scan error: %s", exc)

    async def _run_forecast_fetch(self) -> None:
        """Fetch forecasts for tracked cities."""
        logger.info("Running forecast fetch...")
        try:
            # In a full implementation, fetch forecasts for all tracked cities
            # and persist to the database. For now, log that it ran.
            logger.info("Forecast fetch complete")
        except Exception as exc:
            logger.error("Forecast fetch error: %s", exc)

    async def _run_trade_scan(self) -> None:
        """Evaluate signals and execute trades."""
        logger.info("Running trade scan...")
        try:
            generator = SignalGenerator()
            signals = await generator.generate_signals()
            await generator.close()

            if signals and settings.trading_enabled:
                executor = TradeExecutor()
                # Execute top signal only
                result = await executor.execute_signal(signals[0])
                await executor.close()
                logger.info(
                    "Trade scan: executed %s %s — success=%s",
                    signals[0].direction,
                    signals[0].city,
                    result.success,
                )
            else:
                logger.info(
                    "Trade scan: %d signals, trading_enabled=%s",
                    len(signals),
                    settings.trading_enabled,
                )
        except Exception as exc:
            logger.error("Trade scan error: %s", exc)

    async def _run_daily_pnl(self) -> None:
        """Reset daily stats and compute P&L."""
        logger.info("Running daily P&L computation...")
        try:
            executor = TradeExecutor()
            executor.reset_daily_if_needed()
            logger.info("Daily P&L computation complete")
        except Exception as exc:
            logger.error("Daily P&L error: %s", exc)
