from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from vane.api.lifespan import lifespan
from vane.api.routers import markets, positions, signals, trading, weather
from vane.core.config import settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Vane",
        description="Polymarket weather trading bot with Telegram integration",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Trusted host validation ─────────────────────────────────
    # Only active when ALLOWED_HOSTS is set (empty = skip)
    if settings.allowed_hosts:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts,
        )

    # ── Health check ────────────────────────────────────────────
    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        response: dict[str, Any] = {"status": "ok"}

        # Include scheduler status if available
        if hasattr(request.app.state, "scheduler"):
            try:
                response["scheduler"] = request.app.state.scheduler.get_status()
            except Exception:
                response["scheduler"] = {"error": "unavailable"}

        return response

    # ── API routers ─────────────────────────────────────────────
    app.include_router(trading.router, prefix="/api/v1")
    app.include_router(positions.router, prefix="/api/v1")
    app.include_router(signals.router, prefix="/api/v1")
    app.include_router(weather.router, prefix="/api/v1")
    app.include_router(markets.router, prefix="/api/v1")

    return app


app = create_app()
