"""Skyrict common utilities — shared across all services."""

from skyrict_common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidPasswordError,
    MFARequiredError,
    MFAVerificationError,
    PasskeyError,
    RateLimitExceededError,
    SessionExpiredError,
    SessionNotFoundError,
    SkyrictError,
    TenantContextMissingError,
    TenantDisabledError,
    TenantNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
    UserAlreadyExistsError,
    UserDisabledError,
    UserNotFoundError,
    ValidationError,
)
from skyrict_common.logging import configure_logging, get_logger
from skyrict_common.pagination import PaginationParams
from skyrict_common.schemas import (
    ErrorDetail,
    ErrorResponse,
    ListResponse,
    PaginationMeta,
    ResponseEnvelope,
)

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "configure_logging",
    "ErrorDetail",
    "ErrorResponse",
    "get_logger",
    "InvalidPasswordError",
    "ListResponse",
    "MFARequiredError",
    "MFAVerificationError",
    "PaginationMeta",
    "PaginationParams",
    "PasskeyError",
    "RateLimitExceededError",
    "ResponseEnvelope",
    "SessionExpiredError",
    "SessionNotFoundError",
    "SkyrictError",
    "TenantContextMissingError",
    "TenantDisabledError",
    "TenantNotFoundError",
    "TokenExpiredError",
    "TokenInvalidError",
    "UserAlreadyExistsError",
    "UserDisabledError",
    "UserNotFoundError",
    "ValidationError",
]

__version__ = "0.1.0"
