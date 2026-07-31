"""Token schemas — re-exports for backward-compatible imports."""

from {name}.schemas.token.internal import TokenPayloadSchema
from {name}.schemas.token.responses import TokenIntrospectionResponse

__all__ = [
    "TokenIntrospectionResponse",
    "TokenPayloadSchema",
]
