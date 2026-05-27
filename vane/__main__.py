from __future__ import annotations

import logging

import uvicorn

from vane.core.config import settings

# Suppress noisy loggers before app creation
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

if __name__ == "__main__":
    uvicorn.run(
        "vane.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
