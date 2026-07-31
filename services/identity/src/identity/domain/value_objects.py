"""Value objects — immutable, identity-less domain concepts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskScore(Enum):
    """Risk assessment for authentication attempts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class TokenPair:
    """Access + refresh token pair returned after authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 1800  # seconds

    @property
    def authorization_header(self) -> str:
        return f"{self.token_type} {self.access_token}"


@dataclass(frozen=True)
class PasswordPolicy:
    """Password validation rules."""

    min_length: int = 8
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_digit: bool = True
    require_special: bool = True

    def validate(self, password: str) -> list[str]:
        """Return list of validation error messages (empty = valid)."""
        errors: list[str] = []
        if len(password) < self.min_length:
            errors.append(f"Password must be at least {self.min_length} characters")
        if self.require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")
        if self.require_lowercase and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")
        if self.require_digit and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")
        if self.require_special and not any(not c.isalnum() for c in password):
            errors.append("Password must contain at least one special character")
        return errors


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT payload."""

    sub: str
    tenant_id: str
    type: str  # "access" or "refresh"
    exp: int
    iat: int
