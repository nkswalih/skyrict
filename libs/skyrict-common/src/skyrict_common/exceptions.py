"""
Base exceptions for Skyrict services.

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


class PermissionDeniedError(AuthorizationError):
    message = "You do not have permission to access this resource"
    code = "PERMISSION_DENIED"


# ---------- Billing ----------


class PaymentRequiredError(SkyrictError):
    message = "An active subscription is required"
    code = "PAYMENT_REQUIRED"


class TokenExpiredError(AuthenticationError):
    message = "Token has expired"
    code = "TOKEN_EXPIRED"


class TokenInvalidError(AuthenticationError):
    message = "Token is invalid"
    code = "TOKEN_INVALID"


class TokenReuseDetectedError(AuthenticationError):
    message = "Refresh token reuse detected"
    code = "TOKEN_REUSE_DETECTED"


class MFARequiredError(AuthenticationError):
    message = "Multi-factor authentication is required"
    code = "MFA_REQUIRED"


class MFAVerificationError(AuthenticationError):
    message = "MFA verification failed"
    code = "MFA_VERIFICATION_ERROR"


class EmailNotVerifiedError(AuthenticationError):
    message = "Email address has not been verified"
    code = "EMAIL_NOT_VERIFIED"


class PasskeyError(AuthenticationError):
    message = "Passkey verification failed"
    code = "PASSKEY_ERROR"


# ---------- User ----------


class NotFoundError(SkyrictError):
    message = "Resource not found"
    code = "NOT_FOUND"


class ConflictError(SkyrictError):
    message = "The request conflicts with the current state of the resource"
    code = "CONFLICT"


class UserNotFoundError(NotFoundError):
    message = "User not found"
    code = "USER_NOT_FOUND"


class UserAlreadyExistsError(ConflictError):
    message = "A user with this email already exists"
    code = "USER_ALREADY_EXISTS"


class UserDisabledError(SkyrictError):
    message = "This user account has been disabled"
    code = "USER_DISABLED"


class InvalidPasswordError(AuthenticationError):
    message = "Invalid password"
    code = "INVALID_PASSWORD"


# ---------- Tenant / Organization ----------


class TenantNotFoundError(NotFoundError):
    message = "Organization not found"
    code = "TENANT_NOT_FOUND"


class TenantDisabledError(SkyrictError):
    message = "This organization has been disabled"
    code = "TENANT_DISABLED"


class TenantContextMissingError(SkyrictError):
    message = "Tenant context is not set"
    code = "TENANT_CONTEXT_MISSING"


class TenantMismatchError(AuthenticationError):
    message = "Token tenant does not match the routed tenant"
    code = "TENANT_MISMATCH"


# ---------- Session ----------


class SessionNotFoundError(NotFoundError):
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

    def __init__(
        self,
        message: str | None = None,
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        """Optionally carry how long the caller must wait before retrying.

        ``enforce()`` attaches the seconds-until-window-close so the API layer
        can emit an HTTP ``Retry-After`` header on the 429 response.
        """
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailableError(SkyrictError):
    message = "Service temporarily unavailable"
    code = "RATE_LIMIT_UNAVAILABLE"


class InvitationNotFoundError(NotFoundError):
    message = "Invitation not found"
    code = "INVITATION_NOT_FOUND"


class InvitationExpiredError(SkyrictError):
    message = "Invitation has expired"
    code = "INVITATION_EXPIRED"


class InvitationAlreadyUsedError(SkyrictError):
    message = "Invitation has already been used"
    code = "INVITATION_ALREADY_USED"


class InvitationEmailMismatchError(SkyrictError):
    message = "Email does not match the invitation"
    code = "INVITATION_EMAIL_MISMATCH"


# ---------- Handoff ----------


class HandoffTokenNotFoundError(NotFoundError):
    message = "Handoff token not found"
    code = "HANDOFF_TOKEN_NOT_FOUND"


class HandoffTokenExpiredError(SkyrictError):
    message = "Handoff token has expired"
    code = "HANDOFF_TOKEN_EXPIRED"


class HandoffTokenAlreadyUsedError(SkyrictError):
    message = "Handoff token has already been used"
    code = "HANDOFF_TOKEN_ALREADY_USED"
