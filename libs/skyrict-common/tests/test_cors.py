"""Tests for the tenant-subdomain CORS policy.

The security-relevant cases are the negatives: a pattern that is too permissive
turns `Access-Control-Allow-Origin` into an open door for credentialed
cross-origin requests, so each way of over-matching is pinned here rather than
left to inspection of the generated regex.
"""

from __future__ import annotations

import re

import pytest

from skyrict_common.cors import is_valid_base_domain, tenant_origin_regex


class TestIsValidBaseDomain:
    @pytest.mark.parametrize(
        "domain",
        ["skyrict.in", "beta.skyrict.in", "a.b.skyrict.in", "sky-rict.in", "x1.y2.z3.dev"],
    )
    def test_accepts_plain_domains(self, domain: str) -> None:
        assert is_valid_base_domain(domain) is True

    @pytest.mark.parametrize(
        "domain",
        [
            "",
            "   ",
            "localhost",  # single label: not a registrable domain
            "localhost:3000",  # port
            "https://skyrict.in",  # scheme
            "skyrict.in/path",  # path
            "user@skyrict.in",  # userinfo
            "*.skyrict.in",  # wildcard
            "skyrict.in:443",
            "-skyrict.in",  # label starting with a hyphen
            "skyrict.in-",  # label ending with a hyphen
            "skyrict..in",  # empty label
            "SKY RICT.in",  # embedded space
        ],
    )
    def test_rejects_anything_that_is_not_a_domain(self, domain: str) -> None:
        assert is_valid_base_domain(domain) is False

    def test_is_case_insensitive(self) -> None:
        assert is_valid_base_domain("  SKYrict.IN  ") is True

    def test_base_domain_regex_is_linear(self) -> None:
        """Regression for CodeQL ``py/redos`` (high) on the old nested-quantifier
        pattern: ``[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?...`` had overlapping character
        classes inside the repeated label group, so a full-match that failed at
        the end backtracked exponentially on inputs of repeated ``0.00.00...``
        labels. The linear form answers these in microseconds; the old form took
        minutes at 40 labels. Asserting both the accepting and the failing
        shapes keeps the linearity honest without a wall-clock timer.
        """
        pathological = "0." + "00." * 40 + "00"
        assert is_valid_base_domain(pathological) is True
        # A trailing dot forces a full-match failure - the blow-up path.
        assert is_valid_base_domain(pathological + ".") is False


class TestTenantOriginRegex:
    def test_matches_a_tenant_subdomain(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert re.match(pattern, "https://acme.skyrict.in") is not None
        assert re.match(pattern, "https://sky-rict-1.skyrict.in") is not None

    def test_pattern_is_anchored_on_both_ends(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert pattern.startswith("^")
        assert pattern.endswith("$")

    def test_rejects_lookalike_parent_domain(self) -> None:
        """The reason for the trailing anchor: a prefix match would let
        `skyrict.in.attacker.example` through."""
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert re.match(pattern, "https://acme.skyrict.in.attacker.example") is None

    def test_rejects_prefix_of_the_base_domain(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        # No tenant label at all - the apex is covered by the exact-match list.
        assert re.match(pattern, "https://skyrict.in") is None
        # Suffix confusion.
        assert re.match(pattern, "https://acme.notskyrict.in") is None

    def test_rejects_nested_subdomains(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert re.match(pattern, "https://a.b.skyrict.in") is None

    def test_rejects_plaintext_scheme(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert re.match(pattern, "http://acme.skyrict.in") is None

    def test_rejects_other_schemes(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert re.match(pattern, "null") is None
        assert re.match(pattern, "https://acme.skyrict.in:8443") is None

    def test_rejects_a_trailing_dot_fully_qualified_form(self) -> None:
        pattern = tenant_origin_regex("skyrict.in")
        assert pattern is not None
        assert re.match(pattern, "https://acme.skyrict.in.") is None

    def test_dots_in_the_base_domain_are_escaped(self) -> None:
        pattern = tenant_origin_regex("beta.skyrict.in")
        assert pattern is not None
        # The dot must be literal, not "any character".
        assert re.match(pattern, "https://acme.betaxskyrictxin") is None
        assert re.match(pattern, "https://acme.beta.skyrict.in") is not None

    @pytest.mark.parametrize("domain", ["", "   ", "localhost:3000", "https://skyrict.in"])
    def test_returns_none_for_unusable_base_domains(self, domain: str) -> None:
        """`None` is the degrade-to-exact-match-list signal, and local
        development must never crash on it."""
        assert tenant_origin_regex(domain) is None
