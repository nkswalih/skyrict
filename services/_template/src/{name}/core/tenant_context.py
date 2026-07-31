"""ContextVar-based TenantContext — request-scoped tenant isolation.

This is the FIXED version: uses ContextVar (not threading.local), properly
cleaned up on request end, and never silently defaults to a wrong tenant.
"""

from __future__ import annotations

from contextvars import ContextVar

from fastapi import Depends, Request

from {name}.core.exceptions import TenantContextMissingError

# ContextVar for request-scoped tenant ID
_current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


class TenantContext:
    """Access and set the current tenant for the request lifecycle."""

    @staticmethod
    def set(tenant_id: str) -> None:
        """Set the current tenant ID for this request context."""
        _current_tenant_id.set(tenant_id)

    @staticmethod
    def get() -> str:
        """Get the current tenant ID. Raises if not set."""
        tid = _current_tenant_id.get()
        if tid is None:
            raise TenantContextMissingError(
                "Tenant context is not set. "
                "Ensure TenantContextMiddleware runs before route handlers."
            )
        return tid

    @staticmethod
    def get_optional() -> str | None:
        """Get the current tenant ID without raising. Use sparingly."""
        return _current_tenant_id.get()

    @staticmethod
    def reset() -> None:
        """Reset the context var — called by middleware at request end."""
        _current_tenant_id.set(None)


def get_current_tenant(request: Request) -> str:
    """FastAPI dependency that returns the current tenant ID."""
    tenant_id = TenantContext.get()
    if not tenant_id:
        raise TenantContextMissingError(
            "Tenant context is not set. "
            "Ensure TenantContextMiddleware runs before route handlers."
        )
    return tenant_id
