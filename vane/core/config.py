from __future__ import annotations

import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "Vane"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/vane.db"

    # Infisical bootstrap (identity credentials — not application secrets)
    infisical_enabled: bool = False
    infisical_host: str = "https://app.infisical.com"
    infisical_client_id: str | None = None
    infisical_client_secret: str | None = None
    infisical_token: str | None = None
    infisical_project_id: str | None = None
    infisical_env: str = "dev"
    infisical_path: str = "/"

    # Polymarket
    polymarket_private_key: str | None = None
    polymarket_wallet_address: str | None = None
    polymarket_api_key: str | None = None
    polymarket_api_secret: str | None = None
    polymarket_passphrase: str | None = None
    polymarket_api_url: str = "https://clob.polymarket.com"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_data_url: str = "https://data-api.polymarket.com"

    # Trading
    trading_enabled: bool = False
    trading_mode: str = "paper"  # "paper" | "live"
    bankroll_usd: float = 1000.0
    max_position_size_usd: float = 50.0
    max_total_exposure_usd: float = 400.0
    max_daily_loss_usd: float = 100.0
    min_edge_threshold: float = 0.10
    kelly_fraction: float = 0.25
    max_trades_per_day: int = 10
    min_position_size_usd: float = 5.0

    # Weather
    openmeteo_url: str = "https://api.open-meteo.com/v1"
    noaa_asos_url: str = "https://mesonet.agron.iastate.edu/geojson"
    forecast_t_df: float = 4.0  # Student-t degrees of freedom
    ensemble_models: list[str] = [
        "gfs_seamless",
        "ecmwf_ifs04",
        "icon_seamless",
        "gem_seamless",
        "meteofrance_seamless",
    ]

    # Telegram
    telegram_bot_token: str | None = None
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_admin_chat_ids: list[int] = []

    # Scheduling
    scan_interval_minutes: int = 15
    forecast_fetch_interval_minutes: int = 60

    # Production / security
    allowed_origins: list[str] = ["*"]
    allowed_hosts: list[str] = []
    sentry_dsn: str | None = None


# ── Infisical injection (must run BEFORE Settings() reads env vars) ──
# The .env file is loaded first by pydantic-settings, then Infisical
# secrets are injected as env vars only for keys not already set.
# Local .env values and explicit shell exports take precedence.

_infisical_loaded = False


def _maybe_inject_infisical_secrets() -> None:
    """Inject Infisical secrets into os.environ before Settings reads them.

    Only runs once. Bootstrap credentials come from the .env file or
    the actual shell environment (never from Infisical itself).
    """
    global _infisical_loaded
    if _infisical_loaded:
        return
    _infisical_loaded = True

    # Check if Infisical bootstrap credentials are available
    client_id = os.environ.get("INFISICAL_CLIENT_ID")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")
    token = os.environ.get("INFISICAL_TOKEN")
    project_id = os.environ.get("INFISICAL_PROJECT_ID")

    if not project_id:
        return
    if not ((client_id and client_secret) or token):
        return

    try:
        from vane.core.secrets import inject_secrets_into_env

        count = inject_secrets_into_env()
        if count > 0:
            logger.info(
                "Infisical: injected %d secrets before Settings init",
                count,
            )
    except Exception as exc:
        logger.warning("Infisical: injection failed (falling back to env): %s", exc)


# Inject secrets before creating the singleton
_maybe_inject_infisical_secrets()

settings = Settings()
