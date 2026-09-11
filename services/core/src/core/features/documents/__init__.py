"""Documents feature (SKY-87) - platform document spine.

Core owns document metadata, versions, blob storage keys, and OCR lifecycle;
ai-agent owns OCR/tagging/embeddings (see docs/modules/documents.md).
"""

from core.features.documents.ports import (
    DocumentRepositoryPort,
    DocumentStoragePort,
)
from core.features.documents.repository import DocumentsRepository
from core.features.documents.service import DocumentsService

__all__ = [
    "DocumentRepositoryPort",
    "DocumentStoragePort",
    "DocumentsRepository",
    "DocumentsService",
]
