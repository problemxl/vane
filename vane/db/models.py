from __future__ import annotations

import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Float, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from vane.core.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")


def _table_args() -> dict | tuple:
    """Return SQLite-specific table args only when using SQLite."""
    if _is_sqlite:
        return {"sqlite_autoincrement": True}
    return None


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )

    # Market info
    market_id: Mapped[str] = mapped_column(String(64), index=True)
    condition_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_id: Mapped[str] = mapped_column(String(64), index=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bin_label: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Trade details
    direction: Mapped[str] = mapped_column(String(8))  # YES or NO
    side: Mapped[str] = mapped_column(String(8))  # BUY or SELL
    order_type: Mapped[str] = mapped_column(String(16))  # LIMIT, MARKET
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING"
    )  # PENDING, OPEN, FILLED, CANCELLED, FAILED
    mode: Mapped[str] = mapped_column(String(16), default="paper")  # paper or live

    # Pricing
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    filled_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    size_usd: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    filled_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    # Signal info
    edge: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    our_prob: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    market_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    # Execution
    venue_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trade_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Resolution
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_outcome: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    resolved_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = _table_args()

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    market_id: Mapped[str] = mapped_column(String(64), index=True)
    token_id: Mapped[str] = mapped_column(String(64), index=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    bin_label: Mapped[str | None] = mapped_column(String(256), nullable=True)

    direction: Mapped[str] = mapped_column(String(8))
    edge: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    our_prob: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    market_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    suggested_size_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)

    acted_on: Mapped[bool] = mapped_column(Boolean, default=False)
    trade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow
    )

    city: Mapped[str] = mapped_column(String(64), index=True)
    station_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    forecast_date: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(32))

    temperature_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed: Mapped[float | None] = mapped_column(Float, nullable=True)

    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = _table_args()
