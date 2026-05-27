from __future__ import annotations

import logging
from typing import Any

from polymarket import PRODUCTION, AsyncPublicClient, AsyncSecureClient

from vane.core.config import settings

logger = logging.getLogger(__name__)


class PolymarketClient:
    """Unified Polymarket client wrapper using the official py-sdk."""

    def __init__(self) -> None:
        self._public: AsyncPublicClient | None = None
        self._secure: AsyncSecureClient | None = None

    async def __aenter__(self) -> PolymarketClient:
        self._public = AsyncPublicClient(environment=PRODUCTION)
        if settings.polymarket_private_key:
            self._secure = await AsyncSecureClient.create(
                private_key=settings.polymarket_private_key,
                wallet=settings.polymarket_wallet_address,
            )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._public:
            await self._public.close()
        if self._secure:
            await self._secure.close()

    # ── Discovery ────────────────────────────────────────────────

    async def list_weather_markets(
        self,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch active weather markets from Gamma API via the SDK."""
        markets: list[dict[str, Any]] = []
        paginator = self._public.list_markets(
            page_size=min(limit, 100),
        )

        async for page in paginator:
            for market in page.items:
                market_dict = self._market_to_dict(market)
                [t.lower() for t in market_dict.get("tags", [])]
                if self._is_weather_market(market_dict):
                    if (active and market_dict.get("active")) or (not active):
                        if (not closed and not market_dict.get("closed")) or closed:
                            markets.append(market_dict)
            if len(markets) >= limit:
                break

        logger.info("Discovered %d weather markets", len(markets))
        return markets[:limit]

    async def get_market(self, market_id: str) -> dict[str, Any] | None:
        """Fetch single market by ID."""
        try:
            market = await self._public.get_market(market_id=market_id)
            return self._market_to_dict(market)
        except Exception as exc:
            logger.warning("Failed to fetch market %s: %s", market_id, exc)
            return None

    async def get_orderbook(self, token_id: str) -> dict[str, Any]:
        """Fetch orderbook for a token."""
        try:
            book = await self._public.get_orderbook(token_id=token_id)
            return {
                "token_id": token_id,
                "bids": [
                    {"price": float(b.price), "size": float(b.size)} for b in (book.bids or [])
                ],
                "asks": [
                    {"price": float(a.price), "size": float(a.size)} for a in (book.asks or [])
                ],
            }
        except Exception as exc:
            logger.warning("Orderbook fetch failed for %s: %s", token_id, exc)
            return {"token_id": token_id, "bids": [], "asks": []}

    async def get_price(self, token_id: str, side: str = "BUY") -> float | None:
        """Get current CLOB price for a token."""
        try:
            # Use orderbook best bid/ask for price
            book = await self.get_orderbook(token_id)
            if side.upper() == "BUY" and book["asks"]:
                return book["asks"][0]["price"]
            if side.upper() == "SELL" and book["bids"]:
                return book["bids"][0]["price"]
            return None
        except Exception as exc:
            logger.warning("Price fetch failed for %s: %s", token_id, exc)
            return None

    # ── Trading (secure client) ─────────────────────────────────

    async def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> dict[str, Any]:
        """Place a limit order via the CLOB."""
        if not self._secure:
            raise RuntimeError("Secure client not initialized. Provide POLYMARKET_PRIVATE_KEY.")

        try:
            response = await self._secure.place_limit_order(
                token_id=token_id,
                side=side.upper(),
                price=str(price),
                size=str(size),
            )
            return {
                "ok": response.ok,
                "order_id": response.order_id if response.ok else None,
                "code": response.code if not response.ok else None,
                "message": response.message if not response.ok else None,
            }
        except Exception as exc:
            logger.error("Order placement failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def place_market_order(
        self,
        token_id: str,
        side: str,
        amount: float | None = None,
        shares: float | None = None,
        order_type: str = "FAK",
    ) -> dict[str, Any]:
        """Place a market order via the CLOB."""
        if not self._secure:
            raise RuntimeError("Secure client not initialized.")

        try:
            kwargs: dict[str, Any] = {
                "token_id": token_id,
                "side": side.upper(),
                "order_type": order_type,
            }
            if amount is not None:
                kwargs["amount"] = str(amount)
            if shares is not None:
                kwargs["shares"] = str(shares)

            response = await self._secure.place_market_order(**kwargs)
            return {
                "ok": response.ok,
                "order_id": response.order_id if response.ok else None,
                "code": response.code if not response.ok else None,
                "message": response.message if not response.ok else None,
            }
        except Exception as exc:
            logger.error("Market order failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Cancel an open order."""
        if not self._secure:
            raise RuntimeError("Secure client not initialized.")

        try:
            response = await self._secure.cancel_order(order_id=order_id)
            return {"ok": True, "canceled": list(response.canceled)}
        except Exception as exc:
            logger.error("Cancel failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def list_positions(
        self,
        market_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch current positions."""
        if not self._secure:
            raise RuntimeError("Secure client not initialized.")

        positions: list[dict[str, Any]] = []
        paginator = self._secure.list_positions(
            market=market_ids,
            page_size=100,
        )
        async for page in paginator:
            for pos in page.items:
                positions.append(
                    {
                        "token_id": pos.token_id,
                        "market_id": pos.market_id,
                        "size": float(pos.size) if pos.size else 0.0,
                        "avg_price": float(pos.avg_price) if pos.avg_price else 0.0,
                        "unrealized_pnl": float(pos.unrealized_pnl) if pos.unrealized_pnl else 0.0,
                    }
                )
        return positions

    async def list_open_orders(self, token_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch open orders."""
        if not self._secure:
            raise RuntimeError("Secure client not initialized.")

        orders: list[dict[str, Any]] = []
        paginator = self._secure.list_open_orders(
            token_id=token_id,
            page_size=100,
        )
        async for page in paginator:
            for order in page.items:
                orders.append(
                    {
                        "order_id": order.id,
                        "token_id": order.token_id,
                        "side": order.side,
                        "price": float(order.price) if order.price else 0.0,
                        "size": float(order.size) if order.size else 0.0,
                        "status": order.status,
                        "created_at": str(order.created_at) if order.created_at else None,
                    }
                )
        return orders

    # ── Helpers ─────────────────────────────────────────────────

    def _market_to_dict(self, market: Any) -> dict[str, Any]:
        """Convert SDK Market model to plain dict."""
        return {
            "id": market.id,
            "condition_id": market.condition_id,
            "title": getattr(market, "title", None) or getattr(market, "question", None),
            "description": getattr(market, "description", None),
            "start_date": str(market.state.start_date)
            if market.state and market.state.start_date
            else None,
            "end_date": str(market.state.end_date)
            if market.state and market.state.end_date
            else None,
            "active": getattr(market, "active", None),
            "closed": getattr(market, "closed", None),
            "tags": [
                t.label if hasattr(t, "label") else str(t) for t in getattr(market, "tags", [])
            ],
            "outcomes": {
                "yes": {
                    "token_id": market.outcomes.yes.token_id
                    if market.outcomes and market.outcomes.yes
                    else None,
                    "price": float(market.outcomes.yes.price)
                    if market.outcomes and market.outcomes.yes and market.outcomes.yes.price
                    else None,
                    "label": getattr(market.outcomes.yes, "label", "Yes")
                    if market.outcomes and market.outcomes.yes
                    else None,
                },
                "no": {
                    "token_id": market.outcomes.no.token_id
                    if market.outcomes and market.outcomes.no
                    else None,
                    "price": float(market.outcomes.no.price)
                    if market.outcomes and market.outcomes.no and market.outcomes.no.price
                    else None,
                    "label": getattr(market.outcomes.no, "label", "No")
                    if market.outcomes and market.outcomes.no
                    else None,
                },
            },
            "volume": float(getattr(market, "volume", 0) or 0),
            "liquidity": float(getattr(market, "liquidity", 0) or 0),
        }

    def _is_weather_market(self, market_dict: dict[str, Any]) -> bool:
        """Heuristic: is this a weather market?"""
        title = (market_dict.get("title") or "").lower()
        desc = (market_dict.get("description") or "").lower()
        keywords = [
            "temperature",
            "high temp",
            "low temp",
            "rain",
            "snow",
            "weather",
            "°f",
            "celsius",
        ]
        return any(kw in title or kw in desc for kw in keywords)
