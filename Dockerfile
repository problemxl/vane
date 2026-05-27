# ── Builder stage ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# System deps for scipy wheel + git for polymarket-client
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install dependencies (layer caching: pyproject.toml + stub vane)
# vane/__init__.py is needed so hatchling can find the local package
COPY pyproject.toml .
RUN mkdir -p vane && touch vane/__init__.py
RUN uv sync --no-dev

# Copy application code (overwrites the stub)
COPY vane/ vane/
COPY alembic/ alembic/
COPY alembic.ini .

# ── Runner stage ─────────────────────────────────────────────────────
FROM python:3.12-slim AS runner

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash vane

WORKDIR /app

# Copy virtualenv and app from builder
COPY --from=builder --chown=vane:vane /app/.venv .venv/
COPY --from=builder --chown=vane:vane /app/vane/ vane/
COPY --from=builder --chown=vane:vane /app/alembic/ alembic/
COPY --from=builder --chown=vane:vane /app/alembic.ini .
COPY --from=builder --chown=vane:vane /app/pyproject.toml .

# Create data directory for SQLite (when not using PostgreSQL)
RUN mkdir -p /app/data && chown vane:vane /app/data

USER vane

# App starts → Infisical injection → migrations → scheduler → ready
ENTRYPOINT [".venv/bin/python", "-m", "vane"]
