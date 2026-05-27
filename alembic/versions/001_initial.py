from __future__ import annotations

"""Initial migration: create trades, signals, and weather_forecasts tables."""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("market_id", sa.String(length=64), nullable=False),
        sa.Column("condition_id", sa.String(length=64), nullable=True),
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("event_date", sa.String(length=32), nullable=True),
        sa.Column("bin_label", sa.String(length=256), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("filled_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("size_usd", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("filled_size", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("edge", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("our_prob", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("market_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("venue_order_id", sa.String(length=128), nullable=True),
        sa.Column("trade_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("resolved", sa.Boolean(), nullable=False),
        sa.Column("resolution_outcome", sa.String(length=8), nullable=True),
        sa.Column("pnl_usd", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_trades_market_id", "trades", ["market_id"], unique=False)
    op.create_index("ix_trades_token_id", "trades", ["token_id"], unique=False)

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("market_id", sa.String(length=64), nullable=False),
        sa.Column("token_id", sa.String(length=64), nullable=False),
        sa.Column("city", sa.String(length=64), nullable=True),
        sa.Column("event_date", sa.String(length=32), nullable=True),
        sa.Column("bin_label", sa.String(length=256), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("edge", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("our_prob", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("market_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("suggested_size_usd", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("acted_on", sa.Boolean(), nullable=False),
        sa.Column("trade_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_signals_market_id", "signals", ["market_id"], unique=False)
    op.create_index("ix_signals_token_id", "signals", ["token_id"], unique=False)

    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("city", sa.String(length=64), nullable=False),
        sa.Column("station_id", sa.String(length=32), nullable=True),
        sa.Column("forecast_date", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=32), nullable=False),
        sa.Column("temperature_high", sa.Float(), nullable=True),
        sa.Column("temperature_low", sa.Float(), nullable=True),
        sa.Column("temperature_mean", sa.Float(), nullable=True),
        sa.Column("precipitation", sa.Float(), nullable=True),
        sa.Column("wind_speed", sa.Float(), nullable=True),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_weather_forecasts_city", "weather_forecasts", ["city"], unique=False)
    op.create_index("ix_weather_forecasts_forecast_date", "weather_forecasts", ["forecast_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_weather_forecasts_forecast_date", table_name="weather_forecasts")
    op.drop_index("ix_weather_forecasts_city", table_name="weather_forecasts")
    op.drop_table("weather_forecasts")
    op.drop_index("ix_signals_token_id", table_name="signals")
    op.drop_index("ix_signals_market_id", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_trades_token_id", table_name="trades")
    op.drop_index("ix_trades_market_id", table_name="trades")
    op.drop_table("trades")
