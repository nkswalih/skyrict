"""Tenant schemas — re-exports for backward-compatible imports."""

from {name}.schemas.tenant.requests import TenantCreateRequest, TenantUpdateRequest
from {name}.schemas.tenant.responses import TenantResponse

__all__ = [
    "TenantCreateRequest",
    "TenantResponse",
    "TenantUpdateRequest",
]
