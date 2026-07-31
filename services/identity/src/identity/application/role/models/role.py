"""Role and TenantRole ORM models for RBAC."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RoleModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """SQLAlchemy model for the roles table."""

    __tablename__ = "roles"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    # Relationships
    tenant = relationship("TenantModel", back_populates="roles")
    tenant_roles = relationship("TenantRoleModel", back_populates="role", lazy="selectin")


class TenantRoleModel(UUIDPrimaryKeyMixin, Base):
    """Association table: users <-> roles within a tenant."""

    __tablename__ = "tenant_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    # Relationships
    user = relationship("UserModel", back_populates="tenant_roles")
    role = relationship("RoleModel", back_populates="tenant_roles")
