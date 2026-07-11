"""Async SQLAlchemy engine, session factory, and declarative base.

PostgreSQL is the durable system of record (RANCHO_ASYNC_RESEARCH). The engine
is built from operator configuration; it is never derived from a request.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from rancho.config import Settings, get_settings


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
class Base(DeclarativeBase):
    """Declarative base for all durable Rancho models."""


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
def create_engine(settings: Settings | None = None) -> AsyncEngine | None:
    """Build the async engine when a durable store is configured."""
    settings = settings or get_settings()
    url = settings.async_database_url()
    if not url:
        return None
    return create_async_engine(url, pool_pre_ping=True, future=True)


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Return a session factory that keeps objects usable after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


_session_factory: async_sessionmaker[AsyncSession] | None = None
_factory_built = False


# @spec[RANCHO_ASYNC_RESEARCH.md#architecture-and-storage]
def get_session_factory() -> async_sessionmaker[AsyncSession] | None:
    """Return the process-wide session factory, or None if no store is set."""
    global _session_factory, _factory_built
    if not _factory_built:
        engine = create_engine()
        _session_factory = create_session_factory(engine) if engine else None
        _factory_built = True
    return _session_factory
