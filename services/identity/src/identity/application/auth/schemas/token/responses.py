"""Token response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class TokenIntrospectionResponse(BaseModel):
    """POST /auth/introspect — token introspection."""

    active: bool
    sub: str | None = None
    tenant_id: str | None = None
    type: str | None = None
    exp: int | None = None
    scope: str | None = None
