"""FastAPI application factory with lifespan, middleware, and router mounting."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from {name}.api.v1.router import api_router
from {name}.core.config import Environment, settings
from {name}.core.constants import SERVICE_NAME, SERVICE_VERSION
from {name}.core.exceptions import (
    SkyrictError,
    skyrict_error_handler,
    unhandled_error_handler,
)
from {name}.core.lifespan import lifespan
from {name}.core.middleware import RequestIdMiddleware, TenantContextMiddleware
from {name}.core.telemetry import init_telemetry


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    init_telemetry()

    docs_enabled = settings.ENVIRONMENT != Environment.PRODUCTION

    app = FastAPI(
        title=f"Skyrict {SERVICE_NAME.title()} Service",
        description="[Describe what this service does]",
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
