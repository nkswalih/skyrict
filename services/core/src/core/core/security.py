"""
JWT verification for the core service - RS256, verify-only.

Core never signs tokens: it VERIFIES access tokens issued by the identity
service using the shared RS256 public key and the same issuer/audience. Every
other layer MUST go through verify_jwt() - the single verification path.

The token's ``tenant_id`` claim is cross-checked against the routed tenant by
the middleware / get_current_user; permissions are NEVER read from JWT claims -
they are resolved from the database at request time (see api/deps.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NotRequired, TypedDict, cast

import jwt

from core.core.config import settings
from core.core.exceptions import StartupError, TokenExpiredError, TokenInvalidError

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.types import PublicKeyTypes

# Algorithms we accept - explicitly whitelisted. Rejects "none" and any
# header-driven algorithm switching (CVE-2015-2951 / algorithm confusion).
_ALLOWED_ALGORITHMS = {"RS256"}


class TokenClaims(TypedDict):
    """
    Verified JWT claims returned by :func:`verify_jwt`.

    ``iat``/``nbf``/``exp`` are POSIX timestamps (epoch seconds).
    ``type`` is ``"access"``.
    """

    sub: str
    tenant_id: str
    iss: str
    aud: str
    iat: int
    exp: int
    nbf: int
    type: str
    session_id: NotRequired[str]


def verify_jwt(token: str) -> TokenClaims:
    """Decode and VERIFY a JWT - the ONE AND ONLY verification path.

    Security guarantees:
      - RS256 only (asymmetric - public key verifies)
      - Algorithm whitelist rejects "none" and header-driven attacks
      - Issuer and audience are validated
      - Expiry (exp) and not-before (nbf) are checked

    Returns:
        The verified claims as a :class:`TokenClaims`.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is malformed, signature is invalid,
            algorithm is not RS256, or issuer/audience don't match.
    """
    try:
        unverified_header = jwt.get_unverified_header(token)
        alg = unverified_header.get("alg", "")
        if alg not in _ALLOWED_ALGORITHMS:
            raise TokenInvalidError(f"Token algorithm '{alg}' is not allowed. Expected RS256.")

        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=list(_ALLOWED_ALGORITHMS),
            issuer=settings.JWKS_ISSUER,
            audience=settings.JWKS_AUDIENCE,
            options={
                # PyJWT 2.13 validates required claims via a "require" list of
                # claim names (the legacy per-claim require_* flags are gone).
                # Require every claim our contract needs so tokens that omit
                # exp/iat/sub/iss/aud are rejected, not silently accepted.
                "require": ["aud", "iat", "exp", "iss", "sub"],
            },
        )
        return cast("TokenClaims", payload)

    except jwt.PyJWTError as exc:
        exc_str = str(exc).lower()
        if "expired" in exc_str:
            raise TokenExpiredError() from exc
        raise TokenInvalidError(str(exc)) from exc


def cross_check_jwt_tenant(token_tenant_id: Any, routed_tenant_id: str) -> None:
    """Reject a token whose tenant claim differs from the routed tenant.

    Raises:
        TenantMismatchError: When the claims' tenant_id does not match the
            tenant resolved from the routing layer.
    """
    from skyrict_common.exceptions import TenantMismatchError

    if str(token_tenant_id) != routed_tenant_id:
        raise TenantMismatchError("Token tenant does not match the routed tenant")


def cross_check_routing_hint(token_tenant_slug: str, hint_slug: str) -> None:
    """Reject when a verified token's tenant differs from the request's routing hint.

    The signed ``tenant_id`` claim is the tenant authority. The routing hint
    (Host label, else X-Tenant-Slug) only records which tenant the caller
    believes it is addressing. When both are present they must agree: a
    disagreement means the caller holds a credential for one tenant while
    naming another, which is a cross-tenant attempt and is refused before any
    tenant data is read.

    Callers must skip this when the hint is absent - on a shared API host the
    Host names no tenant, and the token is then the only signal available.

    Raises:
        TenantMismatchError: When the token's tenant slug and the hint disagree.
    """
    from skyrict_common.exceptions import TenantMismatchError

    if token_tenant_slug != hint_slug:
        raise TenantMismatchError(
            "Token tenant does not match the tenant named by the request routing"
        )


def verify_jwt_key_usable() -> None:
    """Verify the configured public key parses as an RSA key of >= 2048 bits.

    Runs ONCE at application startup so a corrupt, non-RSA, or weak key fails
    fast at boot (the lifespan raises :class:`StartupError`) instead of
    surfacing mid-request as opaque verification failures.
    """
    from cryptography.exceptions import UnsupportedAlgorithm
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    try:
        public_key: PublicKeyTypes = serialization.load_pem_public_key(
            settings.jwt_public_key.encode("utf-8"),
        )
    except (TypeError, UnsupportedAlgorithm, ValueError) as exc:
        raise StartupError(f"JWT public key is not a valid PEM public key: {exc}") from exc

    if not isinstance(public_key, rsa.RSAPublicKey):
        raise StartupError(f"JWT public key is not an RSA key (got {type(public_key).__name__})")
    if public_key.key_size < 2048:
        raise StartupError(
            f"JWT public key is only {public_key.key_size} bits - RSA 2048 or larger required"
        )
