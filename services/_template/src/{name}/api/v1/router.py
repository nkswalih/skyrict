"""V1 API router — aggregates all v1 endpoint modules."""

from __future__ import annotations

from fastapi import APIRouter

from {name}.api.v1.auth.router import router as auth_router
from {name}.api.v1.health import router as health_router
from {name}.api.v1.users.router import router as user_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(health_router)

# Add more routers as domains are implemented:
# from {name}.api.v1.{domain}.router import router as {domain}_router
# api_router.include_router({domain}_router)
