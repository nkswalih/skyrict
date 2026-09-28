"""Skyrict common utilities - shared across all services."""

from skyrict_common.config_types import NonEmptyStr
from skyrict_common.cors import is_valid_base_domain, tenant_origin_regex
from skyrict_common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvalidPasswordError,
    MFARequiredError,
    MFAVerificationError,
    PasskeyError,
    RateLimitExceededError,
    RateLimitUnavailableError,
    ServiceUnavailableError,
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
from skyrict_common.problems import PROBLEM_BASE_URL
from skyrict_common.schemas import (
    ErrorDetail,
    ErrorResponse,
    ListResponse,
    PaginationMeta,
    ResponseEnvelope,
)

__all__ = [
    "PROBLEM_BASE_URL",
    "AuthenticationError",
    "AuthorizationError",
    "ErrorDetail",
    "ErrorResponse",
    "InvalidPasswordError",
    "ListResponse",
    "MFARequiredError",
    "MFAVerificationError",
    "NonEmptyStr",
    "PaginationMeta",
    "PaginationParams",
    "PasskeyError",
    "RateLimitExceededError",
    "RateLimitUnavailableError",
    "ResponseEnvelope",
    "ServiceUnavailableError",
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
    "configure_logging",
    "get_logger",
    "is_valid_base_domain",
    "tenant_origin_regex",
]

__version__ = "0.1.0"
