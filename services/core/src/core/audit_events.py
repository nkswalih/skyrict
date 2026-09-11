"""Canonical audit event keys for the ERP core domain.

Single source of truth for the free-form ``action`` strings written to the
shared ``audit_logs`` table (append-only, hash-chained - owned by identity's
migration, reused by core). Services must reference these constants instead of
hardcoding strings so the event vocabulary stays greppable and drift-checked
against the catalog grouping below.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------
PRODUCT_CREATED = "inventory.product.created"
PRODUCT_UPDATED = "inventory.product.updated"
PRODUCT_DEACTIVATED = "inventory.product.deactivated"
PRODUCT_REACTIVATED = "inventory.product.reactivated"
WAREHOUSE_CREATED = "inventory.warehouse.created"
WAREHOUSE_UPDATED = "inventory.warehouse.updated"
WAREHOUSE_DEACTIVATED = "inventory.warehouse.deactivated"
WAREHOUSE_REACTIVATED = "inventory.warehouse.reactivated"
STOCK_ADJUSTED = "inventory.stock.adjusted"
STOCK_TRANSFERRED = "inventory.stock.transferred"
STOCK_REORDER_ALERTED = "inventory.stock.reorder_alerted"
SUPPLIER_CREATED = "inventory.supplier.created"
SUPPLIER_UPDATED = "inventory.supplier.updated"
SUPPLIER_DEACTIVATED = "inventory.supplier.deactivated"
SUPPLIER_PERFORMANCE_ADDED = "inventory.supplier.performance_added"

# ---------------------------------------------------------------------------
# CRM & Sales (CRM-BE-002 / docs/modules/sales-crm.md §6)
# ---------------------------------------------------------------------------
CRM_LEAD_CREATED = "crm.lead.created"
CRM_LEAD_UPDATED = "crm.lead.updated"
CRM_LEAD_STATUS_CHANGED = "crm.lead.status_changed"
CRM_OPPORTUNITY_CREATED = "crm.opportunity.created"
CRM_OPPORTUNITY_UPDATED = "crm.opportunity.updated"
CRM_OPPORTUNITY_STAGE_CHANGED = "crm.opportunity.stage_changed"
CRM_OPPORTUNITY_WON = "crm.opportunity.won"
CRM_OPPORTUNITY_LOST = "crm.opportunity.lost"
CRM_CUSTOMER_CREATED = "crm.customer.created"
CRM_CUSTOMER_UPDATED = "crm.customer.updated"
CRM_CUSTOMER_DEACTIVATED = "crm.customer.deactivated"
CRM_CONTACT_CREATED = "crm.contact.created"
CRM_CONTACT_UPDATED = "crm.contact.updated"
CRM_CONTACT_DEACTIVATED = "crm.contact.deactivated"
CRM_ACTIVITY_CREATED = "crm.activity.created"
CRM_ACTIVITY_UPDATED = "crm.activity.updated"
CRM_ACTIVITY_COMPLETED = "crm.activity.completed"
CRM_ACTIVITY_DELETED = "crm.activity.deleted"
CRM_NOTE_CREATED = "crm.note.created"
CRM_NOTE_UPDATED = "crm.note.updated"
CRM_NOTE_DELETED = "crm.note.deleted"
SALES_ORDER_CREATED = "sales.order.created"
SALES_ORDER_UPDATED = "sales.order.updated"
SALES_ORDER_CONFIRMED = "sales.order.confirmed"
SALES_ORDER_FULFILLED = "sales.order.fulfilled"
SALES_ORDER_CANCELLED = "sales.order.cancelled"

# ---------------------------------------------------------------------------
# Documents (SKY-87, docs/modules/documents.md §6)
# ---------------------------------------------------------------------------
DOCUMENT_UPLOADED = "documents.document.uploaded"
DOCUMENT_VERSION_ADDED = "documents.document.version_added"
DOCUMENT_UPDATED = "documents.document.updated"
DOCUMENT_DELETED = "documents.document.deleted"
DOCUMENT_TAGS_CONFIRMED = "documents.document.tags_confirmed"
DOCUMENT_DOWNLOADED = "documents.document.downloaded"

# Every catalogued audit event, in catalog order.
CATALOG: tuple[str, ...] = (
    PRODUCT_CREATED,
    PRODUCT_UPDATED,
    PRODUCT_DEACTIVATED,
    PRODUCT_REACTIVATED,
    WAREHOUSE_CREATED,
    WAREHOUSE_UPDATED,
    WAREHOUSE_DEACTIVATED,
    WAREHOUSE_REACTIVATED,
    STOCK_ADJUSTED,
    STOCK_TRANSFERRED,
    STOCK_REORDER_ALERTED,
    SUPPLIER_CREATED,
    SUPPLIER_UPDATED,
    SUPPLIER_DEACTIVATED,
    SUPPLIER_PERFORMANCE_ADDED,
    CRM_LEAD_CREATED,
    CRM_LEAD_UPDATED,
    CRM_LEAD_STATUS_CHANGED,
    CRM_OPPORTUNITY_CREATED,
    CRM_OPPORTUNITY_UPDATED,
    CRM_OPPORTUNITY_STAGE_CHANGED,
    CRM_OPPORTUNITY_WON,
    CRM_OPPORTUNITY_LOST,
    CRM_CUSTOMER_CREATED,
    CRM_CUSTOMER_UPDATED,
    CRM_CUSTOMER_DEACTIVATED,
    CRM_CONTACT_CREATED,
    CRM_CONTACT_UPDATED,
    CRM_CONTACT_DEACTIVATED,
    CRM_ACTIVITY_CREATED,
    CRM_ACTIVITY_UPDATED,
    CRM_ACTIVITY_COMPLETED,
    CRM_ACTIVITY_DELETED,
    CRM_NOTE_CREATED,
    CRM_NOTE_UPDATED,
    CRM_NOTE_DELETED,
    SALES_ORDER_CREATED,
    SALES_ORDER_UPDATED,
    SALES_ORDER_CONFIRMED,
    SALES_ORDER_FULFILLED,
    SALES_ORDER_CANCELLED,
    DOCUMENT_UPLOADED,
    DOCUMENT_VERSION_ADDED,
    DOCUMENT_UPDATED,
    DOCUMENT_DELETED,
    DOCUMENT_TAGS_CONFIRMED,
    DOCUMENT_DOWNLOADED,
)

ALL_AUDIT_EVENTS: frozenset[str] = frozenset(CATALOG)

# Event module groupings (for catalog endpoints and UI).
# Each entry: (module_key, module_label, (event_keys, ...))
AUDIT_EVENT_MODULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "inventory",
        "Inventory",
        (
            PRODUCT_CREATED,
            PRODUCT_UPDATED,
            PRODUCT_DEACTIVATED,
            PRODUCT_REACTIVATED,
            WAREHOUSE_CREATED,
            WAREHOUSE_UPDATED,
            WAREHOUSE_DEACTIVATED,
            WAREHOUSE_REACTIVATED,
            STOCK_ADJUSTED,
            STOCK_TRANSFERRED,
            STOCK_REORDER_ALERTED,
            SUPPLIER_CREATED,
            SUPPLIER_UPDATED,
            SUPPLIER_DEACTIVATED,
            SUPPLIER_PERFORMANCE_ADDED,
        ),
    ),
    (
        "crm",
        "CRM",
        (
            CRM_LEAD_CREATED,
            CRM_LEAD_UPDATED,
            CRM_LEAD_STATUS_CHANGED,
            CRM_OPPORTUNITY_CREATED,
            CRM_OPPORTUNITY_UPDATED,
            CRM_OPPORTUNITY_STAGE_CHANGED,
            CRM_OPPORTUNITY_WON,
            CRM_OPPORTUNITY_LOST,
            CRM_CUSTOMER_CREATED,
            CRM_CUSTOMER_UPDATED,
            CRM_CUSTOMER_DEACTIVATED,
            CRM_CONTACT_CREATED,
            CRM_CONTACT_UPDATED,
            CRM_CONTACT_DEACTIVATED,
            CRM_ACTIVITY_CREATED,
            CRM_ACTIVITY_UPDATED,
            CRM_ACTIVITY_COMPLETED,
            CRM_ACTIVITY_DELETED,
            CRM_NOTE_CREATED,
            CRM_NOTE_UPDATED,
            CRM_NOTE_DELETED,
        ),
    ),
    (
        "sales",
        "Sales",
        (
            SALES_ORDER_CREATED,
            SALES_ORDER_UPDATED,
            SALES_ORDER_CONFIRMED,
            SALES_ORDER_FULFILLED,
            SALES_ORDER_CANCELLED,
        ),
    ),
    (
        "documents",
        "Documents",
        (
            DOCUMENT_UPLOADED,
            DOCUMENT_VERSION_ADDED,
            DOCUMENT_UPDATED,
            DOCUMENT_DELETED,
            DOCUMENT_TAGS_CONFIRMED,
            DOCUMENT_DOWNLOADED,
        ),
    ),
)


def _assert_catalog_union() -> None:
    """Ensure AUDIT_EVENT_MODULES and CATALOG stay in sync (fail-fast on drift)."""
    module_keys = {key for _, _, keys in AUDIT_EVENT_MODULES for key in keys}
    if module_keys != ALL_AUDIT_EVENTS:
        missing = ALL_AUDIT_EVENTS - module_keys
        orphaned = module_keys - ALL_AUDIT_EVENTS
        msg = "AUDIT_EVENT_MODULES <-> CATALOG mismatch:\n"
        if missing:
            msg += f"  Missing from AUDIT_EVENT_MODULES: {sorted(missing)}\n"
        if orphaned:
            msg += f"  Orphaned in AUDIT_EVENT_MODULES: {sorted(orphaned)}\n"
        raise ValueError(msg)


_assert_catalog_union()

__all__ = [
    "ALL_AUDIT_EVENTS",
    "AUDIT_EVENT_MODULES",
    "CATALOG",
    "CRM_ACTIVITY_COMPLETED",
    "CRM_ACTIVITY_CREATED",
    "CRM_ACTIVITY_DELETED",
    "CRM_ACTIVITY_UPDATED",
    "CRM_CONTACT_CREATED",
    "CRM_CONTACT_DEACTIVATED",
    "CRM_CONTACT_UPDATED",
    "CRM_CUSTOMER_CREATED",
    "CRM_CUSTOMER_DEACTIVATED",
    "CRM_CUSTOMER_UPDATED",
    "CRM_LEAD_CREATED",
    "CRM_LEAD_STATUS_CHANGED",
    "CRM_LEAD_UPDATED",
    "CRM_NOTE_CREATED",
    "CRM_NOTE_DELETED",
    "CRM_NOTE_UPDATED",
    "CRM_OPPORTUNITY_CREATED",
    "CRM_OPPORTUNITY_LOST",
    "CRM_OPPORTUNITY_STAGE_CHANGED",
    "CRM_OPPORTUNITY_UPDATED",
    "CRM_OPPORTUNITY_WON",
    "DOCUMENT_DELETED",
    "DOCUMENT_DOWNLOADED",
    "DOCUMENT_TAGS_CONFIRMED",
    "DOCUMENT_UPDATED",
    "DOCUMENT_UPLOADED",
    "DOCUMENT_VERSION_ADDED",
    "PRODUCT_CREATED",
    "PRODUCT_DEACTIVATED",
    "PRODUCT_REACTIVATED",
    "PRODUCT_UPDATED",
    "SALES_ORDER_CANCELLED",
    "SALES_ORDER_CONFIRMED",
    "SALES_ORDER_CREATED",
    "SALES_ORDER_FULFILLED",
    "SALES_ORDER_UPDATED",
    "STOCK_ADJUSTED",
    "STOCK_REORDER_ALERTED",
    "STOCK_TRANSFERRED",
    "WAREHOUSE_CREATED",
    "WAREHOUSE_DEACTIVATED",
    "WAREHOUSE_REACTIVATED",
    "WAREHOUSE_UPDATED",
]
