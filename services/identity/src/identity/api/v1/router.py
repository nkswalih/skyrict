"""V1 API router — aggregates all v1 endpoint modules."""

from __future__ import annotations

from fastapi import APIRouter

from identity.api.v1.auth.router import router as auth_router
from identity.api.v1.health import router as health_router
from identity.api.v1.mfa.router import router as mfa_router
from identity.api.v1.organizations.router import router as org_router
from identity.api.v1.passkeys.router import router as passkey_router
from identity.api.v1.sessions.router import router as session_router
from identity.api.v1.sso.router import router as sso_router
from identity.api.v1.users.router import router as user_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(org_router)
api_router.include_router(session_router)
api_router.include_router(mfa_router)
api_router.include_router(passkey_router)
api_router.include_router(sso_router)
api_router.include_router(health_router)
