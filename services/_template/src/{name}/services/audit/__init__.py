"""Audit service package — log all security-relevant actions."""

from __future__ import annotations


class AuditService:
    """Logs security-relevant actions for compliance and debugging."""

    def __init__(self, audit_repo) -> None:
        self.audit_repo = audit_repo

    async def log(self, *, action: str, resource_type: str, **kwargs) -> None:
        """Create an audit log entry for the current tenant."""
        raise NotImplementedError

    async def get_user_audit_log(self, user_id, *, offset: int = 0, limit: int = 50):
        """Retrieve audit entries for a user."""
        raise NotImplementedError
