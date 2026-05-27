from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from vane.core.config import settings
from vane.db.engine import AsyncSessionLocal
from vane.db.models import Signal, Trade
from vane.markets.polymarket_client import PolymarketClient
from vane.trading.signals import TradingSignal

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    success: bool
    trade_id: str | None = None
    order_id: str | None = None
    filled_price: float | None = None
    filled_size: float | None = None
    error: str | None = None


class TradeExecutor:
    """Execute trades: paper or live, with risk checks."""

    def __init__(self, mode: str | None = None) -> None:
        self._mode = mode or settings.trading_mode
        self._polymarket = PolymarketClient()
        self._daily_trades = 0
        self._daily_pnl = 0.0
        self._last_reset = datetime.date.today()

    async def close(self) -> None:
        await self._polymarket.close()

    async def execute_signal(self, signal: TradingSignal) -> ExecutionResult:
        """Execute a single trading signal."""
        self.reset_daily_if_needed()

        # Risk checks
        if self._daily_trades >= settings.max_trades_per_day:
            return ExecutionResult(False, error="Max daily trades reached")
        if self._daily_pnl <= -settings.max_daily_loss_usd:
            return ExecutionResult(False, error="Daily loss limit reached")
        if (
            not signal.suggested_size_usd
            or signal.suggested_size_usd < settings.min_position_size_usd
        ):
            return ExecutionResult(False, error="Position size too small")

        # Persist signal
        async with AsyncSessionLocal() as session:
            db_signal = Signal(
                market_id=signal.market_id,
                token_id=signal.token_id,
                city=signal.city,
                event_date=signal.date,
                bin_label=signal.bin_label,
                direction=signal.direction,
                edge=Decimal(str(signal.edge)),
                our_prob=Decimal(str(signal.our_prob)),
                market_price=Decimal(str(signal.market_price)),
                confidence=Decimal(str(signal.confidence)) if signal.confidence else None,
                suggested_size_usd=Decimal(str(signal.suggested_size_usd)),
            )
            session.add(db_signal)
            await session.flush()

            # Execute
            if self._mode == "paper":
                result = await self._paper_execute(signal)
            elif self._mode == "live":
                if not settings.trading_enabled:
                    return ExecutionResult(False, error="Trading disabled")
                result = await self._live_execute(signal)
            else:
                return ExecutionResult(False, error=f"Unknown mode: {self._mode}")

            # Persist trade
            trade = Trade(
                market_id=signal.market_id,
                condition_id=None,
                token_id=signal.token_id,
                city=signal.city,
                event_date=signal.date,
                bin_label=signal.bin_label,
                direction=signal.direction,
                side="BUY",
                order_type="LIMIT",
                status="FILLED" if result.success else "FAILED",
                mode=self._mode,
                entry_price=Decimal(str(signal.market_price)),
                filled_price=Decimal(str(result.filled_price)) if result.filled_price else None,
                size_usd=Decimal(str(signal.suggested_size_usd)),
                filled_size=Decimal(str(result.filled_size)) if result.filled_size else None,
                edge=Decimal(str(signal.edge)),
                our_prob=Decimal(str(signal.our_prob)),
                market_price=Decimal(str(signal.market_price)),
                confidence=Decimal(str(signal.confidence)) if signal.confidence else None,
                venue_order_id=result.order_id,
                trade_id=result.trade_id,
                error=result.error,
            )
            session.add(trade)
            await session.flush()

            # Link signal to trade
            db_signal.acted_on = True
            db_signal.trade_id = trade.id

            await session.commit()

            if result.success:
                self._daily_trades += 1

            return result

    async def _paper_execute(self, signal: TradingSignal) -> ExecutionResult:
        """Simulate a fill with slippage."""
        trade_id = (
            f"paper-{signal.city}-{signal.date}-{signal.direction}"
            f"-{datetime.datetime.utcnow().timestamp()}"
        )
        slippage = 0.005  # 0.5% simulated slippage
        filled_price = signal.market_price + (slippage if signal.direction == "YES" else -slippage)
        filled_price = max(0.01, min(0.99, filled_price))

        logger.info(
            "PAPER trade: %s %s %s at %.4f (size: $%.2f)",
            signal.direction,
            signal.city,
            signal.bin_label,
            filled_price,
            signal.suggested_size_usd,
        )
        return ExecutionResult(
            success=True,
            trade_id=trade_id,
            filled_price=filled_price,
            filled_size=signal.suggested_size_usd,
        )

    async def _live_execute(self, signal: TradingSignal) -> ExecutionResult:
        """Place a real order on Polymarket CLOB."""
        async with self._polymarket:
            # Place limit order slightly better than market
            if signal.direction == "YES":
                limit_price = signal.market_price - 0.01
            else:
                limit_price = signal.market_price + 0.01
            limit_price = max(0.01, min(0.99, limit_price))

            result = await self._polymarket.place_limit_order(
                token_id=signal.token_id,
                side="BUY",
                price=limit_price,
                size=signal.suggested_size_usd,
            )

            if result.get("ok"):
                logger.info(
                    "LIVE trade: %s %s at %.4f (order: %s)",
                    signal.direction,
                    signal.city,
                    limit_price,
                    result.get("order_id"),
                )
                return ExecutionResult(
                    success=True,
                    order_id=result.get("order_id"),
                    filled_price=limit_price,
                    filled_size=signal.suggested_size_usd,
                )
            else:
                logger.error("LIVE trade failed: %s", result.get("message") or result.get("error"))
                return ExecutionResult(
                    success=False,
                    error=result.get("message") or result.get("error") or "Unknown error",
                )

    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions from Polymarket."""
        async with self._polymarket:
            return await self._polymarket.list_positions()

    async def get_open_orders(self) -> list[dict[str, Any]]:
        """Get open orders from Polymarket."""
        async with self._polymarket:
            return await self._polymarket.list_open_orders()

    def reset_daily_if_needed(self) -> None:
        today = datetime.date.today()
        if today != self._last_reset:
            self._daily_trades = 0
            self._daily_pnl = 0.0
            self._last_reset = today
