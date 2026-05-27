from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from vane.weather.openmeteo import OpenMeteoClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("")
async def get_weather(city: str, date: str | None = None) -> dict[str, Any]:
    """Get ensemble weather forecast for a city."""
    target_date = date or (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

    client = OpenMeteoClient()
    try:
        forecast = await client.fetch_ensemble_forecast(city.lower(), target_date)
    finally:
        await client.close()

    if not forecast:
        raise HTTPException(status_code=404, detail=f"No forecast for {city} on {target_date}")

    return {
        "city": forecast["city"],
        "station": forecast["station"],
        "target_date": forecast["target_date"],
        "ensemble_mean": forecast["ensemble_mean"],
        "ensemble_std": forecast["ensemble_std"],
        "ensemble_min": forecast["ensemble_min"],
        "ensemble_max": forecast["ensemble_max"],
        "model_count": forecast["model_count"],
        "models": forecast["models"],
    }
