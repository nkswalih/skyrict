"""Documents feature boundary ports (SKY-87).

The service depends on the repository port (transaction + persistence),
the storage port (blob I/O), and the audit sink (append-only event log). The
document dispatch hook is a separate module-level function the service calls
after commit - the DB session must be independent of blob storage so a store
failure can never half-commit rows.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

from core.features.documents.storage import DocumentStoragePort

if TYPE_CHECKING:
    import uuid

    from core.domain.entities import Document, DocumentVersion

# Sentinel for "field not provided" in repository updates - distinct from every
# valid value (including None, which is lawful for nullable columns like
# ``ocr_error`` or ``module_ref``).
_UNSET = object()


class DocumentRepositoryPort(ABC):
    """Transaction + query boundary for the documents feature."""

    @abstractmethod
    async def create_document(self, document: Document) -> Document: ...

    @abstractmethod
    async def create_version(self, version: DocumentVersion) -> DocumentVersion: ...

    @abstractmethod
    async def get_document(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Document | None: ...

    @abstractmethod
    async def get_document_by_storage_key(
        self, storage_key: str, tenant_id: uuid.UUID
    ) -> Document | None: ...

    @abstractmethod
    async def get_document_by_checksum(
        self, checksum_sha256: str, tenant_id: uuid.UUID
    ) -> Document | None: ...

    @abstractmethod
    async def list_documents(
        self,
        tenant_id: uuid.UUID,
        *,
        ocr_status: str | None = None,
        module_ref: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        tags: Sequence[str] | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Document]: ...

    @abstractmethod
    async def count_documents(
        self,
        tenant_id: uuid.UUID,
        *,
        ocr_status: str | None = None,
        module_ref: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> int: ...

    @abstractmethod
    async def list_versions(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Sequence[DocumentVersion]: ...

    @abstractmethod
    async def get_latest_version(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> DocumentVersion | None: ...

    @abstractmethod
    async def update_document(
        self,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        filename: str | object = _UNSET,
        module_ref: str | object | None = _UNSET,
        entity_type: str | object | None = _UNSET,
        entity_id: str | object | None = _UNSET,
        tags: list[str] | object = _UNSET,
        ocr_status: str | object = _UNSET,
        ocr_error: str | object | None = _UNSET,
        extracted_text: str | object | None = _UNSET,
        ai_tags: list[str] | object = _UNSET,
        tags_confirmed: bool | object = _UNSET,
        version_count: int | object = _UNSET,
        mime_type: str | object = _UNSET,
        storage_backend: str | object = _UNSET,
        storage_key: str | object = _UNSET,
        checksum_sha256: str | object = _UNSET,
        size_bytes: int | object = _UNSET,
    ) -> Document | None: ...

    @abstractmethod
    async def delete_document(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Document | None: ...

    @abstractmethod
    async def commit(self) -> None: ...


__all__ = ["_UNSET", "DocumentRepositoryPort", "DocumentStoragePort"]
