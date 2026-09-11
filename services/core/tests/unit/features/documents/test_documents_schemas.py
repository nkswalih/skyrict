"""Documents schema tests - API boundary validation (SKY-87).

Covers request input validation (pydantic constraints, MODULE_REFS / OCR_STATUSES
constants), and ``from_entity`` response building for every response model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from core.domain.entities import Document, DocumentVersion
from core.features.documents.schemas import (
    MODULE_REFS,
    OCR_STATUSES,
    DocumentOcrResult,
    DocumentResponse,
    DocumentTagUpdate,
    DocumentUploadIn,
    DocumentVersionResponse,
    ReindexRequest,
    TagConfirmIn,
)

_TENANT = uuid.uuid4()
_DOC_ID = uuid.uuid4()
_VERSION_ID = uuid.uuid4()
_NOW = datetime.now(UTC)


# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------


def _document(**overrides: object) -> Document:
    defaults: dict[str, object] = {
        "tenant_id": _TENANT,
        "filename": "invoice.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1024,
        "checksum_sha256": "abc123",
        "storage_backend": "local",
        "storage_key": "documents/abc/v1",
        "ocr_status": "pending",
        "version_count": 1,
        "id": _DOC_ID,
        "created_at": _NOW,
        "updated_at": _NOW,
    }
    defaults.update(overrides)
    return Document(**defaults)


def _version(**overrides: object) -> DocumentVersion:
    defaults: dict[str, object] = {
        "tenant_id": _TENANT,
        "document_id": _DOC_ID,
        "version_number": 1,
        "filename": "invoice.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1024,
        "checksum_sha256": "abc123",
        "storage_backend": "local",
        "storage_key": "documents/abc/v1",
        "id": _VERSION_ID,
        "created_at": _NOW,
    }
    defaults.update(overrides)
    return DocumentVersion(**defaults)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestModuleRefs:
    def test_general_empty_string(self) -> None:
        assert "" in MODULE_REFS

    def test_all_domain_modules_present(self) -> None:
        for mod in ("inventory", "sales", "crm", "finance", "hr", "payroll"):
            assert mod in MODULE_REFS

    def test_tuple_is_immutable_shape(self) -> None:
        assert len(MODULE_REFS) == 7


class TestOcrStatuses:
    def test_lifecycle_statuses(self) -> None:
        assert OCR_STATUSES == ("pending", "processing", "ready", "failed")


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class TestDocumentUploadIn:
    def test_valid_upload(self) -> None:
        body = DocumentUploadIn(filename="doc.pdf", mime_type="application/pdf")
        assert body.filename == "doc.pdf"
        assert body.tags == []

    def test_filename_min_length_rejects_blank(self) -> None:
        with pytest.raises(PydanticValidationError):
            DocumentUploadIn(filename="", mime_type="application/pdf")

    def test_filename_max_length_rejects_long(self) -> None:
        with pytest.raises(PydanticValidationError):
            DocumentUploadIn(filename="x" * 256, mime_type="application/pdf")

    def test_mime_type_min_length_rejects_blank(self) -> None:
        with pytest.raises(PydanticValidationError):
            DocumentUploadIn(filename="doc.pdf", mime_type="")

    def test_module_ref_defaults_to_general(self) -> None:
        body = DocumentUploadIn(filename="a.txt", mime_type="text/plain")
        assert body.module_ref == ""

    def test_tags_defaults_to_empty(self) -> None:
        body = DocumentUploadIn(filename="a.txt", mime_type="text/plain")
        assert body.tags == []


class TestDocumentTagUpdate:
    def test_partial_update_all_none(self) -> None:
        body = DocumentTagUpdate()
        assert body.module_ref is None
        assert body.tags is None
        assert body.filename is None

    def test_valid_module_ref(self) -> None:
        body = DocumentTagUpdate(module_ref="inventory")
        assert body.module_ref == "inventory"

    def test_filename_min_length_rejects_blank(self) -> None:
        with pytest.raises(PydanticValidationError):
            DocumentTagUpdate(filename="")


class TestDocumentOcrResult:
    def test_valid_ready(self) -> None:
        body = DocumentOcrResult(ocr_status="ready", extracted_text="hello")
        assert body.ocr_status == "ready"
        assert body.ai_tags == []

    def test_valid_processing(self) -> None:
        body = DocumentOcrResult(ocr_status="processing")
        assert body.ocr_status == "processing"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            DocumentOcrResult(ocr_status="pending")

    def test_invalid_status_rejected_by_pattern(self) -> None:
        with pytest.raises(PydanticValidationError):
            DocumentOcrResult(ocr_status="complete")


class TestReindexRequest:
    def test_default_is_failed(self) -> None:
        body = ReindexRequest()
        assert body.ocr_status == "failed"

    def test_ready_accepted(self) -> None:
        body = ReindexRequest(ocr_status="ready")
        assert body.ocr_status == "ready"

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            ReindexRequest(ocr_status="pending")


class TestTagConfirmIn:
    def test_empty_ai_tags(self) -> None:
        body = TagConfirmIn(ai_tags=[])
        assert body.ai_tags == []


# ---------------------------------------------------------------------------
# Response schemas - from_entity
# ---------------------------------------------------------------------------


class TestDocumentVersionResponse:
    def test_from_entity_maps_all_fields(self) -> None:
        ver = _version()
        resp = DocumentVersionResponse.from_entity(ver)
        assert resp.id == _VERSION_ID
        assert resp.document_id == _DOC_ID
        assert resp.version_number == 1
        assert resp.mime_type == "application/pdf"
        assert resp.download_url is None

    def test_from_entity_with_download_url(self) -> None:
        resp = DocumentVersionResponse.from_entity(_version(), download_url="https://x")
        assert resp.download_url == "https://x"


class TestDocumentResponse:
    def test_from_entity_maps_all_fields(self) -> None:
        doc = _document(tags=["a", "b"], ai_tags=["ai1"], tags_confirmed=True)
        resp = DocumentResponse.from_entity(doc)
        assert resp.id == _DOC_ID
        assert resp.tenant_id == _TENANT
        assert resp.tags == ["a", "b"]
        assert resp.ai_tags == ["ai1"]
        assert resp.tags_confirmed is True
        assert resp.version_count == 1
        assert resp.ocr_status == "pending"
        assert resp.latest_version is None

    def test_from_entity_with_latest_version(self) -> None:
        ver_resp = DocumentVersionResponse.from_entity(_version())
        doc_resp = DocumentResponse.from_entity(_document(), latest_version=ver_resp)
        assert doc_resp.latest_version is not None
        assert doc_resp.latest_version.id == _VERSION_ID

    def test_from_entity_none_tags_become_empty_list(self) -> None:
        doc = _document(tags=None, ai_tags=None)
        resp = DocumentResponse.from_entity(doc)
        assert resp.tags == []
        assert resp.ai_tags == []
