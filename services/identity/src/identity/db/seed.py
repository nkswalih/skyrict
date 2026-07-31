"""Database seeding — bootstrap default tenants, roles, and admin users.

Usage:
    python -m identity.db.seed
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from identity.core.config import settings
from identity.core.security import hash_password
from identity.db.session import async_session_factory
from identity.models.role import RoleModel
from identity.models.tenant import TenantModel
from identity.models.user import UserModel

logger = structlog.get_logger("identity.seed")

DEFAULT_ROLES = [
    {"name": "owner", "permissions": ["*"]},
    {"name": "admin", "permissions": ["users:read", "users:write", "settings:read", "settings:write"]},
    {"name": "member", "permissions": ["users:read"]},
    {"name": "viewer", "permissions": ["users:read"]},
]


async def seed_default_tenant() -> None:
    """Create the default tenant if it doesn't exist."""
    from identity.repositories.tenant_repository import TenantRepository

    async with async_session_factory() as session:
        repo = TenantRepository(session)
        existing = await repo.get_by_slug("default")
        if existing:
            logger.info("seed.tenant.exists", slug="default")
            return

        tenant = TenantModel(
            id=uuid.UUID(settings.DEFAULT_TENANT_ID),
            name="Default Organization",
            slug="default",
            is_active=True,
            plan="free",
        )
        await repo.create(tenant)
        await repo.commit()
        logger.info("seed.tenant.created", slug="default", id=str(tenant.id))


async def seed_default_roles() -> None:
    """Create default RBAC roles for the default tenant."""
    from identity.repositories.base import BaseRepository

    async with async_session_factory() as session:
        repo = BaseRepository[RoleModel](session)
        repo.model = RoleModel

        existing = await repo.list(
            filters=[RoleModel.tenant_id == uuid.UUID(settings.DEFAULT_TENANT_ID)]
        )
        if existing:
            logger.info("seed.roles.exists", count=len(existing))
            return

        for role_data in DEFAULT_ROLES:
            role = RoleModel(
                tenant_id=uuid.UUID(settings.DEFAULT_TENANT_ID),
                name=role_data["name"],
                permissions=role_data["permissions"],
            )
            await repo.create(role)

        await repo.commit()
        logger.info("seed.roles.created", count=len(DEFAULT_ROLES))


async def seed_admin_user() -> None:
    """Create a default admin user for development/staging."""
    from identity.repositories.user_repository import UserRepository

    async with async_session_factory() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email("admin@skyrict.io")
        if existing:
            logger.info("seed.admin.exists")
            return

        user = UserModel(
            email="admin@skyrict.io",
            hashed_password=hash_password("Admin123!"),
            full_name="System Admin",
            is_active=True,
            is_verified=True,
        )
        await repo.create(user)
        await repo.commit()
        logger.info("seed.admin.created", email="admin@skyrict.io")


async def run_seed() -> None:
    """Run all seed operations."""
    logger.info("seed.start")
    await seed_default_tenant()
    await seed_default_roles()
    await seed_admin_user()
    logger.info("seed.complete")


if __name__ == "__main__":
    asyncio.run(run_seed())
