"""Event topic constants - single source of truth for Kafka topic names.

Topics follow the ``{domain}.{entity}.{action}`` convention. Phase 1 emits
these via the structlog stub producer (``core.events.producers``); Kafka wiring
later consumes the same constants with no call-site change.
"""

from __future__ import annotations

INVENTORY_STOCK_LEVEL_CHANGED = "inventory.stock.level_changed"
INVENTORY_PRODUCT_UPSERTED = "inventory.product.upserted"
INVENTORY_PRODUCT_REMOVED = "inventory.product.removed"

DOCUMENT_UPLOADED = "documents.document.uploaded"
DOCUMENT_VERSION_ADDED = "documents.document.version_added"
DOCUMENT_UPDATED = "documents.document.updated"
DOCUMENT_DELETED = "documents.document.deleted"
DOCUMENT_TAGS_CONFIRMED = "documents.document.tags_confirmed"
DOCUMENT_DOWNLOADED = "documents.document.downloaded"

__all__ = [
    "DOCUMENT_DELETED",
    "DOCUMENT_DOWNLOADED",
    "DOCUMENT_TAGS_CONFIRMED",
    "DOCUMENT_UPDATED",
    "DOCUMENT_UPLOADED",
    "DOCUMENT_VERSION_ADDED",
    "INVENTORY_PRODUCT_REMOVED",
    "INVENTORY_PRODUCT_UPSERTED",
    "INVENTORY_STOCK_LEVEL_CHANGED",
]
