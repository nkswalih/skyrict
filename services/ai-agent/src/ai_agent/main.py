"""FastAPI application factory with lifespan, middleware, and router mounting."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

import ai_agent.models  # noqa: F401  # register ORM models on the Base metadata
from ai_agent.api.lifespan import lifespan
from ai_agent.api.middleware import RequestIdMiddleware, TenantContextMiddleware
from ai_agent.api.v1.router import api_router
from ai_agent.core.config import Environment, settings
from ai_agent.core.constants import SERVICE_NAME, SERVICE_VERSION
from ai_agent.core.exceptions import (
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
        title=f"Skyrict {SERVICE_NAME.replace('-', ' ').title()} Service",
        description=(
            "Provider-agnostic AI agent service - LLM routing with fallback, "
            "inventory AI features, shared AI tables, and audit logging"
        ),
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
        # Kept identical to identity and core. ai-agent is not in the public
        # route map today - core proxies to it server-to-server, where CORS
        # never applies - but it already declares CORS configuration, and
        # three copies of this policy that can drift is the failure mode that
        # produced the wrong published domain three times.
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
