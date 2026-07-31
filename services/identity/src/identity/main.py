"""FastAPI application factory with lifespan, middleware, and router mounting."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from identity.api.v1.router import api_router
from identity.core.config import Environment, settings
from identity.core.constants import SERVICE_NAME, SERVICE_VERSION
from identity.core.exceptions import (
    SkyrictError,
    skyrict_error_handler,
    unhandled_error_handler,
)
from identity.core.lifespan import lifespan
from identity.core.middleware import RequestIdMiddleware, TenantContextMiddleware


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    docs_enabled = settings.ENVIRONMENT != Environment.PRODUCTION

    app = FastAPI(
        title=f"Skyrict {SERVICE_NAME.title()} Service",
        description="Authentication, authorization, multi-tenancy, sessions, and audit",
        version=SERVICE_VERSION,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    # --- Global exception handlers ---
    app.add_exception_handler(SkyrictError, skyrict_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]

    # --- Middleware (order matters: last added = first executed) ---
    # Execution order: CORSMiddleware → TenantContextMiddleware → RequestIdMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
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
