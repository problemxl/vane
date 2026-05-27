from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from vane.core.config import settings
from vane.trading.executor import TradeExecutor
from vane.trading.signals import SignalGenerator, TradingSignal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trading", tags=["trading"])


class ScanRequest(BaseModel):
    target_date: str | None = None
    min_edge: float | None = None


class ExecuteRequest(BaseModel):
    market_id: str
    token_id: str
    direction: str


@router.post("/scan")
async def trigger_scan(req: ScanRequest | None = None) -> dict[str, Any]:
    """Trigger a manual market scan and return signals."""
    req = req or ScanRequest()
    target = (
        datetime.date.fromisoformat(req.target_date)
        if req.target_date
        else datetime.date.today() + datetime.timedelta(days=1)
    )
    generator = SignalGenerator()
    try:
        signals = await generator.generate_signals(target_date=target)
    finally:
        await generator.close()

    return {
        "signals": [_signal_to_dict(s) for s in signals],
        "count": len(signals),
        "target_date": target.isoformat(),
    }


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Get current trading status."""
    return {
        "mode": settings.trading_mode,
        "trading_enabled": settings.trading_enabled,
        "bankroll_usd": settings.bankroll_usd,
        "max_position_size_usd": settings.max_position_size_usd,
        "max_total_exposure_usd": settings.max_total_exposure_usd,
        "max_daily_loss_usd": settings.max_daily_loss_usd,
        "min_edge_threshold": settings.min_edge_threshold,
        "kelly_fraction": settings.kelly_fraction,
    }


@router.post("/execute")
async def execute_trade(req: ExecuteRequest) -> dict[str, Any]:
    """Execute a trade for a given signal."""
    generator = SignalGenerator()
    try:
        signals = await generator.generate_signals()
        signal = next(
            (s for s in signals if s.market_id == req.market_id and s.direction == req.direction),
            None,
        )
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
    finally:
        await generator.close()

    executor = TradeExecutor()
    try:
        result = await executor.execute_signal(signal)
    finally:
        await executor.close()

    return {
        "success": result.success,
        "trade_id": result.trade_id,
        "order_id": result.order_id,
        "filled_price": result.filled_price,
        "filled_size": result.filled_size,
        "error": result.error,
    }


def _signal_to_dict(signal: TradingSignal) -> dict[str, Any]:
    return {
        "city": signal.city,
        "date": signal.date,
        "bin_label": signal.bin_label,
        "market_id": signal.market_id,
        "token_id": signal.token_id,
        "direction": signal.direction,
        "market_price": signal.market_price,
        "our_prob": signal.our_prob,
        "edge": signal.edge,
        "confidence": signal.confidence,
        "suggested_size_usd": signal.suggested_size_usd,
        "ensemble_mean": signal.ensemble_mean,
        "ensemble_std": signal.ensemble_std,
    }
