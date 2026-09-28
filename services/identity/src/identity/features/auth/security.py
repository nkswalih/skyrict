"""Auth security helpers - JWT tenant cross-checking.

Pure functions shared by the HTTP middleware and the API dependency layer;
both are consumers that verify a token belongs to the routed tenant.
"""

from __future__ import annotations

from identity.core.exceptions import TenantMismatchError


def cross_check_jwt_tenant(jwt_tenant_id: str | None, routed_tenant_id: str) -> None:
    """Reject when a verified JWT's tenant claim differs from the routed tenant.

    Raises TenantMismatchError (401); processing stops. A missing JWT claim is
    treated as a mismatch (a valid token must always carry its tenant).
    """
    if jwt_tenant_id is None or jwt_tenant_id != routed_tenant_id:
        raise TenantMismatchError(
            "Token tenant does not match the tenant resolved from the request routing."
        )


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
    if token_tenant_slug != hint_slug:
        raise TenantMismatchError(
            "Token tenant does not match the tenant named by the request routing."
        )
