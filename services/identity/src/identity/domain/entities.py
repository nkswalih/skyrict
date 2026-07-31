"""Domain entities — pure Python dataclasses, no framework dependencies.

These represent the core business objects of the identity domain.
Services operate on these, not on ORM models directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass
class User:
    """User entity."""

    id: UUID
    email: str
    hashed_password: str
    full_name: str
    is_active: bool = True
    is_verified: bool = False
    mfa_enabled: bool = False
    mfa_secret: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Tenant:
    """Tenant (organization) entity."""

    id: UUID
    name: str
    slug: str
    is_active: bool = True
    plan: str = "free"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Session:
    """User session entity."""

    id: UUID
    user_id: UUID
    tenant_id: UUID
    refresh_token_hash: str
    user_agent: str | None = None
    ip_address: str | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Role:
    """Role entity for RBAC."""

    id: UUID
    tenant_id: UUID
    name: str
    permissions: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AuditLog:
    """Audit log entry entity."""

    id: UUID
    tenant_id: UUID
    user_id: UUID | None = None
    action: str = ""
    resource_type: str = ""
    resource_id: str | None = None
    details: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
