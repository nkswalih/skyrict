"""Tenant (Organization) ORM model."""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """SQLAlchemy model for the tenants table."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)

    # Relationships
    roles = relationship("RoleModel", back_populates="tenant", lazy="selectin")
