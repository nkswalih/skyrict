"""Middleware stack - request-id and tenant context.

TenantContextMiddleware is the SINGLE source of truth for tenant resolution:
it derives the tenant slug via the centralized ``TenantResolver`` (core/core),
verifies the tenant in the shared database, cross-checks the verified JWT
against it, and populates TenantContext. Downstream code consumes TenantContext
instead of re-reading headers or parsing the Host again.

Exceptions raised here are converted to RFC 7807 problem+json responses via
skyrict_error_handler - exceptions thrown inside Starlette middleware do NOT
reach the route-level ExceptionMiddleware handlers.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from core.core.constants import SKIP_AUTH_PATHS
from core.core.exceptions import (
    SkyrictError,
    TenantContextMissingError,
    TenantDisabledError,
    TenantMismatchError,
    TenantNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    skyrict_error_handler,
)
from core.core.security import TokenClaims, cross_check_routing_hint, verify_jwt
from core.core.tenant_context import TenantContext
from core.core.tenant_resolver import derive_tenant_slug
from core.db.session import async_session_factory
from core.db.tenant_repository import TenantRepository

logger = structlog.get_logger("core.middleware")


def is_tenant_required_path(path: str) -> bool:
    """True when the path needs tenant resolution (everything except skip paths).

    Health/readiness/docs are exempt; every business route requires a resolved
    tenant so the context exists before handlers run.
    """
    return path not in SKIP_AUTH_PATHS


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to every request/response for tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Resolve the tenant, verify it, and populate TenantContext.

    Flow (single source of truth - no other layer re-resolves the tenant):
      1. Skip health/ready/docs (no tenant context needed).
      2. Read the routing HINT: the per-tenant Host label, else X-Tenant-Slug.
         The hint records which tenant the caller is ADDRESSING. It is absent on
         the shared API host, where the Host names no tenant.
      3. Verify the bearer token, if one was sent, via verify_jwt() - the ONE
         AND ONLY decode path.
      4. Resolve the tenant:
           - token verified  -> the SIGNED ``tenant_id`` claim is the authority.
             Unknown -> TenantNotFoundError, disabled -> TenantDisabledError.
             When a hint is also present it must agree with the token's tenant;
             disagreement -> TenantMismatchError (401), so a forged hint can
             never redirect a valid credential at another tenant.
           - no valid token  -> the hint is required (TenantContextMissingError)
             and selects the tenant. Nothing is readable on this path: handlers
             still require a verified token via get_current_user.
      5. Populate TenantContext (tenant_id, slug, user_id) and bind structlog vars.
      6. After the response, clear the context and structlog vars so no tenant
         leaks into the next request.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not is_tenant_required_path(request.url.path):
            return await call_next(request)

        try:
            return await self._resolve_and_call(request, call_next)
        except SkyrictError as exc:
            # Middleware exceptions bypass ExceptionMiddleware; produce the
            # same RFC 7807 response the handlers would.
            return await skyrict_error_handler(request, exc)

    async def _resolve_and_call(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # --- 2. Routing hint: the tenant the caller is addressing ---
        hint = derive_tenant_slug(request)

        # --- 3. Verify the bearer token, if one was sent ---
        payload: TokenClaims | None = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            try:
                payload = verify_jwt(token)
            except (TokenExpiredError, TokenInvalidError):
                # Never decode without verification. Fall through to the routing
                # hint; route-level deps (get_current_user) then produce the 401.
                logger.debug(
                    "jwt_verification_failed",
                    path=request.url.path,
                    request_id=request.state.request_id,
                )

        # --- 4. Resolve the tenant, then verify it exists and is active ---
        user_id: str | None = None
        async with async_session_factory() as session:
            repo = TenantRepository(session)
            if payload is not None:
                # Authenticated: the signed claim decides the tenant.
                jwt_tenant_id = payload.get("tenant_id")
                if jwt_tenant_id is None:
                    raise TenantMismatchError("Access token is missing its tenant claim.")
                user_id = payload.get("sub")
                tenant = await repo.get_by_id(jwt_tenant_id)
                if tenant is None:
                    raise TenantNotFoundError("Access token references an unknown tenant")
                if hint is not None:
                    cross_check_routing_hint(tenant.slug, hint)
                slug = tenant.slug
            else:
                # Unauthenticated: the hint is routing only - it grants no access.
                if hint is None:
                    raise TenantContextMissingError(
                        "Tenant cannot be resolved from the request. Send a tenant "
                        "subdomain host, or X-Tenant-Slug, together with a bearer token."
                    )
                tenant = await repo.get_by_slug(hint)
                if tenant is None:
                    raise TenantNotFoundError(f"No tenant found for slug '{hint}'")
                slug = hint
            if not tenant.is_active:
                raise TenantDisabledError(f"Tenant '{slug}' is disabled")
            tenant_id = str(tenant.id)

        # --- 5. Populate the request-scoped context ---
        TenantContext.set(tenant_id)
        TenantContext.set_tenant_slug(slug)
        TenantContext.set_user_id(user_id)
        structlog.contextvars.bind_contextvars(tenant_id=tenant_id, user_id=user_id)

        try:
            response = await call_next(request)
            return response
        finally:
            TenantContext.reset()
            structlog.contextvars.unbind_contextvars("tenant_id", "user_id")
