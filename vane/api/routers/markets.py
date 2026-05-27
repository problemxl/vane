from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from vane.markets.polymarket_client import PolymarketClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("/weather")
async def get_weather_markets(limit: int = 50) -> dict[str, Any]:
    """Get active weather markets from Polymarket."""
    client = PolymarketClient()
    try:
        async with client:
            markets = await client.list_weather_markets(limit=limit)
    finally:
        await client.close()

    return {
        "markets": markets,
        "count": len(markets),
    }
