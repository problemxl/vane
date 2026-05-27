# Vane — Polymarket Weather Trading Bot

A Python-based trading bot for Polymarket weather prediction markets, with Telegram integration and a FastAPI backend.

## Features

- **Weather Signal Generation**: Fetches ensemble forecasts (GFS, ECMWF, ICON, GEM, Météo-France) from Open-Meteo, computes edge against Polymarket prices, and generates trade signals.
- **Paper & Live Trading**: Simulated fills for safe testing, or real CLOB execution via the official Polymarket Python SDK.
- **Telegram Bot**: Full trading interface via Telegram — scan markets, view signals, execute trades, monitor positions and P&L.
- **FastAPI Backend**: REST API for trading, signals, positions, weather data, and market discovery.
- **Scheduled Scans**: APScheduler runs periodic market scans, forecast fetches, and daily trade evaluation.

## Architecture

```
vane/
├── core/          # Configuration
├── db/            # SQLAlchemy ORM + async SQLite
├── markets/       # Polymarket SDK wrapper
├── weather/       # Open-Meteo ensemble client
├── trading/       # Signal generation + execution engine
├── telegram/      # Telegram bot handlers
├── api/           # FastAPI app + routers
└── scheduler.py   # APScheduler manager
```

## Quick Start

### 1. Install dependencies

```bash
cd /home/mark/vane
uv sync
# or: pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys
```

#### Option A: `infisical run` CLI (recommended for dev)

Install the [Infisical CLI](https://infisical.com/docs/cli/overview), then:

```bash
infisical run --env dev -- python -m vane
```

The CLI injects secrets as environment variables before the process
starts. No `.env` file needed for secrets. Bootstrap credentials
(`INFISICAL_CLIENT_ID`, etc.) are NOT required with this approach.

#### Option B: Infisical SDK (for containers / CI)

Set `INFISICAL_ENABLED=true` and add the bootstrap environment vars:

```bash
INFISICAL_ENABLED=true \
INFISICAL_CLIENT_ID=<machine-identity-id> \
INFISICAL_CLIENT_SECRET=<machine-identity-secret> \
INFISICAL_PROJECT_ID=<project-id> \
python -m vane
```

The SDK fetches secrets at startup before `Settings` is created.
Bootstrap credentials are identity credentials (safe to set in env);
the actual secrets (private keys, tokens) live ONLY in Infisical.

#### Option C: plain `.env` (fallback)

Without Infisical, just fill in the `.env` file directly.

### 3. Run database migrations

```bash
alembic upgrade head
```

### 4. Start the API server

```bash
python -m vane
# or: uvicorn vane.api.main:app --reload
```

The server starts on `http://localhost:8000`. Visit `/docs` for interactive API docs.

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message |
| `/scan` | Run market scan |
| `/signals` | View recent signals |
| `/positions` | Open positions |
| `/pnl` | P&L summary |
| `/trades` | Trade history |
| `/markets` | Active weather markets |
| `/weather <city>` | Forecast for city |
| `/status` | Bot status |
| `/config` | Current settings |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/trading/scan` | POST | Trigger market scan |
| `/api/v1/trading/status` | GET | Trading status |
| `/api/v1/trading/execute` | POST | Execute a trade |
| `/api/v1/positions` | GET | Open positions |
| `/api/v1/positions/orders` | GET | Open orders |
| `/api/v1/signals` | GET | Recent signals |
| `/api/v1/weather?city=` | GET | Weather forecast |
| `/api/v1/markets/weather` | GET | Weather markets |

## Trading Strategy

The bot uses an **extreme value / ensemble edge** strategy:

1. **Scan**: Discover active weather markets on Polymarket via Gamma API.
2. **Forecast**: Fetch multi-model ensemble forecasts for the target city and date.
3. **Probability**: Fit a Student-t distribution to the ensemble and integrate over the market's temperature bucket.
4. **Edge**: Compare model probability to market price. If `|edge| > min_edge`, generate a signal.
5. **Size**: Kelly-inspired sizing with confidence discounting.
6. **Execute**: Place limit order via CLOB (paper or live).

## Important Notes

- **Start in paper mode**: Set `TRADING_MODE=paper` and validate signals before going live.
- **pUSD required**: For live trading, your wallet must be funded with pUSD on Polygon.
- **Set allowances**: Run `python -m vane.markets.set_allowances` before first trade (requires `POLYGON_PRIVATE_KEY`).

## License

MIT

## Production Deployment

### Docker Compose (Quick Start)

```bash
# Clone and build
cd /home/mark/vane
docker compose build

# Set Infisical bootstrap credentials (identity only)
export INFISICAL_CLIENT_ID=<machine-identity-id>
export INFISICAL_CLIENT_SECRET=<machine-identity-secret>
export INFISICAL_PROJECT_ID=<project-id>

# Start the stack (PostgreSQL + Vane)
docker compose up -d

# Check health
curl http://localhost:8000/health
```

The stack includes:

| Service | Image | Purpose |
|---------|-------|---------|
| `vane` | Built from `Dockerfile` | FastAPI app + scheduler |
| `db` | `postgres:16-alpine` | Production database |

Secrets flow: bootstrap env vars → Infisical SDK → injects app secrets (keys, tokens, DB password) into the process. No secrets in the repo, Dockerfile, or `.env`.

### systemd

```ini
# /etc/systemd/system/vane.service
[Unit]
Description=Vane Polymarket Weather Bot
After=network.target postgresql.service

[Service]
Type=simple
User=vane
WorkingDirectory=/opt/vane
ExecStart=/opt/vane/.venv/bin/python -m vane

# Bootstrap credentials — identity only
Environment="INFISICAL_ENABLED=true"
Environment="INFISICAL_CLIENT_ID=<machine-identity-id>"
Environment="INFISICAL_CLIENT_SECRET=<machine-identity-secret>"
Environment="INFISICAL_PROJECT_ID=<project-id>"
Environment="INFISICAL_ENV=production"
# DATABASE_URL — also fetched from Infisical, not set here

Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vane
sudo systemctl status vane
```

### Migrating from SQLite to PostgreSQL

1. Dump your SQLite data (optional):
   ```bash
   sqlite3 data/vane.db .dump > backup.sql
   ```

2. Start PostgreSQL and create the database:
   ```bash
   createdb -U vane vane
   ```

3. Update `DATABASE_URL`:
   ```bash
   DATABASE_URL=postgresql+asyncpg://vane:password@localhost:5432/vane
   ```

4. Run migrations:
   ```bash
   alembic upgrade head
   ```

### Environment Reference

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:///...` (local) | **Store in Infisical**. PostgreSQL for production. |
| `INFISICAL_ENABLED` | No | `false` | Set `true` to fetch secrets at startup |
| `INFISICAL_CLIENT_ID` | If SDK | — | Machine identity credential |
| `INFISICAL_CLIENT_SECRET` | If SDK | — | Machine identity credential |
| `INFISICAL_PROJECT_ID` | If SDK | — | Infisical project UUID |
| `INFISICAL_ENV` | No | `dev` | `production`, `staging`, etc. |
| `TRADING_ENABLED` | No | `false` | Only set `true` after paper validation |
| `TRADING_MODE` | No | `paper` | `paper` or `live` |
| `ALLOWED_ORIGINS` | No | `["*"]` | Comma-separated CORS origins |
| `ALLOWED_HOSTS` | No | `[]` | Host header validation |
| `SENTRY_DSN` | No | — | Error monitoring |
