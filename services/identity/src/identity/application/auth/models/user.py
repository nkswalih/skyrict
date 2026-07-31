"""User ORM model."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from identity.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """SQLAlchemy model for the users table."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128), nullable=False)
    full_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Relationships
    sessions = relationship("SessionModel", back_populates="user", lazy="selectin")
    tenant_roles = relationship("TenantRoleModel", back_populates="user", lazy="selectin")
