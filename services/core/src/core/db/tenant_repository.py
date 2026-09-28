"""Tenant lookup against the shared identity ``tenants`` table.

Only the middleware resolves tenants, and it delegates here. The repository
lives in the db layer (never the api layer) so api code never imports ORM
models directly. ``tenants`` has a permissive SELECT policy (``tenants_readable``,
created by identity's migration 0001) so lookup succeeds before any request
tenant context exists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from core.models.tenant import TenantModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class TenantRepository:
    """Read-only access to the shared tenants table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_slug(self, slug: str) -> TenantModel | None:
        """Return the tenant with the given slug, or None."""
        result = await self.session.execute(select(TenantModel).where(TenantModel.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_id(self, tenant_id: str | uuid.UUID) -> TenantModel | None:
        """Return the tenant with the given primary key, or None.

        Used when the tenant comes from a verified JWT ``tenant_id`` claim,
        which identifies the tenant by id rather than by slug.
        """
        return await self.session.get(TenantModel, tenant_id)
