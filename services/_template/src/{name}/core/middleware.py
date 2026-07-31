"""Middleware stack — TenantContext, request-id.

These run on EVERY request. Keep them lightweight and fast.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from {name}.core.constants import SKIP_AUTH_PATHS
from {name}.core.tenant_context import TenantContext

logger = structlog.get_logger("{name}.middleware")


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
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in SKIP_AUTH_PATHS:
            return await call_next(request)

        tenant_id: str | None = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                from {name}.core.security import verify_jwt

                token = auth_header.removeprefix("Bearer ").strip()
                payload = verify_jwt(token)
                tenant_id = payload.get("tenant_id")
            except Exception:
                pass

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
