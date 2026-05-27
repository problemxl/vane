from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vane.core.config import settings

is_sqlite = settings.database_url.startswith("sqlite")

_engine_kwargs: dict[str, object] = {"echo": settings.debug}

if is_sqlite:
    # SQLite: single connection (no pool)
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: connection pool
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_async_engine(
    settings.database_url,
    **_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
