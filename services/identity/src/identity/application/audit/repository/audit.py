"""Audit repository — DB operations for the audit_logs table."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from identity.application.audit.models.audit_log import AuditLogModel
from identity.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditLogModel]):
    """Repository for audit log operations."""

    model = AuditLogModel

    async def log(
        self,
        *,
        tenant_id,
        user_id=None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLogModel:
        """Create an audit log entry."""
        entry = AuditLogModel(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return await self.create(entry)

    async def get_by_user(
        self, user_id, *, offset: int = 0, limit: int = 50
    ) -> list[AuditLogModel]:
        """Get audit entries for a specific user."""
        stmt = (
            select(AuditLogModel)
            .where(AuditLogModel.user_id == user_id)
            .order_by(AuditLogModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
