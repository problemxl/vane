from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from vane.trading.executor import TradeExecutor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("")
async def get_positions() -> dict[str, Any]:
    """Get current open positions from Polymarket."""
    executor = TradeExecutor()
    try:
        positions = await executor.get_positions()
    finally:
        await executor.close()

    return {
        "positions": positions,
        "count": len(positions),
    }


@router.get("/orders")
async def get_open_orders() -> dict[str, Any]:
    """Get current open orders from Polymarket."""
    executor = TradeExecutor()
    try:
        orders = await executor.get_open_orders()
    finally:
        await executor.close()

    return {
        "orders": orders,
        "count": len(orders),
    }
