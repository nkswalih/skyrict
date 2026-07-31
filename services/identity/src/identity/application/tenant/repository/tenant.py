"""Tenant repository — DB operations for the tenants table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.tenant.models.tenant import TenantModel
from identity.repositories.base import BaseRepository


class TenantRepository(BaseRepository[TenantModel]):
    """Repository for tenant CRUD operations."""

    model = TenantModel

    async def get_by_slug(self, slug: str) -> TenantModel | None:
        """Fetch a tenant by slug."""
        stmt = select(TenantModel).where(TenantModel.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def slug_exists(self, slug: str) -> bool:
        """Check if a tenant with this slug already exists."""
        tenant = await self.get_by_slug(slug)
        return tenant is not None
