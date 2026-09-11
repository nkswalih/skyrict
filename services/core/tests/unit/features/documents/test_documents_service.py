"""Documents service tests - business rules (SKY-87).

Unit-level: the in-memory fake repo + fake storage + recording audit sink
exercise every DocumentsService path without touching the DB or disk.
Event dispatch is suppressed via monkeypatch (no running event loop).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from core.domain.entities import Document, DocumentVersion
from core.features.audit.service import AuditService
from core.features.documents.ports import _UNSET
from core.features.documents.service import DocumentsService
from skyrict_common.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

pytestmark = pytest.mark.unit

_TENANT = uuid.uuid4()
_USER = uuid.uuid4()
_DOC_ID = uuid.uuid4()
_NOW = datetime.now(UTC)

_CONTENT = b"Hello SKY-87"
_CHECKSUM = hashlib.sha256(_CONTENT).hexdigest()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAuditRepo:
    """Recording audit sink - satisfies AuditRepositoryPort."""

    entries: ClassVar[list[dict[str, Any]]] = []

    async def log(
        self,
        *,
        tenant_id: str,
        user_id: str | None = None,
        action: str,
        target: str,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.entries.append(
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "action": action,
                "target": target,
                "details": details,
            }
        )

    async def add(self, entry: Any) -> Any:
        self.entries.append(entry)
        return entry

    async def list(
        self, tenant_id: uuid.UUID, *, action: str | None = None, limit: int = 100
    ) -> list[Any]:
        return self.entries

    async def get(self, tenant_id: uuid.UUID, entry_id: uuid.UUID) -> Any:
        return None


class FakeRepo:
    """In-memory document + version repository (satisfies DocumentRepositoryPort)."""

    def __init__(self) -> None:
        self.documents: dict[uuid.UUID, Document] = {}
        self.versions: dict[tuple[uuid.UUID, uuid.UUID], list[DocumentVersion]] = {}
        self._by_checksum: dict[str, Document] = {}
        self._by_storage_key: dict[str, Document] = {}
        self.committed = 0

    async def create_document(self, document: Document) -> Document:
        doc_id = uuid.uuid4()
        data = {k: v for k, v in document.__dict__.items() if k != "id"}
        doc = Document(**data, id=doc_id)
        self.documents[doc_id] = doc
        self._by_checksum[doc.checksum_sha256] = doc
        self._by_storage_key[doc.storage_key] = doc
        return doc

    async def create_version(self, version: DocumentVersion) -> DocumentVersion:
        ver_id = uuid.uuid4()
        data = {k: v for k, v in version.__dict__.items() if k != "id"}
        ver = DocumentVersion(**data, id=ver_id)
        self.versions.setdefault(version.document_id, []).append(ver)
        return ver

    async def get_document(self, document_id: uuid.UUID, tenant_id: uuid.UUID) -> Document | None:
        return self.documents.get(document_id)

    async def get_document_by_storage_key(
        self, storage_key: str, tenant_id: uuid.UUID
    ) -> Document | None:
        return self._by_storage_key.get(storage_key)

    async def get_document_by_checksum(
        self, checksum_sha256: str, tenant_id: uuid.UUID
    ) -> Document | None:
        return self._by_checksum.get(checksum_sha256)

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
    ) -> Sequence[Document]:
        docs = list(self.documents.values())
        if ocr_status is not None:
            docs = [d for d in docs if d.ocr_status == ocr_status]
        if module_ref is not None:
            docs = [d for d in docs if d.module_ref == module_ref]
        return docs[offset : offset + limit]

    async def count_documents(
        self,
        tenant_id: uuid.UUID,
        *,
        ocr_status: str | None = None,
        module_ref: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> int:
        docs = list(self.documents.values())
        if ocr_status is not None:
            docs = [d for d in docs if d.ocr_status == ocr_status]
        return len(docs)

    async def list_versions(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Sequence[DocumentVersion]:
        return self.versions.get(document_id, [])

    async def get_latest_version(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> DocumentVersion | None:
        vers = self.versions.get(document_id, [])
        return max(vers, key=lambda v: v.version_number) if vers else None

    async def update_document(
        self,
        document_id: uuid.UUID,
        tenant_id: uuid.UUID,
        **kwargs: Any,
    ) -> Document | None:
        doc = self.documents.get(document_id)
        if doc is None:
            return None
        for k, v in kwargs.items():
            if v is _UNSET:
                continue
            object.__setattr__(doc, k, v)
        return doc

    async def delete_document(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Document | None:
        doc = self.documents.pop(document_id, None)
        self.versions.pop(document_id, None)
        if doc is not None:
            self._by_checksum.pop(doc.checksum_sha256, None)
            self._by_storage_key.pop(doc.storage_key, None)
        return doc

    async def commit(self) -> None:
        self.committed += 1


class FakeStorage:
    """In-memory storage (satisfies DocumentStoragePort)."""

    name = "local"

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}
        self.deleted: list[str] = []

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        self.blobs[key] = data
        return key

    async def get(self, key: str) -> bytes | None:
        return self.blobs.get(key)

    async def delete(self, key: str) -> None:
        self.blobs.pop(key, None)
        self.deleted.append(key)

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        return f"https://fake/{key}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service(
    *, repo: FakeRepo | None = None, storage: FakeStorage | None = None
) -> tuple[DocumentsService, FakeRepo, FakeStorage]:
    r = repo or FakeRepo()
    s = storage or FakeStorage()
    audit_repo = FakeAuditRepo()
    audit_svc = AuditService(audit_repo)
    svc = DocumentsService(
        documents_repo=r, storage=s, audit_service=audit_svc, max_upload_bytes=1024
    )
    return svc, r, s


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestUploadDocument:
    async def test_upload_creates_doc_and_version(self) -> None:
        svc, repo, storage = _service()
        doc, ver, created = await svc.upload_document(
            _TENANT,
            filename="doc.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
            created_by=_USER,
        )
        assert created is True
        assert doc.id is not None
        assert doc.filename == "doc.pdf"
        assert doc.ocr_status == "pending"
        assert ver.version_number == 1
        assert repo.committed >= 1
        assert len(storage.blobs) == 1

    async def test_upload_dedupe_returns_existing(self) -> None:
        svc, repo, storage = _service()
        await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        doc2, _ver2, created2 = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        assert created2 is False
        assert doc2.id == repo.documents[next(iter(repo.documents.keys()))].id
        assert len(storage.blobs) == 1  # no second blob written

    async def test_upload_empty_bytes_rejected(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(ValidationError, match="empty"):
            await svc.upload_document(
                _TENANT, filename="a.pdf", mime_type="application/pdf", file_bytes=b""
            )

    async def test_upload_oversize_rejected(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(ValidationError, match="maximum"):
            await svc.upload_document(
                _TENANT, filename="a.pdf", mime_type="application/pdf", file_bytes=b"x" * 1025
            )

    async def test_upload_invalid_module_ref_rejected(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(ValidationError, match="module_ref"):
            await svc.upload_document(
                _TENANT,
                filename="a.pdf",
                mime_type="application/pdf",
                file_bytes=_CONTENT,
                module_ref="nonexistent",
            )

    async def test_upload_stores_file_bytes(self) -> None:
        svc, _, storage = _service()
        await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        stored = next(iter(storage.blobs.values()))
        assert stored == _CONTENT

    async def test_upload_records_created_by(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
            created_by=_USER,
        )
        assert doc.created_by == _USER


class TestAddVersion:
    async def _make_doc(self, svc: DocumentsService) -> uuid.UUID:
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        assert doc.id is not None
        return doc.id

    async def test_add_version_bumps_count(self) -> None:
        svc, _repo, storage = _service()
        doc_id = await self._make_doc(svc)
        new_content = b"Version 2 content"
        doc, ver = await svc.add_version(
            _TENANT,
            doc_id,
            filename="a_v2.pdf",
            mime_type="application/pdf",
            file_bytes=new_content,
            created_by=_USER,
        )
        assert doc.version_count == 2
        assert ver.version_number == 2
        assert len(storage.blobs) == 2

    async def test_add_version_same_content_idempotent(self) -> None:
        svc, _, _ = _service()
        doc_id = await self._make_doc(svc)
        _doc, ver = await svc.add_version(
            _TENANT,
            doc_id,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        assert ver.version_number == 1  # no new version created

    async def test_add_version_missing_doc_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.add_version(
                _TENANT,
                uuid.uuid4(),
                filename="x.pdf",
                mime_type="application/pdf",
                file_bytes=b"new",
            )

    async def test_add_version_empty_bytes_rejected(self) -> None:
        svc, _, _ = _service()
        doc_id = await self._make_doc(svc)
        with pytest.raises(ValidationError, match="empty"):
            await svc.add_version(
                _TENANT,
                doc_id,
                filename="x.pdf",
                mime_type="application/pdf",
                file_bytes=b"",
            )

    async def test_add_version_resets_ocr_status(self) -> None:
        svc, _repo, _ = _service()
        doc_id = await self._make_doc(svc)
        # Simulate OCR completed
        await svc.apply_ocr_result(
            _TENANT,
            doc_id,
            ocr_status="ready",
            extracted_text="ocr",
            ai_tags=["tag1"],
        )
        doc, _ = await svc.add_version(
            _TENANT,
            doc_id,
            filename="b.pdf",
            mime_type="application/pdf",
            file_bytes=b"Version 2",
        )
        assert doc.ocr_status == "pending"
        assert doc.tags_confirmed is False


class TestGetDocument:
    async def test_get_existing(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        fetched = await svc.get_document(_TENANT, doc.id)
        assert fetched.id == doc.id

    async def test_get_missing_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.get_document(_TENANT, uuid.uuid4())


class TestUpdateDocumentMeta:
    async def test_update_tags(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        updated = await svc.update_document_meta(
            _TENANT,
            doc.id,
            tags=["new-tag"],
        )
        assert updated.tags == ["new-tag"]

    async def test_update_module_ref(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        updated = await svc.update_document_meta(
            _TENANT,
            doc.id,
            module_ref="finance",
        )
        assert updated.module_ref == "finance"

    async def test_update_invalid_module_ref_rejected(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        with pytest.raises(ValidationError, match="module_ref"):
            await svc.update_document_meta(_TENANT, doc.id, module_ref="bogus")

    async def test_update_tags_too_many_rejected(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        with pytest.raises(ValidationError, match="200"):
            await svc.update_document_meta(_TENANT, doc.id, tags=[f"t{i}" for i in range(201)])

    async def test_update_missing_doc_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.update_document_meta(_TENANT, uuid.uuid4(), tags=["a"])

    async def test_update_filename_blank_rejected(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        with pytest.raises(ValidationError, match="blank"):
            await svc.update_document_meta(_TENANT, doc.id, filename="   ")


class TestConfirmTags:
    async def test_confirm_pins_ai_tags(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        updated = await svc.confirm_tags(_TENANT, doc.id, ["tag1", "tag2"])
        assert updated.tags == ["tag1", "tag2"]
        assert updated.ocr_status == "ready"

    async def test_confirm_too_many_tags_rejected(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        with pytest.raises(ValidationError, match="200"):
            await svc.confirm_tags(_TENANT, doc.id, [f"t{i}" for i in range(201)])

    async def test_confirm_missing_doc_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.confirm_tags(_TENANT, uuid.uuid4(), [])


class TestApplyOcrResult:
    async def test_apply_ready_sets_text_and_tags(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        updated = await svc.apply_ocr_result(
            _TENANT,
            doc.id,
            ocr_status="ready",
            extracted_text="text",
            ai_tags=["auto1"],
        )
        assert updated.ocr_status == "ready"
        assert updated.extracted_text == "text"
        assert updated.ai_tags == ["auto1"]

    async def test_apply_processing_no_text(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        updated = await svc.apply_ocr_result(_TENANT, doc.id, ocr_status="processing")
        assert updated.ocr_status == "processing"
        assert updated.extracted_text is None

    async def test_apply_failed_sets_error(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        updated = await svc.apply_ocr_result(
            _TENANT,
            doc.id,
            ocr_status="failed",
            error_message="OCR error",
        )
        assert updated.ocr_status == "failed"
        assert updated.ocr_error == "OCR error"

    async def test_apply_invalid_status_rejected(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        with pytest.raises(ValidationError, match="invalid ocr_status"):
            await svc.apply_ocr_result(_TENANT, doc.id, ocr_status="pending")

    async def test_apply_missing_doc_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.apply_ocr_result(_TENANT, uuid.uuid4(), ocr_status="ready")


class TestReindex:
    async def test_reindex_single(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        await svc.apply_ocr_result(_TENANT, doc.id, ocr_status="failed")
        result = await svc.reindex(_TENANT, doc.id)
        assert result.ocr_status == "pending"

    async def test_reindex_many(self) -> None:
        svc, _repo, _ = _service()
        ids: list[uuid.UUID] = []
        for i in range(3):
            content = f"content-{i}".encode()
            doc, _, _ = await svc.upload_document(
                _TENANT,
                filename=f"a{i}.pdf",
                mime_type="application/pdf",
                file_bytes=content,
            )
            ids.append(doc.id)
            await svc.apply_ocr_result(_TENANT, doc.id, ocr_status="failed")
        enqueued = await svc.reindex_many(_TENANT, ocr_status="failed")
        assert enqueued == 3

    async def test_reindex_invalid_status_rejected(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(ValidationError, match="reindex only"):
            await svc.reindex_many(_TENANT, ocr_status="pending")

    async def test_reindex_missing_doc_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.reindex(_TENANT, uuid.uuid4())


class TestDeleteDocument:
    async def test_delete_removes_blob_and_row(self) -> None:
        svc, repo, storage = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        removed = await svc.delete_document(_TENANT, doc.id)
        assert removed.id == doc.id
        assert doc.id not in repo.documents
        assert len(storage.blobs) == 0
        assert len(storage.deleted) == 1

    async def test_delete_missing_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.delete_document(_TENANT, uuid.uuid4())


class TestGetDocumentBytes:
    async def test_get_bytes_returns_content(self) -> None:
        svc, _, _storage = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        fetched_doc, stream = await svc.get_document_bytes(_TENANT, doc.id)
        assert stream == _CONTENT
        assert fetched_doc.id == doc.id

    async def test_get_bytes_missing_blob_raises(self) -> None:
        svc, _, storage = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        storage.blobs.clear()
        with pytest.raises(NotFoundError, match="missing from storage"):
            await svc.get_document_bytes(_TENANT, doc.id)


class TestRecordDownload:
    async def test_record_download_audits(self) -> None:
        svc, _, _ = _service()
        doc, _, _ = await svc.upload_document(
            _TENANT,
            filename="a.pdf",
            mime_type="application/pdf",
            file_bytes=_CONTENT,
        )
        result = await svc.record_download(_TENANT, doc.id)
        assert result.id == doc.id

    async def test_record_download_missing_raises(self) -> None:
        svc, _, _ = _service()
        with pytest.raises(NotFoundError):
            await svc.record_download(_TENANT, uuid.uuid4())
