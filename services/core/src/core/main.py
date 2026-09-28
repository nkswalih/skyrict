"""FastAPI application factory with lifespan, middleware, and router mounting."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

# Import every ORM model so SQLAlchemy can configure cross-module relationships
# before the first query (see core/models/__init__.py).
import core.models  # noqa: F401
from core.api.lifespan import lifespan
from core.api.middleware import RequestIdMiddleware, TenantContextMiddleware
from core.api.v1.router import api_router
from core.core.config import Environment, settings
from core.core.constants import SERVICE_NAME, SERVICE_VERSION
from core.core.exceptions import (
    SkyrictError,
    http_exception_handler,
    request_validation_error_handler,
    skyrict_error_handler,
    unhandled_error_handler,
)
from skyrict_common.cors import tenant_origin_regex


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings.SENTRY_DSN:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT.value,
            traces_sample_rate=0.1,
        )
    docs_enabled = settings.ENVIRONMENT != Environment.PRODUCTION

    app = FastAPI(
        title=f"Skyrict {SERVICE_NAME.title()} Service",
        description="ERP foundations - tenant/RLS plumbing, RBAC, Money, and Phase-1 ERP modules",
        version=SERVICE_VERSION,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    # --- Global exception handlers ---
    app.add_exception_handler(SkyrictError, skyrict_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)

    # --- Middleware (order matters: last added = first executed) ---
    # Execution order: RequestIdMiddleware → TenantContextMiddleware → CORSMiddleware.
    # RequestId must run first so request_id is bound before tenant resolution
    # logs, and so stale contextvars from the previous request are cleared.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        # The exact-match list is the apex only. Tenant pages are served from
        # per-tenant subdomains, which are dynamic, so they need the anchored
        # regex derived from BASE_DOMAIN. core is the app the browser actually
        # reaches for /api/v1/ai/agents/chat/stream, so without this the agent
        # chat SSE fails preflight and nothing logs. See skyrict_common.cors for
        # the anchoring argument.
        allow_origin_regex=tenant_origin_regex(settings.BASE_DOMAIN),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RequestIdMiddleware)

    # --- Routers ---
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
