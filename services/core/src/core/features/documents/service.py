"""Documents service - business rules for the SKY-87 document spine.

Core is the document authority: metadata, version rows, storage keys, and the
OCR status lifecycle (``pending -> processing -> ready | failed``). The byte
stream lives in the configured backend (local dir or S3) and is NEVER round-
tripped through the relational store; the DB owns keys + checksums only.

Rules (docs/modules/documents.md §4-§5):
  * Blob write comes FIRST (outside the DB transaction), DB row commit SECOND -
    a store failure must never half-commit rows, and the store key is required
    before any row is valid.
  * Exact-content dedupe: a repeat of an already-stored ``checksum_sha256``
    within the same tenant short-circuits to the existing document (200), no
    blob write, no new version.
  * Every version bumps ``version_count`` in ONE transaction with the new
    ``erp_document_versions`` row (atomic, or neither).
  * Metadata updates (link/tags/filename) never touch version history.
  * ``confirm_tags`` pins AI-tags only; it never re-runs OCR.
  * Delete = storage delete + version cascade; the row goes away with it.

Like inventory, every mutating method commits ONCE, then audits and emits. The
ocr dispatch (fire-and-forget POST to ai-agent) happens AFTER commit and never
blocks or raises into the request.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

from core.audit_events import (
    DOCUMENT_DELETED,
    DOCUMENT_DOWNLOADED,
    DOCUMENT_TAGS_CONFIRMED,
    DOCUMENT_UPDATED,
    DOCUMENT_UPLOADED,
    DOCUMENT_VERSION_ADDED,
)
from core.core.config import settings
from core.core.tenant_context import TenantContext
from core.domain.entities import Document, DocumentVersion
from core.features.audit.service import AuditService
from core.features.documents.events import (
    publish_document_deleted,
    publish_document_tags_confirmed,
    publish_document_uploaded,
    publish_document_version_added,
    reindex_failed,
)
from core.features.documents.ports import _UNSET, DocumentRepositoryPort, DocumentStoragePort
from core.features.documents.schemas import MODULE_REFS, OCR_STATUSES
from skyrict_common.exceptions import NotFoundError, ValidationError

logger = logging.getLogger(__name__)


def _as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    return uuid.UUID(value) if isinstance(value, str) else value


class DocumentsService:
    """Implements the document CLI + REST surface for SKY-87."""

    def __init__(
        self,
        documents_repo: DocumentRepositoryPort,
        storage: DocumentStoragePort,
        audit_service: AuditService,
        *,
        max_upload_bytes: int | None = None,
    ) -> None:
        self.documents_repo = documents_repo
        self.storage = storage
        self.audit_service = audit_service
        self.max_upload_bytes = (
            settings.DOCS_MAX_UPLOAD_BYTES if max_upload_bytes is None else max_upload_bytes
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    async def _audit(
        self,
        *,
        tenant_id: str | uuid.UUID,
        action: str,
        target: str,
        details: dict[str, object] | None = None,
    ) -> None:
        await self.audit_service.log(
            action=action,
            target=target,
            user_id=TenantContext.get_user_id(),
            tenant_id=str(tenant_id),
            details=details,
        )

    @staticmethod
    def _build_storage_key(tenant_id: uuid.UUID, version: int) -> str:
        return f"documents/{tenant_id}/{uuid.uuid4().hex}/v{version}"

    def _validate_link(self, module_ref: str) -> None:
        if module_ref not in MODULE_REFS:
            raise ValidationError(
                "module_ref must be one of: " + ", ".join(MODULE_REFS[1:] or ["(general)"])
            )

    @staticmethod
    def _sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    async def _emit_after_commit(self, *, tenant_id: uuid.UUID, document: Document) -> None:
        """Audit + publish post-commit (never part of the DB transaction)."""
        await self._audit(
            tenant_id=tenant_id,
            action=DOCUMENT_UPLOADED,
            target=str(document.id),
            details={"filename": document.filename, "size_bytes": document.size_bytes},
        )
        publish_document_uploaded(tenant_id=str(tenant_id), document_id=str(document.id))

    # ------------------------------------------------------------------
    # Upload / version lifecycle
    # ------------------------------------------------------------------

    async def upload_document(
        self,
        tenant_id: str | uuid.UUID,
        *,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
        module_ref: str = "",
        entity_type: str | None = None,
        entity_id: str | None = None,
        tags: Sequence[str] | None = None,
        created_by: str | uuid.UUID | None = None,
    ) -> tuple[Document, DocumentVersion, bool]:
        """Store a new document + version 1; ``created=False`` means a dedupe hit.

        The blob is written to the storage backend BEFORE any DB work, so a
        store failure leaves zero rows behind (no phantom document). After the
        single commit, OCR dispatch + audit run fire-and-forget.
        """
        tid = _as_uuid(tenant_id)
        actor = _as_uuid(created_by) if created_by else None
        if filename is None or not str(filename).strip():
            raise ValidationError("filename is required")
        if len(file_bytes) == 0:
            raise ValidationError("Cannot upload an empty file")
        if len(file_bytes) > self.max_upload_bytes:
            raise ValidationError(
                f"file exceeds maximum upload size of {self.max_upload_bytes} bytes"
            )
        self._validate_link(module_ref)

        checksum = self._sha256(file_bytes)
        existing = await self.documents_repo.get_document_by_checksum(checksum, tid)
        if existing is not None:
            assert existing.id is not None
            logger.info(
                "documents.upload.dedupe tenant_doc=%s",
                str(existing.id),
            )
            latest = await self.get_latest_version(tid, existing.id)
            assert latest is not None
            return existing, latest, False

        storage_key = self._build_storage_key(tid, version=1)
        await self.storage.put(storage_key, file_bytes, content_type=mime_type)

        now = self._utcnow()
        document = Document(
            tenant_id=tid,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            checksum_sha256=checksum,
            storage_backend=self.storage.name,
            storage_key=storage_key,
            module_ref=module_ref or None,
            entity_type=entity_type,
            entity_id=entity_id,
            tags=list(tags or []),
            ocr_status="pending",
            ai_tags=[],
            tags_confirmed=False,
            version_count=1,
            created_by=actor,
            created_at=now,
            updated_at=now,
        )
        saved = await self.documents_repo.create_document(document)
        assert saved.id is not None
        version = await self.documents_repo.create_version(
            DocumentVersion(
                tenant_id=tid,
                document_id=saved.id,
                version_number=1,
                filename=filename,
                mime_type=mime_type,
                size_bytes=len(file_bytes),
                checksum_sha256=checksum,
                storage_backend=self.storage.name,
                storage_key=storage_key,
                created_by=actor,
                created_at=now,
            )
        )
        await self.documents_repo.commit()
        await self._emit_after_commit(tenant_id=tid, document=saved)
        logger.info(
            "documents.upload.created doc=%s version=1",
            str(saved.id),
        )
        return saved, version, True

    async def add_version(
        self,
        tenant_id: str | uuid.UUID,
        document_id: uuid.UUID,
        *,
        filename: str,
        mime_type: str,
        file_bytes: bytes,
        created_by: str | uuid.UUID | None = None,
    ) -> tuple[Document, DocumentVersion]:
        """Append a new immutable version on top of an existing document."""
        tid = _as_uuid(tenant_id)
        actor = _as_uuid(created_by) if created_by else None
        if len(file_bytes) == 0:
            raise ValidationError("Cannot upload an empty file")
        if len(file_bytes) > self.max_upload_bytes:
            raise ValidationError(
                f"file exceeds maximum upload size of {self.max_upload_bytes} bytes"
            )
        document = await self.documents_repo.get_document(document_id, tid)
        if document is None:
            raise NotFoundError("Document not found")

        checksum = self._sha256(file_bytes)
        if document.checksum_sha256 == checksum and document.version_count == 1:
            latest = await self.get_latest_version(tid, document_id)
            assert latest is not None
            return document, latest

        next_version = document.version_count + 1
        storage_key = self._build_storage_key(tid, version=next_version)
        await self.storage.put(storage_key, file_bytes, content_type=mime_type)

        now = self._utcnow()
        updated = await self.documents_repo.update_document(
            document_id,
            tid,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            checksum_sha256=checksum,
            storage_key=storage_key,
            version_count=next_version,
            ocr_status="pending",
            ocr_error=None,
            extracted_text=None,
            ai_tags=[],
            tags_confirmed=False,
        )
        assert updated is not None, "update_document returned None on a known row"
        version = await self.documents_repo.create_version(
            DocumentVersion(
                tenant_id=tid,
                document_id=document_id,
                version_number=next_version,
                filename=filename,
                mime_type=mime_type,
                size_bytes=len(file_bytes),
                checksum_sha256=checksum,
                storage_backend=self.storage.name,
                storage_key=storage_key,
                created_by=actor,
                created_at=now,
            )
        )
        await self.documents_repo.commit()
        await self._audit(
            tenant_id=tid,
            action=DOCUMENT_VERSION_ADDED,
            target=str(document_id),
            details={"version": next_version, "size_bytes": len(file_bytes)},
        )
        publish_document_version_added(tenant_id=str(tid), document_id=str(document_id))
        return updated, version

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_document(self, tenant_id: str | uuid.UUID, document_id: uuid.UUID) -> Document:
        tid = _as_uuid(tenant_id)
        document = await self.documents_repo.get_document(document_id, tid)
        if document is None:
            raise NotFoundError("Document not found")
        return document

    async def get_latest_version(
        self, tenant_id: str | uuid.UUID, document_id: uuid.UUID
    ) -> DocumentVersion | None:
        tid = _as_uuid(tenant_id)
        return await self.documents_repo.get_latest_version(document_id, tid)

    async def list_versions(
        self, tenant_id: str | uuid.UUID, document_id: uuid.UUID
    ) -> Sequence[DocumentVersion]:
        tid = _as_uuid(tenant_id)
        await self.get_document(tid, document_id)
        return await self.documents_repo.list_versions(document_id, tid)

    async def list_documents(
        self,
        tenant_id: str | uuid.UUID,
        *,
        ocr_status: str | None = None,
        module_ref: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        tags: Sequence[str] | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[Document]:
        tid = _as_uuid(tenant_id)
        if ocr_status is not None and ocr_status not in OCR_STATUSES:
            raise ValidationError(f"ocr_status must be one of: {', '.join(OCR_STATUSES)}")
        return await self.documents_repo.list_documents(
            tid,
            ocr_status=ocr_status,
            module_ref=module_ref,
            entity_type=entity_type,
            entity_id=entity_id,
            tags=tags,
            offset=offset,
            limit=limit,
        )

    async def count_documents(
        self,
        tenant_id: str | uuid.UUID,
        *,
        ocr_status: str | None = None,
        module_ref: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> int:
        tid = _as_uuid(tenant_id)
        return await self.documents_repo.count_documents(
            tid,
            ocr_status=ocr_status,
            module_ref=module_ref,
            entity_type=entity_type,
            entity_id=entity_id,
            tags=tags,
        )

    async def get_document_bytes(
        self, tenant_id: str | uuid.UUID, document_id: uuid.UUID
    ) -> tuple[Document, bytes]:
        """Load a document's current byte stream from the storage backend."""
        tid = _as_uuid(tenant_id)
        document = await self.get_document(tid, document_id)
        stream = await self.storage.get(document.storage_key)
        if stream is None:
            raise NotFoundError("Document bytes missing from storage backend")
        return document, stream

    async def record_download(self, tenant_id: str | uuid.UUID, document_id: uuid.UUID) -> Document:
        """Audit a download (fired before streaming so it is always on record)."""
        tid = _as_uuid(tenant_id)
        document = await self.get_document(tid, document_id)
        await self._audit(
            tenant_id=tid,
            action=DOCUMENT_DOWNLOADED,
            target=str(document_id),
            details={"filename": document.filename},
        )
        return document

    # ------------------------------------------------------------------
    # Metadata mutation
    # ------------------------------------------------------------------

    async def update_document_meta(
        self,
        tenant_id: str | uuid.UUID,
        document_id: uuid.UUID,
        *,
        filename: str | object = _UNSET,
        module_ref: str | object | None = _UNSET,
        entity_type: str | object | None = _UNSET,
        entity_id: str | object | None = _UNSET,
        tags: Sequence[str] | object = _UNSET,
    ) -> Document:
        """Patch link + display metadata; NEVER touches versions or OCR state."""
        tid = _as_uuid(tenant_id)
        if tags is not _UNSET and tags is not None:
            tag_list = cast("Sequence[str]", tags)
            if len(list(tag_list)) > 200:
                raise ValidationError("tags limited to 200 entries")
            tags = list(tag_list)
        if isinstance(module_ref, str):
            self._validate_link(module_ref)
        if filename is not _UNSET and filename is not None and not str(filename).strip():
            raise ValidationError("filename must not be blank")
        updated = await self.documents_repo.update_document(
            document_id,
            tid,
            filename=filename if filename is not _UNSET else _UNSET,
            module_ref=(module_ref if module_ref is not _UNSET else _UNSET),
            entity_type=entity_type,
            entity_id=entity_id,
            tags=tags,
        )
        if updated is None:
            raise NotFoundError("Document not found")
        await self.documents_repo.commit()
        await self._audit(
            tenant_id=tid,
            action=DOCUMENT_UPDATED,
            target=str(document_id),
            details={
                "filename": updated.filename,
                "module_ref": updated.module_ref or "",
                "tags": list(updated.tags or []),
            },
        )
        return updated

    async def confirm_tags(
        self,
        tenant_id: str | uuid.UUID,
        document_id: uuid.UUID,
        ai_tags: Sequence[str],
    ) -> Document:
        """Pin the AI-suggested tags as authoritative (idempotent)."""
        tid = _as_uuid(tenant_id)
        document = await self.documents_repo.get_document(document_id, tid)
        if document is None:
            raise NotFoundError("Document not found")
        confirmed = list(ai_tags or [])
        if len(confirmed) > 200:
            raise ValidationError("tags limited to 200 entries")
        updated = await self.documents_repo.update_document(
            document_id,
            tid,
            tags=confirmed,
            ocr_status="ready",
        )
        assert updated is not None
        await self.documents_repo.commit()
        await self._audit(
            tenant_id=tid,
            action=DOCUMENT_TAGS_CONFIRMED,
            target=str(document_id),
            details={"tags_count": len(confirmed)},
        )
        publish_document_tags_confirmed(
            tenant_id=str(tid), document_id=str(document_id), tags=confirmed
        )
        return updated

    # ------------------------------------------------------------------
    # ai-agent OCR callback (m2m)
    # ------------------------------------------------------------------

    async def apply_ocr_result(
        self,
        tenant_id: str | uuid.UUID,
        document_id: uuid.UUID,
        *,
        ocr_status: str,
        extracted_text: str | None = None,
        ai_tags: Sequence[str] | None = None,
        error_message: str | None = None,
    ) -> Document:
        """Consume an OCR result from ai-agent; only accepts processing/ready/failed."""
        tid = _as_uuid(tenant_id)
        document = await self.documents_repo.get_document(document_id, tid)
        if document is None:
            raise NotFoundError("Document not found")
        if ocr_status not in ("processing", "ready", "failed"):
            raise ValidationError(f"invalid ocr_status: {ocr_status}")
        ready = ocr_status == "ready"
        updated = await self.documents_repo.update_document(
            document_id,
            tid,
            ocr_status=ocr_status,
            ocr_error=error_message if ocr_status == "failed" else None,
            extracted_text=extracted_text if ready else None,
            ai_tags=list(ai_tags or []) if ready else _UNSET,
        )
        assert updated is not None
        await self.documents_repo.commit()
        return updated

    async def reindex(self, tenant_id: str | uuid.UUID, document_id: uuid.UUID) -> Document:
        """Re-enqueue one failed/ready document for OCR (operator action)."""
        tid = _as_uuid(tenant_id)
        document = await self.documents_repo.get_document(document_id, tid)
        if document is None:
            raise NotFoundError("Document not found")
        await self.documents_repo.update_document(
            document_id,
            tid,
            ocr_status="pending",
            ocr_error=None,
        )
        await self.documents_repo.commit()
        reindex_failed(tenant_id=str(tid), document_id=str(document_id))
        return document

    async def reindex_many(
        self, tenant_id: str | uuid.UUID, *, ocr_status: str, limit: int = 100
    ) -> int:
        """Re-enqueue up to ``limit`` documents in ``ocr_status`` (admin reindex)."""
        tid = _as_uuid(tenant_id)
        if ocr_status not in ("failed", "ready"):
            raise ValidationError("reindex only accepts ocr_status in ('failed', 'ready')")
        documents = await self.documents_repo.list_documents(
            tid, ocr_status=ocr_status, offset=0, limit=limit
        )
        enqueued = 0
        for document in documents:
            assert document.id is not None
            await self.documents_repo.update_document(
                document.id, tid, ocr_status="pending", ocr_error=None
            )
            enqueued += 1
        await self.documents_repo.commit()
        for document in documents:
            assert document.id is not None
            reindex_failed(tenant_id=str(tid), document_id=str(document.id))
        return enqueued

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete_document(self, tenant_id: str | uuid.UUID, document_id: uuid.UUID) -> Document:
        """Hard-delete a document: storage blob + row + version cascade."""
        tid = _as_uuid(tenant_id)
        document = await self.documents_repo.get_document(document_id, tid)
        if document is None:
            raise NotFoundError("Document not found")
        await self.storage.delete(document.storage_key)
        removed = await self.documents_repo.delete_document(document_id, tid)
        assert removed is not None
        await self.documents_repo.commit()
        await self._audit(
            tenant_id=tid,
            action=DOCUMENT_DELETED,
            target=str(document_id),
            details={"filename": document.filename},
        )
        publish_document_deleted(tenant_id=str(tid), document_id=str(document_id))
        return removed

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(UTC)


__all__ = ["_UNSET", "DocumentsService"]
