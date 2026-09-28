"""The RFC 7807 problem-type base is a published contract, so it is pinned.

This is the single place the literal appears in the repository. Every other
assertion in the suite checks that a service's exception maps to
``<base>/<slug>``; only this file checks that the base itself is what we
publish, and that it has not quietly reverted to a retired domain.
"""

from __future__ import annotations

import re

import pytest

from skyrict_common.problems import PROBLEM_BASE_URL

# Domains this project has served from and must never publish problem types
# under again. See docs/runbooks/pre-release-audit-2026-09.md finding 16: the
# services emitted api.skyrict.io for a full release cycle while the deployed
# host was api.skyrict.in, and nothing failed until a client compared the two.
_RETIRED_TLDS = ("skyrict.com", "skyrict.io", "skyrict.dev")


def test_problem_base_is_the_live_api_host() -> None:
    # Spelled out in full and in this order on purpose. This is the one
    # assertion in the repository that checks the published value rather than
    # how a service consumes it; every other test builds its expectations from
    # PROBLEM_BASE_URL, so a change here would otherwise pass silently.
    assert PROBLEM_BASE_URL == "https://api.skyrict.in/problems"


def test_problem_base_has_no_trailing_slash() -> None:
    # Services build types as f"{PROBLEM_BASE_URL}/{slug}". A trailing slash
    # would produce ".../problems//token-expired", which is a different
    # identifier and would silently break every client that switches on it.
    assert not PROBLEM_BASE_URL.endswith("/")
    assert PROBLEM_BASE_URL.count("/") == 3  # https:// + host + /problems


@pytest.mark.parametrize("tld", _RETIRED_TLDS)
def test_problem_base_uses_no_retired_domain(tld: str) -> None:
    assert tld not in PROBLEM_BASE_URL


def test_problem_base_is_an_absolute_https_uri() -> None:
    # A relative or http:// base would not be dereferenceable, and would fail
    # the public API's own requirement that problem types are absolute URIs.
    assert re.match(r"^https://[a-z0-9.-]+(/[a-z0-9-]+)+$", PROBLEM_BASE_URL)
