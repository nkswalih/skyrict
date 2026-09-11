"""Documents HTTP router - thin marshalling, business rules live in the service.

Endpoints follow docs/modules/documents.md. Every route requires a valid access
JWT + tenant context (via shared deps) and a module-level permission dependency
resolved from DB grants at request time. Responses are wrapped in
``ResponseEnvelope``; lists use offset/limit with ``PaginationMeta``.

Permissions (spec §7.3): reads need ``erp.documents.read``; uploads/version
adds/metadata updates/tag confirmation need ``erp.documents.write``; hard
deletes need ``erp.documents.delete``. Documents that are entity-linked
(``module_ref`` set) ALSO need the owning module's read key (``inventory`` →
``erp.inventory.read``, etc. - see ``require_entity_linked_read``), enforced
after the document row is resolved so the rule never blocks ``general`` docs.
The OCR callback accepts ai-agent's m2m ingest secret instead of a user JWT.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from core.api.deps import (
    get_documents_service,
    get_entity_link_guard,
    get_tenant_context,
    require_ingest_m2m_or_permission,
    require_permission,
)
from core.core.permissions import (
    ERP_DOCUMENTS_DELETE,
    ERP_DOCUMENTS_READ,
    ERP_DOCUMENTS_WRITE,
)
from core.features.documents.ports import _UNSET
from core.features.documents.schemas import (
    DocumentOcrResult,
    DocumentResponse,
    DocumentTagUpdate,
    DocumentVersionResponse,
    ReindexRequest,
    TagConfirmIn,
)
from skyrict_common.pagination import PaginationParams
from skyrict_common.schemas import ListResponse, PaginationMeta, ResponseEnvelope

if TYPE_CHECKING:
    from core.features.documents.service import DocumentsService

router = APIRouter(prefix="/documents", tags=["documents"])

_require_documents_read = require_permission(ERP_DOCUMENTS_READ)
_require_documents_write = require_permission(ERP_DOCUMENTS_WRITE)
_require_documents_delete = require_permission(ERP_DOCUMENTS_DELETE)
# OCR callback: ai-agent pulls with the ingest secret OR a user holds write.
_require_ocr_callback = require_ingest_m2m_or_permission(ERP_DOCUMENTS_WRITE)


# ---------------------------------------------------------------------------
# List / reindex
# ---------------------------------------------------------------------------


@router.get("", response_model=ListResponse[DocumentResponse])
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ocr_status: str | None = Query(default=None),
    module_ref: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    tags: str | None = Query(default=None),
    _: dict[str, Any] = Depends(_require_documents_read),
    tenant_id: str = Depends(get_tenant_context),
    service: DocumentsService = Depends(get_documents_service),
) -> ListResponse[DocumentResponse]:
    """List documents with optional filters (tags as comma-separated string)."""
    params = PaginationParams.create(page, page_size)
    tag_list = [t for t in (tags or "").split(",") if t] if tags else None
    documents = await service.list_documents(
        tenant_id,
        ocr_status=ocr_status,
        module_ref=module_ref,
        entity_type=entity_type,
        entity_id=entity_id,
        tags=tag_list,
        offset=params.offset,
        limit=params.limit,
    )
    total = await service.count_documents(
        tenant_id,
        ocr_status=ocr_status,
        module_ref=module_ref,
        entity_type=entity_type,
        entity_id=entity_id,
        tags=tag_list,
    )
    latest_responses: dict[uuid.UUID, DocumentVersionResponse | None] = {}
    for doc in documents:
        assert doc.id is not None
        version = await service.get_latest_version(tenant_id, doc.id)
        latest_responses[doc.id] = DocumentVersionResponse.from_entity(version) if version else None
    responses: list[DocumentResponse] = []
    for doc in documents:
        assert doc.id is not None
        responses.append(
            DocumentResponse.from_entity(doc, latest_version=latest_responses.get(doc.id))
        )
    return ListResponse(
        data=responses,
        meta=PaginationMeta.create(total=total, page=params.page, page_size=params.page_size),
    )


@router.post("/reindex", response_model=ResponseEnvelope[dict[str, int]])
async def reindex_documents(
    body: ReindexRequest,
    _: dict[str, Any] = Depends(_require_documents_write),
    tenant_id: str = Depends(get_tenant_context),
    service: DocumentsService = Depends(get_documents_service),
) -> ResponseEnvelope[dict[str, int]]:
    """Re-enqueue documents stuck in ``failed`` (or force re-run ``ready``)."""
    enqueued = await service.reindex_many(tenant_id, ocr_status=body.ocr_status)
    return ResponseEnvelope(data={"enqueued": enqueued}, message="Reindex triggered")


# ---------------------------------------------------------------------------
# Upload + detail
# ---------------------------------------------------------------------------


@router.post("", response_model=ResponseEnvelope[DocumentResponse])
async def upload_document(
    file: UploadFile,
    current_user: dict[str, Any] = Depends(_require_documents_write),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
    module_ref: str | None = Form(default=None),
    entity_type: str | None = Form(default=None),
    entity_id: str | None = Form(default=None),
    tags: str | None = Form(default=None),
    mime_type: str | None = Form(default=None),
) -> ResponseEnvelope[DocumentResponse]:
    """Upload a document (multipart: ``file`` + optional link/tags metadata).

    ``erp.documents.write`` is required; entity-linked uploads additionally
    need the owning module read key (checked before any bytes are stored).
    """
    await guard(module_ref or "")
    data = await file.read()
    await file.close()
    document, version, _created = await service.upload_document(
        tenant_id,
        filename=file.filename or "document",
        mime_type=mime_type or file.content_type or "application/octet-stream",
        file_bytes=data,
        module_ref=module_ref or "",
        entity_type=entity_type,
        entity_id=entity_id,
        tags=[t for t in (tags or "").split(",") if t] if tags else None,
        created_by=current_user.get("user_id"),
    )
    return ResponseEnvelope(
        data=DocumentResponse.from_entity(
            document,
            latest_version=DocumentVersionResponse.from_entity(version),
        ),
        message="Document uploaded",
    )


@router.get("/{document_id}", response_model=ResponseEnvelope[DocumentResponse])
async def get_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_documents_read),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
) -> ResponseEnvelope[DocumentResponse]:
    """Fetch one document (latest version embedded)."""
    document = await service.get_document(tenant_id, document_id)
    await guard(document.module_ref)
    latest = await service.get_latest_version(tenant_id, document_id)
    return ResponseEnvelope(
        data=DocumentResponse.from_entity(
            document,
            latest_version=(DocumentVersionResponse.from_entity(latest) if latest else None),
        )
    )


@router.patch("/{document_id}", response_model=ResponseEnvelope[DocumentResponse])
async def update_document_meta(
    document_id: uuid.UUID,
    body: DocumentTagUpdate,
    current_user: dict[str, Any] = Depends(_require_documents_write),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
) -> ResponseEnvelope[DocumentResponse]:
    """Patch link + tags + display filename (version history untouched)."""
    document = await service.get_document(tenant_id, document_id)
    await guard(body.module_ref or document.module_ref)
    updates = body.model_fields_set
    updated = await service.update_document_meta(
        tenant_id,
        document_id,
        filename=body.filename if "filename" in updates else _UNSET,
        module_ref=body.module_ref if "module_ref" in updates else _UNSET,
        entity_type=body.entity_type if "entity_type" in updates else _UNSET,
        entity_id=body.entity_id if "entity_id" in updates else _UNSET,
        tags=body.tags if "tags" in updates else _UNSET,
    )
    return ResponseEnvelope(data=DocumentResponse.from_entity(updated), message="Document updated")


@router.delete("/{document_id}", response_model=ResponseEnvelope[DocumentResponse])
async def delete_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_documents_delete),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
) -> ResponseEnvelope[DocumentResponse]:
    """Hard-delete a document (blob + row + version cascade) - audit trail stays."""
    document = await service.get_document(tenant_id, document_id)
    await guard(document.module_ref)
    removed = await service.delete_document(tenant_id, document_id)
    return ResponseEnvelope(data=DocumentResponse.from_entity(removed), message="Document deleted")


# ---------------------------------------------------------------------------
# Versions / download
# ---------------------------------------------------------------------------


@router.post("/{document_id}/versions", response_model=ResponseEnvelope[DocumentResponse])
async def add_version(
    document_id: uuid.UUID,
    file: UploadFile,
    current_user: dict[str, Any] = Depends(_require_documents_write),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
    mime_type: str | None = Form(default=None),
) -> ResponseEnvelope[DocumentResponse]:
    """Append a new immutable version to a document."""
    document = await service.get_document(tenant_id, document_id)
    await guard(document.module_ref)
    data = await file.read()
    await file.close()
    updated, version = await service.add_version(
        tenant_id,
        document_id,
        filename=file.filename or document.filename,
        mime_type=mime_type
        or file.content_type
        or document.mime_type
        or "application/octet-stream",
        file_bytes=data,
        created_by=current_user.get("user_id"),
    )
    return ResponseEnvelope(
        data=DocumentResponse.from_entity(
            updated,
            latest_version=DocumentVersionResponse.from_entity(version),
        ),
        message=f"Version {version.version_number} added",
    )


@router.get("/{document_id}/versions", response_model=ListResponse[DocumentVersionResponse])
async def list_versions(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_documents_read),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
) -> ListResponse[DocumentVersionResponse]:
    """List every immutable version of a document (newest first)."""
    document = await service.get_document(tenant_id, document_id)
    await guard(document.module_ref)
    versions = await service.list_versions(tenant_id, document_id)
    return ListResponse(
        data=[DocumentVersionResponse.from_entity(v) for v in versions],
        meta=PaginationMeta.create(total=len(versions), page=1, page_size=max(len(versions), 1)),
    )


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_documents_read),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
) -> StreamingResponse:
    """Stream the current byte stream; download audited BEFORE streaming."""
    document = await service.get_document(tenant_id, document_id)
    await guard(document.module_ref)
    await service.record_download(tenant_id, document_id)
    _document, data = await service.get_document_bytes(tenant_id, document_id)
    headers = {"Content-Disposition": f'attachment; filename="{document.filename}"'}
    return StreamingResponse(
        iter([data]),
        media_type=document.mime_type or "application/octet-stream",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Tags + OCR callback
# ---------------------------------------------------------------------------


@router.post("/{document_id}/tags/confirm", response_model=ResponseEnvelope[DocumentResponse])
async def confirm_tags(
    document_id: uuid.UUID,
    body: TagConfirmIn,
    current_user: dict[str, Any] = Depends(_require_documents_write),
    tenant_id: str = Depends(get_tenant_context),
    guard: Callable[[str | None], Awaitable[None]] = Depends(get_entity_link_guard),
    service: DocumentsService = Depends(get_documents_service),
) -> ResponseEnvelope[DocumentResponse]:
    """Confirm AI-suggested tags as authoritative (idempotent)."""
    document = await service.get_document(tenant_id, document_id)
    await guard(document.module_ref)
    updated = await service.confirm_tags(tenant_id, document_id, body.ai_tags)
    return ResponseEnvelope(data=DocumentResponse.from_entity(updated), message="Tags confirmed")


@router.post("/{document_id}/ocr/result", response_model=ResponseEnvelope[DocumentResponse])
async def ocr_result(
    document_id: uuid.UUID,
    body: DocumentOcrResult,
    current_user: dict[str, Any] = Depends(_require_ocr_callback),
    tenant_id: str = Depends(get_tenant_context),
    service: DocumentsService = Depends(get_documents_service),
) -> ResponseEnvelope[DocumentResponse]:
    """ai-agent OCR callback: write extracted text + tags back to the spine."""
    updated = await service.apply_ocr_result(
        tenant_id,
        document_id,
        ocr_status=body.ocr_status,
        extracted_text=body.extracted_text,
        ai_tags=body.ai_tags,
        error_message=body.error_message,
    )
    return ResponseEnvelope(
        data=DocumentResponse.from_entity(updated), message="OCR result recorded"
    )
