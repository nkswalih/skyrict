"""Base exceptions for Skyrict services.

Every service should catch these at the API layer and map them to HTTP responses.
Domain code should raise these, never HTTPException.
"""

from __future__ import annotations


class SkyrictError(Exception):
    """Base exception for all Skyrict domain errors."""

    message: str = "An unexpected error occurred"
    code: str = "SKYRICT_ERROR"

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.message = message or self.__class__.message
        self.code = code or self.__class__.code
        super().__init__(self.message)


# ---------- Auth ----------

class AuthenticationError(SkyrictError):
    message = "Authentication failed"
    code = "AUTHENTICATION_ERROR"


class AuthorizationError(SkyrictError):
    message = "You do not have permission to perform this action"
    code = "AUTHORIZATION_ERROR"


class TokenExpiredError(AuthenticationError):
    message = "Token has expired"
    code = "TOKEN_EXPIRED"


class TokenInvalidError(AuthenticationError):
    message = "Token is invalid"
    code = "TOKEN_INVALID"


class MFARequiredError(AuthenticationError):
    message = "Multi-factor authentication is required"
    code = "MFA_REQUIRED"


class MFAVerificationError(AuthenticationError):
    message = "MFA verification failed"
    code = "MFA_VERIFICATION_ERROR"


class PasskeyError(AuthenticationError):
    message = "Passkey verification failed"
    code = "PASSKEY_ERROR"


# ---------- User ----------

class UserNotFoundError(SkyrictError):
    message = "User not found"
    code = "USER_NOT_FOUND"


class UserAlreadyExistsError(SkyrictError):
    message = "A user with this email already exists"
    code = "USER_ALREADY_EXISTS"


class UserDisabledError(SkyrictError):
    message = "This user account has been disabled"
    code = "USER_DISABLED"


class InvalidPasswordError(AuthenticationError):
    message = "Invalid password"
    code = "INVALID_PASSWORD"


# ---------- Tenant / Organization ----------

class TenantNotFoundError(SkyrictError):
    message = "Organization not found"
    code = "TENANT_NOT_FOUND"


class TenantDisabledError(SkyrictError):
    message = "This organization has been disabled"
    code = "TENANT_DISABLED"


class TenantContextMissingError(SkyrictError):
    message = "Tenant context is not set"
    code = "TENANT_CONTEXT_MISSING"


# ---------- Session ----------

class SessionNotFoundError(SkyrictError):
    message = "Session not found"
    code = "SESSION_NOT_FOUND"


class SessionExpiredError(SkyrictError):
    message = "Session has expired"
    code = "SESSION_EXPIRED"


# ---------- Validation ----------

class ValidationError(SkyrictError):
    message = "Validation failed"
    code = "VALIDATION_ERROR"


# ---------- Rate Limiting ----------

class RateLimitExceededError(SkyrictError):
    message = "Rate limit exceeded"
    code = "RATE_LIMIT_EXCEEDED"
