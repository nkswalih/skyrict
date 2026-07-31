"""FastAPI dependency injection — get_db, get_current_user, require_permission.

Every route that touches the database or requires auth goes through these deps.
"""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from identity.core.security import verify_jwt
from identity.core.tenant_context import TenantContext
from identity.application.audit.repository.audit import AuditRepository
from identity.application.audit.service.audit import AuditService
from identity.application.auth.repository.user import UserRepository
from identity.application.auth.service.authentication import AuthenticationService
from identity.application.auth.service.token import TokenService
from identity.application.mfa.service.mfa import MFAService
from identity.application.passkey.service.passkey import PasskeyService
from identity.application.permissions.service.authorization import AuthorizationService
from identity.application.session.repository.session import SessionRepository
from identity.application.session.service.session import SessionService
from identity.application.sso.service.sso import SSOService
from identity.application.tenant.repository.tenant import TenantRepository
from skyrict_common.exceptions import AuthenticationError
from identity.db.session import async_session_factory

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, auto-closed after request."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Extract and verify JWT from Authorization header, return user claims.

    Uses security.verify_jwt() — the ONE AND ONLY decode path.
    Raises:
        AuthenticationError: If no token, token is invalid, or token is expired.
    """
    if credentials is None:
        raise AuthenticationError("Missing Authorization header")

    payload = verify_jwt(credentials.credentials)

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    # Ensure tenant context is set from the token
    tenant_id = payload.get("tenant_id")
    if tenant_id:
        TenantContext.set(tenant_id)

    return {
        "user_id": payload["sub"],
        "tenant_id": tenant_id,
        "token_payload": payload,
    }


def require_permission(permission: str):
    """Dependency factory — returns a dependency that checks a specific permission."""

    async def _check(
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict:
        authz = AuthorizationService(UserRepository(db))
        await authz.require_permission(
            user_id=current_user["user_id"],
            permission=permission,
            tenant_id=current_user["tenant_id"],
        )
        return current_user

    return _check


# --- Repository/Service deps ---

def get_user_repo(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_tenant_repo(db: AsyncSession = Depends(get_db)) -> TenantRepository:
    return TenantRepository(db)


def get_session_repo(db: AsyncSession = Depends(get_db)) -> SessionRepository:
    return SessionRepository(db)


def get_audit_repo(db: AsyncSession = Depends(get_db)) -> AuditRepository:
    return AuditRepository(db)


def get_token_service(session_repo: SessionRepository = Depends(get_session_repo)) -> TokenService:
    return TokenService(session_repo)


def get_audit_service(audit_repo: AuditRepository = Depends(get_audit_repo)) -> AuditService:
    return AuditService(audit_repo)


def get_authn_service(
    user_repo: UserRepository = Depends(get_user_repo),
    tenant_repo: TenantRepository = Depends(get_tenant_repo),
    token_service: TokenService = Depends(get_token_service),
    audit_service: AuditService = Depends(get_audit_service),
) -> AuthenticationService:
    return AuthenticationService(user_repo, tenant_repo, token_service, audit_service)


def get_mfa_service(user_repo: UserRepository = Depends(get_user_repo)) -> MFAService:
    return MFAService(user_repo)


def get_session_service(session_repo: SessionRepository = Depends(get_session_repo)) -> SessionService:
    return SessionService(session_repo)


def get_passkey_service(user_repo: UserRepository = Depends(get_user_repo)) -> PasskeyService:
    return PasskeyService(user_repo)


def get_sso_service(user_repo: UserRepository = Depends(get_user_repo)) -> SSOService:
    return SSOService(user_repo)
