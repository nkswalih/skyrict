"""User repository - DB operations for the users table.

All SQLAlchemy stays in this file. Repositories are the only layer allowed to
touch ORM models; service-facing methods accept and return domain entities
(``identity.domain.entities.User``). All queries are tenant-scoped: when no
tenant_id is passed the current request tenant is used (see TenantContext) and
RLS additionally enforces it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from identity.core.tenant_context import TenantContext
from identity.db.repository import SqlRepository
from identity.domain.entities import User
from identity.models.user import UserModel
from skyrict_common.exceptions import UserAlreadyExistsError, UserNotFoundError


def _to_orm(user: User) -> UserModel:
    """Map a domain entity to a new ORM model (id is DB-generated unless set)."""
    model_kwargs: dict[str, Any] = {
        "tenant_id": user.tenant_id,
        "email": user.email,
        "password_hash": user.password_hash,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "mfa_enabled": user.mfa_enabled,
        "mfa_secret": user.mfa_secret,
        "phone_country": user.phone_country,
        "phone_number": user.phone_number,
        "avatar_url": user.avatar_url,
        "mfa_backup_codes": user.mfa_backup_codes or None,
        "onboarding_dismissed_at": user.onboarding_dismissed_at,
    }
    if user.id is not None:
        model_kwargs["id"] = user.id
    return UserModel(**model_kwargs)


def _from_orm(model: UserModel) -> User:
    """Map an ORM model to a domain entity."""
    return User(
        id=model.id,
        tenant_id=model.tenant_id,
        email=model.email,
        password_hash=model.password_hash,
        full_name=model.full_name,
        is_active=model.is_active,
        is_verified=model.is_verified,
        mfa_enabled=model.mfa_enabled,
        mfa_secret=model.mfa_secret,
        phone_country=model.phone_country,
        phone_number=model.phone_number,
        avatar_url=model.avatar_url,
        mfa_backup_codes=list(model.mfa_backup_codes) if model.mfa_backup_codes else [],
        onboarding_dismissed_at=model.onboarding_dismissed_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class UserRepository(SqlRepository):
    """Repository for user persistence (implements ``UserRepositoryPort``)."""

    async def get_by_id(self, user_id: str | uuid.UUID) -> User | None:
        """Fetch a user by primary key within the current tenant, or None when absent.

        The tenant is taken from TenantContext so a raw primary-key lookup can
        never cross tenant boundaries (RLS is not guaranteed to be active).
        """
        stmt = select(UserModel).where(
            UserModel.id == user_id,
            UserModel.tenant_id == TenantContext.get(),
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _from_orm(model) if model is not None else None

    async def get_by_email(self, tenant_id: str | uuid.UUID, email: str) -> User | None:
        """Fetch a user by email within a tenant."""
        stmt = select(UserModel).where(
            UserModel.tenant_id == tenant_id,
            UserModel.email == email,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _from_orm(model) if model is not None else None

    async def get_by_full_name(
        self,
        tenant_id: str | uuid.UUID,
        full_name: str,
        *,
        exclude_email: str | None = None,
    ) -> User | None:
        """Fetch the tenant user with this exact full_name, optionally excluding one email.

        Used by the demo-tenant seeder so pre-rebrand roster accounts (same
        person, old email domain) converge in place instead of duplicating.
        """
        stmt = select(UserModel).where(
            UserModel.tenant_id == tenant_id,
            UserModel.full_name == full_name,
        )
        if exclude_email is not None:
            stmt = stmt.where(UserModel.email != exclude_email)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _from_orm(model) if model is not None else None

    async def email_exists(self, tenant_id: str | uuid.UUID, email: str) -> bool:
        """Check if a user with this email already exists within a tenant."""
        user = await self.get_by_email(tenant_id, email)
        return user is not None

    async def email_exists_global(self, email: str) -> bool:
        stmt = select(UserModel.id).where(UserModel.email == email).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(self, user: User) -> User:
        """Persist a new user and return it with its DB-generated id.

        A duplicate email is a domain conflict, not a server fault: the global
        ``uq_users_email`` index (or, for two concurrent accepts in one tenant,
        ``uq_users_tenant_email``) raises an ``IntegrityError`` that the HTTP
        layer would otherwise report as a 500. Translate it to the domain error
        so every caller - signup, invite creation, invite acceptance - returns
        a 409 with a message instead.
        """
        model = _to_orm(user)
        self.session.add(model)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            if "uq_users_email" in str(exc) or "uq_users_tenant_email" in str(exc):
                raise UserAlreadyExistsError("A user with this email already exists") from exc
            raise
        await self.session.refresh(model)
        return _from_orm(model)

    async def update_profile(
        self,
        user_id: str | uuid.UUID,
        *,
        full_name: str | None = None,
        email: str | None = None,
    ) -> User:
        """Apply profile field updates and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        if full_name is not None:
            model.full_name = full_name
        if email is not None:
            model.email = email
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def update_password_hash(self, user_id: str | uuid.UUID, password_hash: str) -> User:
        """Store a new password hash and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        model.password_hash = password_hash
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def update_mfa(
        self,
        user_id: str | uuid.UUID,
        *,
        mfa_enabled: bool | None = None,
        mfa_secret: str | None = None,
        mfa_backup_codes: list[str | None] | None = None,
    ) -> User:
        """Apply the provided MFA field updates; ``None`` leaves a field unchanged."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        if mfa_enabled is not None:
            model.mfa_enabled = mfa_enabled
        if mfa_secret is not None:
            model.mfa_secret = mfa_secret
        if mfa_backup_codes is not None:
            model.mfa_backup_codes = mfa_backup_codes
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def disable_mfa(self, user_id: str | uuid.UUID) -> User:
        """Clear every MFA field (secret, backup codes, enabled flag) and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        model.mfa_enabled = False
        model.mfa_secret = None
        model.mfa_backup_codes = None
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def update_avatar(self, user_id: str | uuid.UUID, avatar_url: str | None) -> User:
        """Store (or clear, when ``None``) the avatar_url and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        model.avatar_url = avatar_url
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def mark_verified(self, user_id: str | uuid.UUID) -> User:
        """Mark the user's email as verified (idempotent) and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        model.is_verified = True
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def dismiss_onboarding(self, user_id: str | uuid.UUID) -> User:
        """Stamp onboarding_dismissed_at (idempotent) and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        if model.onboarding_dismissed_at is None:
            model.onboarding_dismissed_at = datetime.now(UTC)
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def set_active(self, user_id: str | uuid.UUID, *, is_active: bool) -> User:
        """Set the account's active flag (soft removal) and flush."""
        model = await self.session.get(UserModel, user_id)
        if model is None:
            raise UserNotFoundError("User not found")
        model.is_active = is_active
        await self.session.flush()
        await self.session.refresh(model)
        return _from_orm(model)

    async def list_active(
        self,
        *,
        tenant_id: str | uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[User]:
        """List all active users for a tenant."""
        tid: str | uuid.UUID = tenant_id or TenantContext.get()
        stmt = (
            select(UserModel)
            .where(
                UserModel.is_active == True,  # noqa: E712
                UserModel.tenant_id == tid,
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [_from_orm(model) for model in result.scalars().all()]
