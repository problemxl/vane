from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from vane.core.config import settings
from vane.db.engine import AsyncSessionLocal
from vane.db.models import Signal, Trade
from vane.markets.polymarket_client import PolymarketClient
from vane.trading.executor import TradeExecutor
from vane.trading.signals import SignalGenerator

logger = logging.getLogger(__name__)

# Conversation states
CONFIRM_TRADE = 1


class TelegramBot:
    """Telegram bot for Vane weather trading bot."""

    def __init__(self) -> None:
        self._app: Application | None = None

    async def initialize(self) -> Application:
        """Build and return the Telegram application."""
        if not settings.telegram_bot_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN not set")

        self._app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .build()
        )

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("scan", self._cmd_scan))
        self._app.add_handler(CommandHandler("signals", self._cmd_signals))
        self._app.add_handler(CommandHandler("positions", self._cmd_positions))
        self._app.add_handler(CommandHandler("pnl", self._cmd_pnl))
        self._app.add_handler(CommandHandler("trades", self._cmd_trades))
        self._app.add_handler(CommandHandler("weather", self._cmd_weather))
        self._app.add_handler(CommandHandler("markets", self._cmd_markets))
        self._app.add_handler(CommandHandler("config", self._cmd_config))

        # Callbacks
        self._app.add_handler(CallbackQueryHandler(self._cb_trade, pattern="^trade:"))
        self._app.add_handler(CallbackQueryHandler(self._cb_cancel, pattern="^cancel:"))
        self._app.add_handler(CallbackQueryHandler(self._cb_refresh, pattern="^refresh$"))

        return self._app

    # ── Command Handlers ────────────────────────────────────────

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "🌦 *Vane Weather Bot*\n\n"
            "Commands:\n"
            "/scan — Run market scan\n"
            "/signals — View latest signals\n"
            "/positions — Open positions\n"
            "/pnl — P&L summary\n"
            "/trades — Trade history\n"
            "/markets — Active weather markets\n"
            "/weather <city> — Forecast for city\n"
            "/status — Bot status\n"
            "/config — Current settings\n"
            "/help — This message",
            parse_mode="Markdown",
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._cmd_start(update, context)

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        status_text = (
            f"🤖 *Vane Status*\n\n"
            f"Mode: `{settings.trading_mode}`\n"
            f"Trading enabled: `{settings.trading_enabled}`\n"
            f"Bankroll: `${settings.bankroll_usd:.2f}`\n"
            f"Min edge: `{settings.min_edge_threshold:.0%}`\n"
            f"Max position: `${settings.max_position_size_usd:.2f}`\n"
            f"Max daily loss: `${settings.max_daily_loss_usd:.2f}`\n"
            f"Scan interval: `{settings.scan_interval_minutes} min`\n"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")

    async def _cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("🔍 Scanning markets...")

        try:
            generator = SignalGenerator()
            signals = await generator.generate_signals()
            await generator.close()

            if not signals:
                await update.message.reply_text("No signals found.")
                return

            text = f"📊 *Found {len(signals)} signals*\n\n"
            for i, sig in enumerate(signals[:5], 1):
                text += (
                    f"{i}. *{sig.city.title()}* {sig.bin_label}\n"
                    f"   Direction: `{sig.direction}`\n"
                    f"   Edge: `{sig.edge:.1%}`\n"
                    f"   Market: `{sig.market_price:.2f}` | Model: `{sig.our_prob:.2f}`\n"
                    f"   Size: `${sig.suggested_size_usd:.2f}`\n\n"
                )

            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh")],
            ]
            if signals:
                keyboard.append([
                    InlineKeyboardButton(
                        f"Trade {signals[0].city.title()}",
                        callback_data=f"trade:{signals[0].market_id}:{signals[0].token_id}:{signals[0].direction}",
                    )
                ])

            await update.message.reply_text(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
        except Exception as exc:
            logger.exception("Scan failed")
            await update.message.reply_text(f"❌ Scan failed: {exc}")

    async def _cmd_signals(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import desc, select
            result = await session.execute(
                select(Signal).order_by(desc(Signal.created_at)).limit(10)
            )
            signals = result.scalars().all()

            if not signals:
                await update.message.reply_text("No signals in database.")
                return

            text = "📡 *Recent Signals*\n\n"
            for sig in signals:
                status = "✅" if sig.acted_on else "⏳"
                text += (
                    f"{status} *{sig.city}* {sig.bin_label or ''}\n"
                    f"   `{sig.direction}` Edge: `{float(sig.edge):.1%}`\n"
                    f"   Size: `${float(sig.suggested_size_usd or 0):.2f}`\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            executor = TradeExecutor()
            positions = await executor.get_positions()
            await executor.close()

            if not positions:
                await update.message.reply_text("No open positions.")
                return

            text = "📂 *Open Positions*\n\n"
            for pos in positions:
                text += (
                    f"• Token: `{pos['token_id'][:16]}...`\n"
                    f"  Size: `{pos['size']:.2f}` @ `{pos['avg_price']:.4f}`\n"
                    f"  Unrealized: `${pos['unrealized_pnl']:.2f}`\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception as exc:
            logger.exception("Positions fetch failed")
            await update.message.reply_text(f"❌ Failed: {exc}")

    async def _cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import func, select

            from vane.db.models import Trade

            result = await session.execute(
                select(
                    func.count(Trade.id).label("total"),
                    func.sum(Trade.pnl_usd).label("pnl"),
                ).where(Trade.resolved == True)  # noqa: E712
            )
            row = result.one()

            text = (
                f"💰 *P&L Summary*\n\n"
                f"Resolved trades: `{row.total or 0}`\n"
                f"Total P&L: `${float(row.pnl or 0):.2f}`\n"
            )
            await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with AsyncSessionLocal() as session:
            from sqlalchemy import desc, select
            result = await session.execute(
                select(Trade).order_by(desc(Trade.created_at)).limit(10)
            )
            trades = result.scalars().all()

            if not trades:
                await update.message.reply_text("No trades yet.")
                return

            text = "📝 *Recent Trades*\n\n"
            for t in trades:
                status_emoji = "✅" if t.status == "FILLED" else "❌" if t.status == "FAILED" else "⏳"
                text += (
                    f"{status_emoji} *{t.city}* {t.bin_label or ''}\n"
                    f"   `{t.direction}` @ `{float(t.filled_price or t.entry_price or 0):.4f}`\n"
                    f"   Size: `${float(t.size_usd):.2f}` | Mode: `{t.mode}`\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")

    async def _cmd_weather(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = context.args
        if not args:
            await update.message.reply_text("Usage: /weather <city>")
            return

        city = " ".join(args).lower()
        from datetime import date, timedelta

        from vane.weather.openmeteo import OpenMeteoClient

        target = date.today() + timedelta(days=1)
        client = OpenMeteoClient()
        try:
            forecast = await client.fetch_ensemble_forecast(city, target.isoformat())
            if not forecast:
                await update.message.reply_text(f"No forecast for {city}.")
                return

            text = (
                f"🌤 *Weather Forecast: {city.title()}*\n"
                f"Date: `{target.isoformat()}`\n\n"
                f"Ensemble mean: `{forecast['ensemble_mean']:.1f}°F`\n"
                f"Ensemble std: `{forecast['ensemble_std']:.1f}°F`\n"
                f"Range: `{forecast['ensemble_min']:.1f}` - `{forecast['ensemble_max']:.1f}°F`\n"
                f"Models: `{forecast['model_count']}`\n"
            )
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception as exc:
            logger.exception("Weather fetch failed")
            await update.message.reply_text(f"❌ Failed: {exc}")
        finally:
            await client.close()

    async def _cmd_markets(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("📈 Fetching weather markets...")
        try:
            client = PolymarketClient()
            async with client:
                markets = await client.list_weather_markets(limit=20)

            if not markets:
                await update.message.reply_text("No weather markets found.")
                return

            text = "📈 *Weather Markets*\n\n"
            for m in markets[:10]:
                yes_price = m.get("outcomes", {}).get("yes", {}).get("price")
                text += (
                    f"• {m.get('title', 'Unknown')[:60]}...\n"
                    f"  YES: `{yes_price:.4f if yes_price else 'N/A'}`\n\n"
                )
            await update.message.reply_text(text, parse_mode="Markdown")
        except Exception as exc:
            logger.exception("Markets fetch failed")
            await update.message.reply_text(f"❌ Failed: {exc}")

    async def _cmd_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        text = (
            f"⚙️ *Configuration*\n\n"
            f"Trading mode: `{settings.trading_mode}`\n"
            f"Trading enabled: `{settings.trading_enabled}`\n"
            f"Bankroll: `${settings.bankroll_usd:.2f}`\n"
            f"Kelly fraction: `{settings.kelly_fraction:.0%}`\n"
            f"Min edge: `{settings.min_edge_threshold:.0%}`\n"
            f"Max position: `${settings.max_position_size_usd:.2f}`\n"
            f"Max exposure: `${settings.max_total_exposure_usd:.2f}`\n"
            f"Max daily loss: `${settings.max_daily_loss_usd:.2f}`\n"
            f"Max trades/day: `{settings.max_trades_per_day}`\n"
            f"Scan interval: `{settings.scan_interval_minutes} min`\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    # ── Callback Handlers ───────────────────────────────────────

    async def _cb_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()

        data = query.data  # format: trade:market_id:token_id:direction
        _, market_id, token_id, direction = data.split(":")

        await query.edit_message_text("⏳ Executing trade...")

        try:
            # Re-fetch the signal to get full details
            generator = SignalGenerator()
            signals = await generator.generate_signals()
            await generator.close()

            signal = next(
                (s for s in signals if s.market_id == market_id and s.direction == direction),
                None,
            )
            if not signal:
                await query.edit_message_text("❌ Signal no longer valid.")
                return

            executor = TradeExecutor()
            result = await executor.execute_signal(signal)
            await executor.close()

            if result.success:
                await query.edit_message_text(
                    f"✅ *Trade Executed*\n\n"
                    f"{signal.direction} {signal.city.title()} {signal.bin_label}\n"
                    f"Price: `{result.filled_price:.4f}`\n"
                    f"Size: `${result.filled_size:.2f}`\n"
                    f"ID: `{result.trade_id}`",
                    parse_mode="Markdown",
                )
            else:
                await query.edit_message_text(f"❌ Trade failed: {result.error}")
        except Exception as exc:
            logger.exception("Trade callback failed")
            await query.edit_message_text(f"❌ Error: {exc}")

    async def _cb_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Cancelled.")

    async def _cb_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        # Re-run scan by simulating the command
        fake_update = Update(update.update_id, message=query.message)
        await self._cmd_scan(fake_update, context)
