"""Permission catalog consistency tests - CATALOG vs PERMISSION_MODULES."""

from __future__ import annotations

from core.core.permissions import (
    CATALOG,
    ERP_CRM_READ,
    ERP_CRM_WRITE,
    ERP_INVENTORY_READ,
    ERP_INVOICE_APPROVE,
    ERP_INVOICE_READ,
    ERP_PURCHASE_APPROVE,
    ERP_REPORTS_READ,
    ERP_SALES_APPROVE,
    PERMISSION_MODULES,
    WILDCARD,
)


class TestCatalog:
    def test_modules_cover_catalog_exactly(self) -> None:
        module_keys = {key for _, _, keys in PERMISSION_MODULES for key in keys}
        assert module_keys == set(CATALOG)

    def test_catalog_has_no_duplicates(self) -> None:
        assert len(CATALOG) == len(set(CATALOG))

    def test_wildcard_is_platform_constant(self) -> None:
        assert WILDCARD == "*"

    def test_reuses_identity_invoice_keys(self) -> None:
        # identity seeds erp.invoice.read / erp.invoice.approve and
        # erp.purchase.approve - the SAME strings, so role grants stay portable.
        assert ERP_INVOICE_READ == "erp.invoice.read"
        assert ERP_INVOICE_APPROVE == "erp.invoice.approve"
        assert ERP_PURCHASE_APPROVE == "erp.purchase.approve"

    def test_inventory_key_is_provisional(self) -> None:
        # Provisional until docs/modules/inventory-warehouse.md lands.
        assert ERP_INVENTORY_READ == "erp.inventory.read"

    def test_hr_and_payroll_keys_are_catalogued(self) -> None:
        # docs/modules/hr-payroll.md §2.2 permission matrix; seeded by 0006.
        for key in (
            "erp.hr.read",
            "erp.hr.write",
            "erp.hr.approve",
            "erp.payroll.read",
            "erp.payroll.write",
            "erp.payroll.approve",
        ):
            assert key in CATALOG

    def test_reuses_identity_crm_and_sales_approve_keys(self) -> None:
        # identity seeds erp.crm.read / erp.crm.write / erp.sales.approve -
        # the SAME strings (services/identity/src/identity/core/permissions.py),
        # so role grants stay portable. Migration 0003 seeds exactly these
        # three (0001 already seeded erp.sales.read/write).
        assert ERP_CRM_READ == "erp.crm.read"
        assert ERP_CRM_WRITE == "erp.crm.write"
        assert ERP_SALES_APPROVE == "erp.sales.approve"

    def test_reporting_key_is_catalogued(self) -> None:
        # RPT-DATA-001: erp.reports.read, seeded by migration 0036; every
        # report definition references it via its permission_key.
        assert ERP_REPORTS_READ == "erp.reports.read"
        assert ERP_REPORTS_READ in CATALOG

    def test_ai_wave2_keys_are_catalogued(self) -> None:
        # SKY-90 wave 2: Sales Coach + Audit Guardian, seeded by migration
        # 0048. Read gates the queue/report surfaces; review gates the
        # accept-dismiss and acknowledge-report decisions.
        for key in (
            "erp.ai.coaching.read",
            "erp.ai.coaching.review",
            "erp.ai.guardian.read",
            "erp.ai.guardian.review",
        ):
            assert key in CATALOG
