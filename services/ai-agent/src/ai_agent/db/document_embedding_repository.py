"""ai_document_embeddings repository - tenant-scoped persistence (SKY-87).

Writes extracted text, AI tags, and the embedding vector for each document.
Also tracks processing status (pending/processing/ready/failed) so a reindex
can find documents that needs retry without hitting core.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from ai_agent.models.ai_document_embeddings import AiDocumentEmbeddingModel

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


class DocumentEmbeddingRepository:
    """Persist + query AI document enrichment rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        extracted_text: str | None = None,
        ai_tags: list[str] | None = None,
        embedding: list[float] | None = None,
        processing_status: str = "pending",
        error_message: str | None = None,
        module_ref: str | None = None,
        chunk_count: int = 0,
        confidence_score: float | None = None,
    ) -> None:
        row = await self._session.get(AiDocumentEmbeddingModel, (tenant_id, document_id))
        now = datetime.now(UTC)
        tags_json = json.dumps(ai_tags or []) if ai_tags is not None else None
        if row is None:
            row = AiDocumentEmbeddingModel(
                tenant_id=tenant_id,
                document_id=document_id,
                extracted_text=extracted_text,
                ai_tags=tags_json,
                embedding=embedding,
                processing_status=processing_status,
                error_message=error_message,
                module_ref=module_ref,
                chunk_count=chunk_count,
                confidence_score=confidence_score,
                processed_at=now if processing_status == "ready" else None,
            )
            self._session.add(row)
        else:
            row.extracted_text = extracted_text
            row.ai_tags = tags_json
            row.embedding = embedding
            row.processing_status = processing_status
            row.error_message = error_message
            row.module_ref = module_ref
            row.chunk_count = chunk_count
            row.confidence_score = confidence_score
            row.processed_at = now if processing_status == "ready" else None
            row.updated_at = now

    async def get(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> AiDocumentEmbeddingModel | None:
        return await self._session.get(AiDocumentEmbeddingModel, (tenant_id, document_id))

    async def list_by_status(
        self,
        tenant_id: uuid.UUID,
        *,
        statuses: list[str],
        limit: int = 50,
        offset: int = 0,
    ) -> list[AiDocumentEmbeddingModel]:
        stmt = (
            select(AiDocumentEmbeddingModel)
            .where(
                AiDocumentEmbeddingModel.tenant_id == tenant_id,
                AiDocumentEmbeddingModel.processing_status.in_(statuses),
            )
            .order_by(AiDocumentEmbeddingModel.updated_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, tenant_id: uuid.UUID) -> dict[str, int]:
        """Count documents grouped by processing status."""
        stmt = (
            select(
                AiDocumentEmbeddingModel.processing_status,
                func.count(AiDocumentEmbeddingModel.document_id),
            )
            .where(AiDocumentEmbeddingModel.tenant_id == tenant_id)
            .group_by(AiDocumentEmbeddingModel.processing_status)
        )
        result = await self._session.execute(stmt)
        return {status: int(count or 0) for status, count in result.all()}

    async def delete(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
        stmt = delete(AiDocumentEmbeddingModel).where(
            AiDocumentEmbeddingModel.tenant_id == tenant_id,
            AiDocumentEmbeddingModel.document_id == document_id,
        )
        await self._session.execute(stmt)


__all__ = ["DocumentEmbeddingRepository"]
