from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from vane.db.engine import get_db
from vane.db.models import Signal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("")
async def get_signals(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get recent signals from the database."""
    result = await db.execute(
        select(Signal).order_by(desc(Signal.created_at)).limit(limit)
    )
    signals = result.scalars().all()

    return {
        "signals": [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "city": s.city,
                "event_date": s.event_date,
                "bin_label": s.bin_label,
                "direction": s.direction,
                "edge": float(s.edge) if s.edge else None,
                "our_prob": float(s.our_prob) if s.our_prob else None,
                "market_price": float(s.market_price) if s.market_price else None,
                "confidence": float(s.confidence) if s.confidence else None,
                "suggested_size_usd": float(s.suggested_size_usd) if s.suggested_size_usd else None,
                "acted_on": s.acted_on,
                "trade_id": s.trade_id,
            }
            for s in signals
        ],
        "count": len(signals),
    }
