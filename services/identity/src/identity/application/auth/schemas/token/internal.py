"""Token internal schemas — used by services, not exposed in API."""

from __future__ import annotations

from pydantic import BaseModel


class TokenPayloadSchema(BaseModel):
    """Decoded JWT payload."""

    sub: str
    tenant_id: str
    type: str  # "access" or "refresh"
    exp: int
    iat: int
