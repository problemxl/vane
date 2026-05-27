from __future__ import annotations

import datetime
import logging
import re
from dataclasses import dataclass
from typing import Any

from vane.core.config import settings
from vane.markets.polymarket_client import PolymarketClient
from vane.weather.openmeteo import OpenMeteoClient

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    city: str
    date: str
    bin_label: str
    token_id: str
    market_id: str
    direction: str  # YES or NO
    market_price: float
    our_prob: float
    edge: float
    confidence: float
    suggested_size_usd: float = 0.0
    ensemble_mean: float = 0.0
    ensemble_std: float = 0.0


class SignalGenerator:
    """Generate trading signals from weather forecasts + Polymarket prices."""

    def __init__(self) -> None:
        self._weather = OpenMeteoClient()
        self._markets = PolymarketClient()

    async def close(self) -> None:
        await self._weather.close()
        await self._markets.close()

    async def generate_signals(
        self,
        target_date: datetime.date | None = None,
    ) -> list[TradingSignal]:
        """Full scan: discover weather markets, fetch forecasts, compute edges."""
        target = target_date or (datetime.date.today() + datetime.timedelta(days=1))
        target_str = target.isoformat()

        signals: list[TradingSignal] = []

        async with self._markets, self._weather:
            # 1. Discover weather markets
            markets = await self._markets.list_weather_markets(limit=200)
            logger.info("Scanning %d markets for %s", len(markets), target_str)

            for market in markets:
                try:
                    sig = await self._evaluate_market(market, target_str)
                    if sig:
                        signals.append(sig)
                except Exception as exc:
                    logger.warning("Market evaluation failed for %s: %s", market.get("id"), exc)

        # Sort by absolute edge descending
        signals.sort(key=lambda s: -abs(s.edge))
        logger.info("Generated %d signals", len(signals))
        return signals

    async def _evaluate_market(
        self,
        market: dict[str, Any],
        target_date: str,
    ) -> TradingSignal | None:
        """Evaluate a single market for a trading signal."""
        title = market.get("title", "")
        city = self._extract_city(title)
        if not city:
            return None

        # Extract temperature bucket from title
        bucket = self._extract_temperature_bucket(title)
        if not bucket:
            return None

        # Fetch ensemble forecast
        forecast = await self._weather.fetch_ensemble_forecast(city, target_date)
        if not forecast:
            return None

        # Compute probability of being in bucket
        our_prob = await self._weather.compute_probability(
            forecast, bucket["low"], bucket["high"]
        )
        our_prob = float(our_prob)

        # Get market price
        yes_token = market.get("outcomes", {}).get("yes", {}).get("token_id")
        no_token = market.get("outcomes", {}).get("no", {}).get("token_id")
        if not yes_token:
            return None

        yes_price = market.get("outcomes", {}).get("yes", {}).get("price") or 0.0
        no_price = market.get("outcomes", {}).get("no", {}).get("price") or 0.0

        # Use mid price if available
        market_price = yes_price if yes_price else 1.0 - no_price

        # Determine direction and edge
        if our_prob > market_price + settings.min_edge_threshold:
            direction = "YES"
            edge = our_prob - market_price
        elif (1.0 - our_prob) > no_price + settings.min_edge_threshold:
            direction = "NO"
            edge = (1.0 - our_prob) - no_price
            market_price = no_price
        else:
            return None

        # Confidence based on ensemble agreement
        confidence = self._compute_confidence(forecast["ensemble_std"])

        # Size position
        suggested_size = self._size_position(edge, confidence)

        return TradingSignal(
            city=city,
            date=target_date,
            bin_label=bucket["label"],
            token_id=yes_token if direction == "YES" else no_token,
            market_id=market["id"],
            direction=direction,
            market_price=market_price,
            our_prob=our_prob if direction == "YES" else 1.0 - our_prob,
            edge=edge,
            confidence=confidence,
            suggested_size_usd=suggested_size,
            ensemble_mean=forecast["ensemble_mean"],
            ensemble_std=forecast["ensemble_std"],
        )

    def _extract_city(self, title: str) -> str | None:
        """Extract city name from market title."""
        lower = title.lower()
        from vane.weather.openmeteo import CITY_STATIONS
        for city in sorted(CITY_STATIONS.keys(), key=len, reverse=True):
            if city in lower:
                return city
        return None

    def _extract_temperature_bucket(self, title: str) -> dict[str, Any] | None:
        """Extract temperature range from market title.

        Examples:
            'Will the high temp in NYC be 65-70°F on Jan 15?'
            'Will the high temp in LA be above 75°F?'
        """
        # Pattern: number-number°F or number - number °F
        range_match = re.search(
            r"(\d+)\s*[-–]\s*(\d+)\s*[°\u00B0]?\s*[Ff]",
            title,
        )
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            return {"low": low, "high": high, "label": f"{low}-{high}°F"}

        # Pattern: above number°F
        above_match = re.search(r"above\s+(\d+)\s*[°\u00B0]?\s*[Ff]", title)
        if above_match:
            threshold = float(above_match.group(1))
            return {"low": threshold, "high": 999, "label": f">{threshold}°F"}

        # Pattern: below number°F
        below_match = re.search(r"below\s+(\d+)\s*[°\u00B0]?\s*[Ff]", title)
        if below_match:
            threshold = float(below_match.group(1))
            return {"low": -999, "high": threshold, "label": f"<{threshold}°F"}

        # Pattern: exactly number°F or just a number before °F
        exact_match = re.search(r"(\d+)\s*[°\u00B0]?\s*[Ff]", title)
        if exact_match:
            val = float(exact_match.group(1))
            return {"low": val - 0.5, "high": val + 0.5, "label": f"~{val}°F"}

        return None

    def _compute_confidence(self, ensemble_std: float) -> float:
        """Map ensemble std to confidence score (0-1)."""
        if ensemble_std < 0.5:
            return 0.9
        if ensemble_std < 1.0:
            return 0.7
        if ensemble_std < 2.0:
            return 0.5
        if ensemble_std < 3.0:
            return 0.3
        return 0.1

    def _size_position(self, edge: float, confidence: float) -> float:
        """Kelly-inspired sizing with confidence discount."""
        bankroll = settings.bankroll_usd
        base_size = bankroll * settings.kelly_fraction * edge

        # Confidence discount
        base_size *= confidence

        # Clamp
        base_size = max(base_size, settings.min_position_size_usd)
        base_size = min(base_size, settings.max_position_size_usd)
        return round(base_size, 2)
