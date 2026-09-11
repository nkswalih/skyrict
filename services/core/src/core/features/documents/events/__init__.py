"""Documents feature event emission (producers)."""

from core.features.documents.events.dispatch import (
    publish_document_deleted,
    publish_document_downloaded,
    publish_document_tags_confirmed,
    publish_document_uploaded,
    publish_document_version_added,
    reindex_failed,
)

__all__ = [
    "publish_document_deleted",
    "publish_document_downloaded",
    "publish_document_tags_confirmed",
    "publish_document_uploaded",
    "publish_document_version_added",
    "reindex_failed",
]
