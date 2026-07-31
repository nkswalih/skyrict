"""JWT sign/verify (RS256) and password hashing (Argon2id).

Every other layer MUST go through these functions. Never verify JWTs inline.
Single verification path: verify_jwt().
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from {name}.core.config import settings
from {name}.core.exceptions import TokenExpiredError, TokenInvalidError

# Algorithms we accept — explicitly whitelisted. Rejects "none" and any
# header-driven algorithm switching (CVE-2015-2951 / algorithm confusion).
_ALLOWED_ALGORITHMS = {"RS256"}


# ---------------------------------------------------------------------------
# Password hashing — Argon2id (OWASP recommended)
# ---------------------------------------------------------------------------
try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError

    _ph = PasswordHasher(
        time_cost=3,        # number of iterations
        memory_cost=65536,  # 64 MB
        parallelism=4,      # threads
        hash_len=32,        # output length
        salt_len=16,        # salt length
    )

    def hash_password(password: str) -> str:
        """Hash a plaintext password with Argon2id."""
        return _ph.hash(password)

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against its Argon2id hash."""
        try:
            return _ph.verify(hashed_password, plain_password)
        except (VerifyMismatchError, VerificationError):
            return False

except ImportError:
    import logging
    logging.warning(
        "argon2-cffi not installed — falling back to plaintext comparison. "
        "DO NOT use in production. Install: pip install argon2-cffi"
    )

    def hash_password(password: str) -> str:  # type: ignore[misc]
        return password  # pragma: no cover

    def verify_password(plain_password: str, hashed_password: str) -> bool:  # type: ignore[misc]
        return plain_password == hashed_password  # pragma: no cover


# ---------------------------------------------------------------------------
# JWT — RS256 only
# ---------------------------------------------------------------------------
def create_access_token(
    subject: str,
    *,
    tenant_id: str,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed RS256 access token."""
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "iss": settings.JWKS_ISSUER,
        "aud": settings.JWKS_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_private_key, algorithm="RS256")


def create_refresh_token(
    subject: str,
    *,
    tenant_id: str,
) -> str:
    """Create a signed RS256 refresh token with longer expiry."""
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "iss": settings.JWKS_ISSUER,
        "aud": settings.JWKS_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_private_key, algorithm="RS256")


def verify_jwt(token: str) -> dict[str, Any]:
    """Decode and VERIFY a JWT — the ONE AND ONLY verification path.

    Security guarantees:
      - RS256 only (asymmetric — public key verifies, private key signs)
      - Algorithm whitelist rejects "none" and header-driven attacks
      - Issuer and audience are validated
      - Expiry (exp) and not-before (nbf) are checked

    Returns:
        The decoded payload dict.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is malformed, signature is invalid,
            algorithm is not RS256, or issuer/audience don't match.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "")
        if alg not in _ALLOWED_ALGORITHMS:
            raise TokenInvalidError(
                f"Token algorithm '{alg}' is not allowed. Expected RS256."
            )

        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=list(_ALLOWED_ALGORITHMS),
            issuer=settings.JWKS_ISSUER,
            audience=settings.JWKS_AUDIENCE,
            options={
                "require": ["exp", "iss", "aud", "sub", "iat"],
            },
        )
        return payload

    except JWTError as exc:
        exc_str = str(exc).lower()
        if "exp" in exc_str or "expired" in exc_str:
            raise TokenExpiredError() from exc
        raise TokenInvalidError(str(exc)) from exc
