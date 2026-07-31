"""Authentication service — login, register, password verification."""

from __future__ import annotations

import uuid

from identity.core.security import hash_password, verify_password
from identity.domain.entities import User
from identity.application.tenant.repository.tenant import TenantRepository
from identity.application.auth.repository.user import UserRepository
from identity.application.auth.schemas import LoginRequest, RegisterRequest
from identity.application.audit.service.audit import AuditService
from identity.application.auth.service.token import TokenService
from skyrict_common.exceptions import (
    InvalidPasswordError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
)


class AuthenticationService:
    """Handles user authentication — login, register, password verification."""

    def __init__(
        self,
        user_repo: UserRepository,
        tenant_repo: TenantRepository,
        token_service: TokenService,
        audit_service: AuditService,
    ) -> None:
        self.user_repo = user_repo
        self.tenant_repo = tenant_repo
        self.token_service = token_service
        self.audit_service = audit_service

    async def login(
        self, request: LoginRequest, *, ip_address: str | None = None, user_agent: str | None = None
    ) -> dict:
        """Authenticate a user and return token pair.

        Raises:
            UserNotFoundError: If no user with this email exists.
            InvalidPasswordError: If the password is wrong.
            UserDisabledError: If the user account is disabled.
        """
        user = await self.user_repo.get_by_email(request.email)
        if not user:
            raise UserNotFoundError()

        if not user.is_active:
            raise UserDisabledError()

        if not verify_password(request.password, user.hashed_password):
            raise InvalidPasswordError()

        # Resolve tenant
        tenant_id = user.id  # Default — in production, resolve from tenant_slug

        tokens = await self.token_service.create_token_pair(
            user_id=str(user.id),
            tenant_id=str(tenant_id),
        )

        await self.audit_service.log(
            action="auth.login.success",
            resource_type="user",
            resource_id=str(user.id),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
            "user": user,
        }

    async def register(
        self, request: RegisterRequest, *, ip_address: str | None = None, user_agent: str | None = None
    ) -> dict:
        """Register a new user.

        Raises:
            UserAlreadyExistsError: If the email is already taken.
        """
        if await self.user_repo.email_exists(request.email):
            raise UserAlreadyExistsError()

        hashed = hash_password(request.password)

        user_model = await self.user_repo.create(
            __import__("identity.application.auth.models.user", fromlist=["UserModel"]).UserModel(
                email=request.email,
                hashed_password=hashed,
                full_name=request.full_name,
                is_active=True,
                is_verified=False,
            )
        )

        tokens = await self.token_service.create_token_pair(
            user_id=str(user_model.id),
            tenant_id=str(user_model.id),
        )

        await self.audit_service.log(
            action="auth.register.success",
            resource_type="user",
            resource_id=str(user_model.id),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": tokens.expires_in,
            "user": user_model,
        }
