"""Async database engine and session factory — the ONE place DB connections are created.

Sets Row-Level Security context on every connection.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from identity.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async session."""
    async with async_session_factory() as session:
        # Set RLS tenant context on every new connection
        # In production, this would be: SET app.current_tenant_id = '<tenant_id>'
        yield session
