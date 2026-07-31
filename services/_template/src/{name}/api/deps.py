"""FastAPI dependency injection — get_db, get_current_user, require_permission."""

from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from {name}.core.security import verify_jwt
from {name}.core.tenant_context import TenantContext
from {name}.db.session import async_session_factory
from skyrict_common.exceptions import AuthenticationError

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None:
        raise AuthenticationError("Missing Authorization header")

    payload = verify_jwt(credentials.credentials)
    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    tenant_id = payload.get("tenant_id")
    if tenant_id:
        TenantContext.set(tenant_id)

    return {
        "user_id": payload["sub"],
        "tenant_id": tenant_id,
        "token_payload": payload,
    }
