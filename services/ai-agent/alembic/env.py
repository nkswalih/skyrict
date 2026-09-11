"""Alembic env.py - async migration runner for the AI agent service.

CRITICAL: the AI agent shares the ``skyrict_identity`` Postgres database with
identity and core, so it MUST migrate under its own Alembic version table
(``alembic_version_ai``). Both ``run_migrations_offline`` and
``run_migrations_online`` pass ``version_table=VERSION_TABLE`` to
``context.configure``; without this, the three services would clobber each
other's migration bookkeeping in the single database.

Ordering: identity's chain must run first in a fresh database (it creates
``tenants`` and ``public.current_tenant_id()``, both referenced here).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import TYPE_CHECKING

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

from ai_agent.core.config import settings
from ai_agent.models import (  # noqa: F401  # registers every ORM model
    AgentRegistryModel,
    AiAnomalyModel,
    AiAuditLogModel,
    AiDocumentEmbeddingModel,
    AiFinanceEvalRunModel,
    AiQueryLogModel,
    AiSuggestionModel,
)
from ai_agent.models.base import Base

config = context.config
# Escape "%" so configparser interpolation does not choke on URL-encoded
# credentials (e.g. "%40" in a password); get_main_option restores the "%".
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# The AI agent migrates the SHARED skyrict_identity database under its own
# Alembic version table so identity / core / ai-agent never clobber each
# other's bookkeeping.
VERSION_TABLE = "alembic_version_ai"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode - generate SQL without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=VERSION_TABLE,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode - connect to the database."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
