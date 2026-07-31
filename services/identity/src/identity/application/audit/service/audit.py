"""Audit service — log all security-relevant actions."""

from __future__ import annotations

from identity.application.audit.repository.audit import AuditRepository
from identity.core.tenant_context import TenantContext


class AuditService:
    """Logs security-relevant actions for compliance and debugging."""

    def __init__(self, audit_repo: AuditRepository) -> None:
        self.audit_repo = audit_repo

    async def log(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        user_id=None,
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Create an audit log entry for the current tenant."""
        tenant_id = TenantContext.get_optional()
        if not tenant_id:
            return  # Skip audit if no tenant context (e.g., during startup)

        await self.audit_repo.log(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get_user_audit_log(self, user_id, *, offset: int = 0, limit: int = 50):
        """Retrieve audit entries for a user."""
        return await self.audit_repo.get_by_user(user_id, offset=offset, limit=limit)
