"""Document repository - SQLAlchemy persistence for the SKY-87 document spine.

Single tenant-scoped repository over the request-scoped ``AsyncSession``;
returns immutable domain dataclasses so the service layer stays presentation-
and ORM-free. All queries filter on ``tenant_id`` first (RLS is the guarantee,
this is the habit). Tag filters use the JSON containment operator to keep the
GIN index on ``erp_documents.tags`` engaged.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import func, select

from core.domain.entities import Document, DocumentVersion
from core.features.documents.models.document import ErpDocumentModel
from core.features.documents.models.document_version import ErpDocumentVersionModel
from core.features.documents.ports import _UNSET, DocumentRepositoryPort


def _document_to_orm(document: Document) -> ErpDocumentModel:
    kwargs: dict[str, Any] = {
        "tenant_id": document.tenant_id,
        "filename": document.filename,
        "mime_type": document.mime_type,
        "size_bytes": document.size_bytes,
        "checksum_sha256": document.checksum_sha256,
        "storage_backend": document.storage_backend,
        "storage_key": document.storage_key,
        "module_ref": document.module_ref,
        "entity_type": document.entity_type,
        "entity_id": document.entity_id,
        "tags": list(document.tags or []),
        "ocr_status": document.ocr_status,
        "ocr_error": document.ocr_error,
        "extracted_text": document.extracted_text,
        "ai_tags": list(document.ai_tags or []),
        "tags_confirmed": document.tags_confirmed,
        "version_count": document.version_count,
        "created_by": document.created_by,
    }
    if document.id is not None:
        kwargs["id"] = document.id
    return ErpDocumentModel(**kwargs)


def _document_from_orm(model: ErpDocumentModel) -> Document:
    return Document(
        id=model.id,
        tenant_id=model.tenant_id,
        filename=model.filename,
        mime_type=model.mime_type,
        size_bytes=model.size_bytes,
        checksum_sha256=model.checksum_sha256,
        storage_backend=model.storage_backend,
        storage_key=model.storage_key,
        module_ref=model.module_ref,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        tags=list(model.tags or []),
        ocr_status=model.ocr_status,
        ocr_error=model.ocr_error,
        extracted_text=model.extracted_text,
        ai_tags=list(model.ai_tags or []),
        tags_confirmed=model.tags_confirmed,
        version_count=model.version_count,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _version_from_orm(model: ErpDocumentVersionModel) -> DocumentVersion:
    return DocumentVersion(
        id=model.id,
        tenant_id=model.tenant_id,
        document_id=model.document_id,
        version_number=model.version_number,
        filename=model.filename,
        mime_type=model.mime_type,
        size_bytes=model.size_bytes,
        checksum_sha256=model.checksum_sha256,
        storage_backend=model.storage_backend,
        storage_key=model.storage_key,
        created_by=model.created_by,
        created_at=model.created_at,
    )


class DocumentsRepository(DocumentRepositoryPort):
    def __init__(self, session: Any) -> None:
        self.session = session

    async def create_document(self, document: Document) -> Document:
        model = _document_to_orm(document)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _document_from_orm(model)

    async def create_version(self, version: DocumentVersion) -> DocumentVersion:
        model = ErpDocumentVersionModel(
            tenant_id=version.tenant_id,
            document_id=version.document_id,
            version_number=version.version_number,
            filename=version.filename,
            mime_type=version.mime_type,
            size_bytes=version.size_bytes,
            checksum_sha256=version.checksum_sha256,
            storage_backend=version.storage_backend,
            storage_key=version.storage_key,
            created_by=version.created_by,
        )
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _version_from_orm(model)

    async def get_document(self, document_id: uuid.UUID, tenant_id: uuid.UUID) -> Document | None:
        stmt = select(ErpDocumentModel).where(
            ErpDocumentModel.tenant_id == tenant_id,
            ErpDocumentModel.id == document_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return _document_from_orm(model) if model is not None else None

    async def get_document_by_storage_key(
        self, storage_key: str, tenant_id: uuid.UUID
    ) -> Document | None:
        stmt = select(ErpDocumentModel).where(
            ErpDocumentModel.tenant_id == tenant_id,
            ErpDocumentModel.storage_key == storage_key,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return _document_from_orm(model) if model is not None else None

    async def get_document_by_checksum(
        self, checksum_sha256: str, tenant_id: uuid.UUID
    ) -> Document | None:
        stmt = select(ErpDocumentModel).where(
            ErpDocumentModel.tenant_id == tenant_id,
            ErpDocumentModel.checksum_sha256 == checksum_sha256,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        return _document_from_orm(model) if model is not None else None

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
        stmt = select(ErpDocumentModel).where(ErpDocumentModel.tenant_id == tenant_id)
        if ocr_status is not None:
            stmt = stmt.where(ErpDocumentModel.ocr_status == ocr_status)
        if module_ref is not None:
            stmt = stmt.where(ErpDocumentModel.module_ref == module_ref)
        if entity_type is not None:
            stmt = stmt.where(ErpDocumentModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ErpDocumentModel.entity_id == entity_id)
        if tags:
            stmt = stmt.where(ErpDocumentModel.tags.contains(list(tags)))
        stmt = stmt.order_by(ErpDocumentModel.created_at.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return [_document_from_orm(model) for model in result.scalars().all()]

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
        stmt = (
            select(func.count())
            .select_from(ErpDocumentModel)
            .where(ErpDocumentModel.tenant_id == tenant_id)
        )
        if ocr_status is not None:
            stmt = stmt.where(ErpDocumentModel.ocr_status == ocr_status)
        if module_ref is not None:
            stmt = stmt.where(ErpDocumentModel.module_ref == module_ref)
        if entity_type is not None:
            stmt = stmt.where(ErpDocumentModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ErpDocumentModel.entity_id == entity_id)
        if tags:
            stmt = stmt.where(ErpDocumentModel.tags.contains(list(tags)))
        return int((await self.session.execute(stmt)).scalar_one())

    async def list_versions(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Sequence[DocumentVersion]:
        stmt = (
            select(ErpDocumentVersionModel)
            .where(
                ErpDocumentVersionModel.tenant_id == tenant_id,
                ErpDocumentVersionModel.document_id == document_id,
            )
            .order_by(ErpDocumentVersionModel.version_number.desc())
        )
        result = await self.session.execute(stmt)
        return [_version_from_orm(model) for model in result.scalars().all()]

    async def get_latest_version(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> DocumentVersion | None:
        versions = await self.list_versions(document_id, tenant_id)
        return versions[0] if versions else None

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
    ) -> Document | None:
        stmt = select(ErpDocumentModel).where(
            ErpDocumentModel.tenant_id == tenant_id,
            ErpDocumentModel.id == document_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        if filename is not _UNSET:
            model.filename = cast("str", filename)
        if module_ref is not _UNSET:
            model.module_ref = cast("str | None", module_ref)
        if entity_type is not _UNSET:
            model.entity_type = cast("str | None", entity_type)
        if entity_id is not _UNSET:
            model.entity_id = cast("str | None", entity_id)
        if tags is not _UNSET:
            model.tags = cast("list[str]", tags)
        if ocr_status is not _UNSET:
            model.ocr_status = cast("str", ocr_status)
        if ocr_error is not _UNSET:
            model.ocr_error = cast("str | None", ocr_error)
        if extracted_text is not _UNSET:
            model.extracted_text = cast("str | None", extracted_text)
        if ai_tags is not _UNSET:
            model.ai_tags = cast("list[str]", ai_tags)
        if tags_confirmed is not _UNSET:
            model.tags_confirmed = cast("bool", tags_confirmed)
        if version_count is not _UNSET:
            model.version_count = cast("int", version_count)
        if mime_type is not _UNSET:
            model.mime_type = cast("str", mime_type)
        if storage_backend is not _UNSET:
            model.storage_backend = cast("str", storage_backend)
        if storage_key is not _UNSET:
            model.storage_key = cast("str", storage_key)
        if checksum_sha256 is not _UNSET:
            model.checksum_sha256 = cast("str", checksum_sha256)
        if size_bytes is not _UNSET:
            model.size_bytes = cast("int", size_bytes)
        await self.session.flush()
        await self.session.refresh(model)
        return _document_from_orm(model)

    async def delete_document(
        self, document_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Document | None:
        stmt = select(ErpDocumentModel).where(
            ErpDocumentModel.tenant_id == tenant_id,
            ErpDocumentModel.id == document_id,
        )
        model = (await self.session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        snapshot = _document_from_orm(model)
        await self.session.delete(model)
        await self.session.flush()
        return snapshot

    async def commit(self) -> None:
        await self.session.commit()
