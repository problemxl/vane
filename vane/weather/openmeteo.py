from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from scipy import stats

from vane.core.config import settings

logger = logging.getLogger(__name__)

# ICAO station mapping for major cities on Polymarket weather markets
CITY_STATIONS: dict[str, str] = {
    "new york": "KLGA",
    "los angeles": "KLAX",
    "chicago": "KORD",
    "houston": "KIAH",
    "miami": "KMIA",
    "dallas": "KDFW",
    "seattle": "KSEA",
    "san francisco": "KSFO",
    "atlanta": "KATL",
    "boston": "KBOS",
    "denver": "KDEN",
    "phoenix": "KPHX",
    "philadelphia": "KPHL",
    "las vegas": "KLAS",
    "san diego": "KSAN",
    "austin": "KAUS",
    "nashville": "KBNA",
    "detroit": "KDTW",
    "paris": "LFPO",
    "london": "EGLL",
    "tokyo": "RJTT",
    "buenos aires": "SAEZ",
    "sao paulo": "SBGR",
    "tel aviv": "LLBG",
    "munich": "EDDM",
}


class OpenMeteoClient:
    """Multi-model ensemble forecast client."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> OpenMeteoClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def fetch_ensemble_forecast(
        self,
        city: str,
        target_date: str,
    ) -> dict[str, Any] | None:
        """Fetch ensemble forecast for a city on a target date.

        Returns dict with model predictions and ensemble stats.
        """
        station = CITY_STATIONS.get(city.lower())
        if not station:
            logger.warning("No ICAO station mapped for city: %s", city)
            return None

        # Get lat/lon for the station (simplified — in production, use a station DB)
        lat, lon = await self._station_to_latlon(station)
        if lat is None:
            return None

        model_predictions: list[float] = []
        model_raw: list[dict[str, Any]] = []

        # Fetch forecasts from each ensemble model in parallel
        tasks = [
            self._fetch_model(lat, lon, target_date, model)
            for model in settings.ensemble_models
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for model, result in zip(settings.ensemble_models, results, strict=False):
            if isinstance(result, Exception):
                logger.warning("Model %s failed for %s: %s", model, city, result)
                continue
            if result is not None:
                model_predictions.append(result)
                model_raw.append({"model": model, "temp_high": result})

        if len(model_predictions) < 3:
            logger.warning("Insufficient ensemble data for %s (got %d models)", city, len(model_predictions))
            return None

        ensemble_mean = sum(model_predictions) / len(model_predictions)
        ensemble_std = (sum((x - ensemble_mean) ** 2 for x in model_predictions) / len(model_predictions)) ** 0.5

        return {
            "city": city,
            "station": station,
            "target_date": target_date,
            "model_count": len(model_predictions),
            "models": model_raw,
            "ensemble_mean": ensemble_mean,
            "ensemble_std": ensemble_std,
            "ensemble_min": min(model_predictions),
            "ensemble_max": max(model_predictions),
        }

    async def compute_probability(
        self,
        forecast: dict[str, Any],
        low_threshold: float,
        high_threshold: float,
    ) -> float:
        """Compute P(actual_high in [low, high]) using Student-t distribution."""
        mean = forecast["ensemble_mean"]
        std = max(forecast["ensemble_std"], 0.5)  # Minimum 0.5°C uncertainty
        df = settings.forecast_t_df

        # P(low < T < high) = CDF(high) - CDF(low)
        prob = stats.t.cdf(high_threshold, df, loc=mean, scale=std) - stats.t.cdf(
            low_threshold, df, loc=mean, scale=std
        )
        return float(prob)

    async def _fetch_model(
        self,
        lat: float,
        lon: float,
        target_date: str,
        model: str,
    ) -> float | None:
        """Fetch daily temperature max from a single model."""
        url = f"{settings.openmeteo_url}/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max",
            "models": model,
            "start_date": target_date,
            "end_date": target_date,
            "timezone": "auto",
        }
        try:
            resp = await self._http.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            daily = data.get("daily", {})
            temps = daily.get("temperature_2m_max", [])
            if temps and temps[0] is not None:
                return float(temps[0])
            return None
        except Exception as exc:
            logger.debug("Model %s fetch error: %s", model, exc)
            return None

    async def _station_to_latlon(self, station: str) -> tuple[float | None, float | None]:
        """Map ICAO station to lat/lon. Use a simple cache or lookup."""
        # In production, maintain a station database or use a geocoding API
        # For now, use a hardcoded lookup for common stations
        lookup: dict[str, tuple[float, float]] = {
            "KLGA": (40.7772, -73.8726),
            "KLAX": (33.9425, -118.4081),
            "KORD": (41.9742, -87.9073),
            "KIAH": (29.9844, -95.3414),
            "KMIA": (25.7959, -80.2870),
            "KDFW": (32.8968, -97.0380),
            "KSEA": (47.4502, -122.3088),
            "KSFO": (37.6213, -122.3790),
            "KATL": (33.6407, -84.4277),
            "KBOS": (42.3656, -71.0096),
            "KDEN": (39.8561, -104.6737),
            "KPHX": (33.4343, -112.0116),
            "KPHL": (39.8744, -75.2424),
            "KLAS": (36.0840, -115.1537),
            "KSAN": (32.7336, -117.1897),
            "KAUS": (30.1945, -97.6699),
            "KBNA": (36.1263, -86.6774),
            "KDTW": (42.2124, -83.3534),
            "LFPO": (48.7233, 2.3794),
            "EGLL": (51.4700, -0.4543),
            "RJTT": (35.5494, 139.7798),
            "SAEZ": (-34.8222, -58.5358),
            "SBGR": (-23.4356, -46.4731),
            "LLBG": (32.0114, 34.8867),
            "EDDM": (48.3538, 11.7861),
        }
        return lookup.get(station, (None, None))
