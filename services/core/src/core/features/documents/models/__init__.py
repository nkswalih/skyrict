"""ERP document ORM models - registered on ``Base.metadata`` by alembic/env.py.

Feature models are NOT re-exported from ``core.models``: importing that package
from ``core.features`` would violate the import-linter layering contract, so
the migration runner imports these models directly (same convention as
``core.features.inventory.models``).
"""

from core.features.documents.models.document import ErpDocumentModel
from core.features.documents.models.document_version import ErpDocumentVersionModel

__all__ = [
    "ErpDocumentModel",
    "ErpDocumentVersionModel",
]
