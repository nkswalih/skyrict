r"""CORS origin policy for tenant subdomains.

The web app is served from a per-tenant subdomain - `https://acme.skyrict.in` -
and it calls the API on a *different* origin, `https://api.skyrict.in`. That is
cross-origin, so the API has to say which origins it answers for.

The three services configure that with `allow_origins=CORS_ORIGINS`, which is an
**exact-match list**, and it is set from the IaC to `["https://skyrict.in"]` -
the apex only. Starlette has no wildcard support when `allow_credentials=True`,
which every service here sets, so the apex-only list is the only thing that
works without a regex. A page on `https://acme.skyrict.in` is then blocked, and
the browser reports it as a CORS error with no server-side trace: the request
never reaches application code, so nothing logs and nothing alerts.

The fix is an **anchored** `allow_origin_regex` alongside the exact-match list.
Anchoring is the whole safety argument, so it is worth being precise about what
each part of the pattern rules out:

    ^https://[a-z0-9-]+\.skyrict\.in$
    ^  https://            scheme is pinned. `http://` is not accepted, so a
                            page cannot downgrade itself into the allow-list.
       [a-z0-9-]+          exactly ONE label, and no dot inside it. A nested
                            name like `a.b.skyrict.in` is not a tenant host.
       \.skyrict\.in       the base domain, escaped.
    $                      the end. Without it, `https://acme.skyrict.in.attacker.example`
                            would match, because the pattern is a prefix test.

The slug character class is `[a-z0-9-]+` deliberately: it is the same class
`identity.core.tenant_resolver` already compiles as `_TENANT_SLUG_RE` to decide
whether a Host label is a tenant at all. If the two ever disagreed, a slug the
resolver would accept could be refused by CORS - or worse, a host the resolver
treats as a tenant could be reflected into `Access-Control-Allow-Origin`. They
are written as one class here for that reason.

The base domain is **derived** from `BASE_DOMAIN`, not configured separately.
`BASE_DOMAIN` is already injected into all three services by the IaC and is
already required in staging and production, and a second copy of the same domain
string is exactly the drift that let the published domain be wrong three times
(see `PROBLEM_BASE_URL` in `problems.py` for that history).

A value that is not a plain registrable domain - the empty string that local
development runs with, or `localhost:3000` - returns ``None`` rather than
raising. ``allow_origin_regex=None`` leaves the middleware on its exact-match
list, which is the behaviour that already works; the alternative would be an
import-time crash in every local environment to catch a condition that is only
meaningful in production. The production guard is the other half of this: the
staging/production settings check requires `BASE_DOMAIN` to be a valid domain
and refuses to start otherwise, so a misconfigured production deploy fails
loudly instead of quietly serving an empty CORS policy.
"""

from __future__ import annotations

import re

__all__ = ["is_valid_base_domain", "tenant_origin_regex"]

#: One tenant slug label. Same class as identity's `_TENANT_SLUG_RE`.
_SLUG_LABEL = r"[a-z0-9-]+"

#: A plain registrable domain: dot-separated labels of alphanumerics and
#: hyphens. Deliberately excludes `:`, `/`, `@` and `*` so a base domain can
#: never smuggle a port, a path, userinfo or a wildcard into the pattern.
#:
#: The shape is deliberately linear. The naive alternative
#: ``[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+$``
#: lets the label's character classes overlap, so a full-match that fails at
#: the end (say, a trailing dot) makes the engine retry every split of every
#: label - exponential on inputs like ``0.00.00.00...`` (CodeQL ``py/redos``,
#: high). Here each label is one ``[a-z0-9-]+`` group whose class is disjoint
#: from the ``\.`` separator, which the engine matches deterministically; the
#: "no leading/trailing hyphen" rule moves to an explicit check below.
_BASE_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")


def is_valid_base_domain(base_domain: str) -> bool:
    """Return True when `base_domain` is a plain multi-label domain name.

    ``skyrict.in`` and ``beta.skyrict.in`` pass. ``""``, ``localhost``,
    ``localhost:3000``, ``*.skyrict.in`` and ``https://skyrict.in`` do not -
    the last four would each widen or misdirect the generated pattern.
    """
    if not base_domain:
        return False
    domain = base_domain.strip().lower()
    if _BASE_DOMAIN_RE.fullmatch(domain) is None:
        return False
    # DNS labels must not start or end with a hyphen; `[a-z0-9-]+` alone would
    # accept `-skyrict.in` and `skyrict.in-`, which are not registrable domains.
    return all(not label.startswith("-") and not label.endswith("-") for label in domain.split("."))


def tenant_origin_regex(base_domain: str) -> str | None:
    """Build the anchored `allow_origin_regex` for tenant subdomains.

    Returns ``None`` when `base_domain` is not a usable domain name, which
    leaves the caller on its exact-match origin list. That is the correct
    degradation for local development, where `BASE_DOMAIN` is empty or points
    at a host and port rather than a domain.
    """
    domain = base_domain.strip().lower()
    if not is_valid_base_domain(domain):
        return None
    return rf"^https://{_SLUG_LABEL}\.{re.escape(domain)}$"
