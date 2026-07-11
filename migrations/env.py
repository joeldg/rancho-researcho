"""Async Alembic environment for the Rancho durable store."""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from rancho import db_models  # noqa: F401  (imported to populate Base.metadata)
from rancho.config import get_settings
from rancho.db import Base

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the migration URL from the environment or app settings."""
    return (
        os.environ.get("RANCHO_ALEMBIC_URL")
        or get_settings().async_database_url()
        or "sqlite+aiosqlite://"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
