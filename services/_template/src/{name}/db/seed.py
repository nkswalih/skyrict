"""Database seeding — bootstrap default tenants, roles, and admin users.

Usage:
    python -m {name}.db.seed
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from {name}.core.config import settings

logger = structlog.get_logger("{name}.seed")


async def seed_default_tenant() -> None:
    """Create the default tenant if it doesn't exist."""
    raise NotImplementedError("Implement after DB session setup")


async def seed_default_roles() -> None:
    """Create default RBAC roles for the default tenant."""
    raise NotImplementedError("Implement after DB session setup")


async def seed_admin_user() -> None:
    """Create a default admin user for development/staging."""
    raise NotImplementedError("Implement after DB session setup")


async def run_seed() -> None:
    """Run all seed operations."""
    logger.info("seed.start")
    await seed_default_tenant()
    await seed_default_roles()
    await seed_admin_user()
    logger.info("seed.complete")


if __name__ == "__main__":
    asyncio.run(run_seed())
