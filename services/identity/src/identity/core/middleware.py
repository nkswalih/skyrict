"""Middleware stack — TenantContext, request-id.

These run on EVERY request. Keep them lightweight and fast.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from identity.core.tenant_context import TenantContext

logger = structlog.get_logger("identity.middleware")

# Paths that don't require authentication or tenant context
_SKIP_AUTH_PATHS = frozenset({"/health", "/ready", "/docs", "/openapi.json", "/redoc"})


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
    """Extract tenant_id from verified JWT and set TenantContext.

    Calls security.verify_jwt() — the ONE AND ONLY decode path.
    Never trusts an unverified token.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in _SKIP_AUTH_PATHS:
            return await call_next(request)

        tenant_id: str | None = None

        # Extract from verified JWT via security.verify_jwt()
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from identity.core.security import verify_jwt

                token = auth_header.removeprefix("Bearer ").strip()
                payload = verify_jwt(token)
                tenant_id = payload.get("tenant_id")
            except Exception:
                # Invalid/expired token — let route-level deps handle the error.
                # We only need tenant_id here for context; auth errors are
                # raised by get_current_user in deps.py.
                pass

        # Fallback to X-Tenant-ID header (for service-to-service calls)
        if not tenant_id:
            tenant_id = request.headers.get("X-Tenant-ID")

        if tenant_id:
            TenantContext.set(tenant_id)
            structlog.contextvars.bind_contextvars(tenant_id=tenant_id)

        try:
            response = await call_next(request)
            return response
        finally:
            TenantContext.reset()
