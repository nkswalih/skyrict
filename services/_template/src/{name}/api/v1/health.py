"""Health check endpoints — /health and /ready."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    """Liveness probe — is the service running?"""
    return {"status": "healthy", "service": "{name}"}


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness probe — is the service ready to accept traffic?"""
    return {"status": "ready", "service": "{name}"}
