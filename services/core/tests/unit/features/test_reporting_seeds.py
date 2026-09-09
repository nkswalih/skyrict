"""Phase-1 report seed catalog tests (RPT-DATA-001).

The catalog is the single source of truth for the report pack used by both
migration 0036/0039 and the tenant-provisioning hook. These tests pin its
shape:

  - exactly the 12 reports from erp-phase1.md §M-RPT (unique slugs)
  - modules finance / sales / inventory / hr, three reports each
  - every SQL passes the read-only validator
  - every used bind is declared, and no declared bind is unused (tight whitelist)
  - every seed references the catalogue `erp.reports.read` permission
  - versioning: every seed declares a version, and version bumps are only
    accepted when the SQL actually changed (a version bump with no content
    change is a catalog error - it would rewrite identical rows forever)
"""

from __future__ import annotations

from collections import Counter

import pytest

from core.core.permissions import CATALOG, ERP_REPORTS_READ
from core.features.reporting.seeds import (
    PHASE_1_REPORT_SEEDS,
    find_seed_for_sql,
    is_seed_stale,
)
from core.features.reporting.validation import (
    ReportDefinitionValidationError,
    require_tenant_filter,
    validate_read_only_sql,
)

EXPECTED_SLUGS = frozenset(
    {
        "pnl_by_period",
        "ar_aging",
        "cash_received",
        "pipeline_value_by_stage",
        "orders_by_period",
        "top_customers",
        "stock_on_hand_vs_reorder",
        "movement_by_type",
        "slow_movers",
        "headcount_by_department",
        "leave_usage",
        "payroll_cost_by_period",
    }
)


class TestCatalogShape:
    def test_phase_one_has_twelve_reports(self) -> None:
        assert len(PHASE_1_REPORT_SEEDS) == 12

    def test_slugs_match_mrpt_spec(self) -> None:
        assert {s.slug for s in PHASE_1_REPORT_SEEDS} == EXPECTED_SLUGS

    def test_slugs_are_unique(self) -> None:
        slugs = [s.slug for s in PHASE_1_REPORT_SEEDS]
        assert len(slugs) == len(set(slugs))

    def test_modules_are_balanced(self) -> None:
        counts = Counter(s.module for s in PHASE_1_REPORT_SEEDS)
        assert counts == {"finance": 3, "sales": 3, "inventory": 3, "hr": 3}

    def test_every_seed_has_description_and_params(self) -> None:
        for seed in PHASE_1_REPORT_SEEDS:
            assert seed.title
            assert seed.description
            assert seed.params

    def test_every_seed_declares_a_version(self) -> None:
        for seed in PHASE_1_REPORT_SEEDS:
            assert seed.version >= 1

    def test_every_seed_declares_nl_vocabulary(self) -> None:
        """RPT-AI-001: every template must expose the selectable dataset,
        dimensions and measures the NL report builder is allowed to use."""
        for seed in PHASE_1_REPORT_SEEDS:
            assert seed.dataset
            assert seed.dimensions
            assert seed.measures


class TestFindSeedForSql:
    """The enrichment key that recovers template semantics for saved reports."""

    def test_matches_by_exact_sql(self) -> None:
        seed = next(s for s in PHASE_1_REPORT_SEEDS if s.slug == "ar_aging")
        assert find_seed_for_sql(seed.sql) is seed

    def test_matches_whitespace_collapsed_sql(self) -> None:
        """Legacy write paths collapse whitespace; stored rows must still
        resolve back to their template."""
        seed = next(s for s in PHASE_1_REPORT_SEEDS if s.slug == "ar_aging")
        collapsed = " ".join(seed.sql.split())
        assert find_seed_for_sql(collapsed) is seed

    def test_returns_none_for_unknown_sql(self) -> None:
        assert find_seed_for_sql("SELECT 1") is None


class TestSeedVersioning:
    """The drift contract shared by migration 0039 and the provisioning hook."""

    def test_newer_version_with_identical_sql_is_not_stale(self) -> None:
        """is_seed_stale compares SQL content too - a stored version newer than
        the seed with identical SQL is NOT stale (would rewrite forever)."""
        seed = next(s for s in PHASE_1_REPORT_SEEDS if s.slug == "ar_aging")
        assert not is_seed_stale(seed, version=seed.version + 1, sql=seed.sql)

    def test_same_version_with_different_sql_is_stale(self) -> None:
        seed = next(s for s in PHASE_1_REPORT_SEEDS if s.slug == "ar_aging")
        assert is_seed_stale(seed, version=seed.version, sql="SELECT 1")

    def test_whitespace_only_sql_difference_is_not_stale(self) -> None:
        """The legacy write paths collapsed whitespace; that must not count as
        drift or every existing tenant would be rewritten on first reconcile."""
        seed = next(s for s in PHASE_1_REPORT_SEEDS if s.slug == "ar_aging")
        collapsed = " ".join(seed.sql.split())
        assert not is_seed_stale(seed, version=seed.version, sql=collapsed)

    def test_older_version_with_different_sql_is_stale(self) -> None:
        seed = next(s for s in PHASE_1_REPORT_SEEDS if s.slug == "ar_aging")
        assert is_seed_stale(seed, version=seed.version - 1, sql="SELECT 1")


class TestPageOneValidity:
    @pytest.mark.parametrize("seed", PHASE_1_REPORT_SEEDS)
    def test_sql_is_read_only(self, seed) -> None:
        validate_read_only_sql(seed.sql, seed.params)

    @pytest.mark.parametrize("seed", PHASE_1_REPORT_SEEDS)
    def test_used_binds_match_declared_whitelist(self, seed) -> None:
        used = validate_read_only_sql(seed.sql, seed.params)
        # No unused declarations and no undeclared uses: the whitelist is the
        # query's parameter contract.
        assert used == set(seed.params)
        assert "tenant_id" in used

    @pytest.mark.parametrize("seed", PHASE_1_REPORT_SEEDS)
    def test_sql_filters_by_tenant_id(self, seed) -> None:
        """Defense-in-depth: every report must filter by tenant_id = :tenant_id."""
        require_tenant_filter(seed.sql)

    @pytest.mark.parametrize("seed", PHASE_1_REPORT_SEEDS)
    def test_permission_key_references_catalog(self, seed) -> None:
        assert seed.permission_key == ERP_REPORTS_READ
        assert seed.permission_key in CATALOG


class TestTenantFilterGate:
    """Defense-in-depth: require_tenant_filter rejects unscoped SQL."""

    def test_rejects_sql_without_tenant_filter(self) -> None:
        sql = "SELECT id, name FROM erp_products WHERE is_active = TRUE"
        with pytest.raises(ReportDefinitionValidationError, match="tenant_id"):
            require_tenant_filter(sql)

    def test_rejects_sql_with_tenant_bind_but_no_filter(self) -> None:
        # A SQL that binds :tenant_id but never uses it as a predicate
        # (e.g. just SELECT it). This must fail.
        sql = "SELECT :tenant_id AS tenant, name FROM erp_products"
        with pytest.raises(ReportDefinitionValidationError, match="tenant_id"):
            require_tenant_filter(sql)
