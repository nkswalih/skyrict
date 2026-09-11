"""Document OCR + tagging + embedding service (SKY-87).

ai-agent owns the AI enrichment of documents stored in core:

1. fetch the byte stream from core (GET /documents/{id}/download)
2. extract text (or pass images to a vision-capable LLM)
3. tag the document via LLM, chunk it, and embed each chunk
4. write the OCR result + tags + embedding back (both to core's callback
   AND our ai_agent_document_embeddings mirror row)

Every step is tenant-scoped and mirrors core's lifecycle statuses
(pending -> processing -> ready | failed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog

from ai_agent.core.config import settings
from ai_agent.core.embedding import EmbeddingProvider, build_embedding_provider
from ai_agent.core.providers.base import LlmRequest
from ai_agent.core.token_counter import TokenCounter
from ai_agent.features.documents.gateway import (
    DocumentGatewayPort,
    HttpDocumentGateway,
)

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.models.ai_document_embeddings import AiDocumentEmbeddingModel

logger = structlog.get_logger("ai_agent.documents_service")

_TAGGER_SYSTEM = (
    "You are a document classification assistant. Return ONLY a JSON array of "
    "strings, each a concise lowercase tag (max 5 tags). Tags should capture the "
    "document type (invoice, contract, receipt, report, memo), the entity it "
    "concerns, and key subjects. Use up to 8 words per tag."
)

_IMAGE_TAGGER_SYSTEM = (
    "You are a document visual assistant. Describe this document scan/image as "
    "concise lowercase tags. Return ONLY a JSON array of strings (max 8 tags) "
    "covering document type and content subjects."
)


@runtime_checkable
class DocumentEmbeddingStorePort(Protocol):
    """Boundary the service depends on for document enrichment persistence.

    The concrete :class:`ai_agent.db.document_embedding_repository.DocumentEmbeddingRepository`
    implements this in production; tests provide fakes. The router is the
    composition root that wires the concrete store in.
    """

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
    ) -> None: ...

    async def get(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> AiDocumentEmbeddingModel | None: ...


@dataclass(frozen=True, slots=True)
class DocumentProcessResult:
    document_id: uuid.UUID
    ocr_status: str
    extracted_text: str | None
    ai_tags: list[str]
    error_message: str | None


class DocumentOcrService:
    """Full pipeline for one document. Tests inject fakes for the seams.

    The router (composition root) wires in the concrete
    :class:`DocumentEmbeddingRepository` and commits the DB session after
    :meth:`process` returns - this service never owns the session so it stays
    free of the ``db`` layer (import-linter: features never touch db).
    """

    def __init__(
        self,
        *,
        store: DocumentEmbeddingStorePort,
        gateway: DocumentGatewayPort | None = None,
        llm_router: LlmRouter | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._store = store
        self._gateway = gateway or HttpDocumentGateway()
        self._llm_router = llm_router
        self._embedding_provider = embedding_provider or build_embedding_provider(settings)

    async def process(
        self,
        *,
        tenant_id: uuid.UUID,
        tenant_slug: str,
        document_id: uuid.UUID,
    ) -> DocumentProcessResult:
        """Run the OCR/tag/embed pipeline for one document and persist results.

        The caller (router) is responsible for committing the session after the
        writes; this method only mutates the injected store.
        """
        try:
            await self._store.upsert(
                tenant_id=tenant_id,
                document_id=document_id,
                processing_status="processing",
            )

            doc, raw_bytes = await self._gateway.fetch_document_bytes(tenant_slug, document_id)

            from ai_agent.features.documents.processor import extract_document_content

            extraction = extract_document_content(raw_bytes, doc.mime_type, doc.filename)

            tags: list[str] = []
            if self._llm_router is not None:
                tags = await self._tag_document(
                    extracted_text=extraction.extracted_text,
                    image_base64s=extraction.image_base64s,
                    filename=doc.filename,
                )
            else:
                logger.info(
                    "documents.tags.skipped",
                    document_id=str(document_id),
                    reason="no llm configured",
                )

            embedding_vec: list[float] | None = None
            if self._embedding_provider is not None and extraction.extracted_text:
                chunk_texts = _chunk_for_embedding(extraction.extracted_text, TokenCounter())
                if chunk_texts:
                    try:
                        result = await self._embedding_provider.embed(chunk_texts[:32])
                        if result.vectors:
                            embedding_vec = result.vectors[0]
                    except Exception:
                        logger.warning(
                            "documents.embed.failed",
                            document_id=str(document_id),
                        )

            await self._store.upsert(
                tenant_id=tenant_id,
                document_id=document_id,
                extracted_text=extraction.extracted_text,
                ai_tags=tags,
                embedding=embedding_vec,
                processing_status="ready",
                module_ref=doc.module_ref,
                chunk_count=extraction.chunk_count,
                confidence_score=extraction.confidence_score,
            )

            await self._gateway.write_ocr_result(
                tenant_slug,
                document_id,
                ocr_status="ready",
                extracted_text=extraction.extracted_text,
                ai_tags=tags,
            )

            return DocumentProcessResult(
                document_id=document_id,
                ocr_status="ready",
                extracted_text=extraction.extracted_text,
                ai_tags=tags,
                error_message=None,
            )
        except Exception as exc:
            logger.exception(
                "documents.process.failed",
                document_id=str(document_id),
            )
            await self._store.upsert(
                tenant_id=tenant_id,
                document_id=document_id,
                processing_status="failed",
                error_message=str(exc),
            )
            await self._gateway.write_ocr_result(
                tenant_slug,
                document_id,
                ocr_status="failed",
                error_message=str(exc),
            )
            return DocumentProcessResult(
                document_id=document_id,
                ocr_status="failed",
                extracted_text=None,
                ai_tags=[],
                error_message=str(exc),
            )

    async def _tag_document(
        self,
        *,
        extracted_text: str,
        image_base64s: list[str],
        filename: str,
    ) -> list[str]:
        if self._llm_router is None:
            return []
        if image_base64s:
            image_blocks: list[dict[str, object]] = [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_base64s[0]}"},
                }
            ]
            request = LlmRequest(
                system_prompt=_IMAGE_TAGGER_SYSTEM,
                user_prompt=(f"Classify this document (file: {filename}) into subject tags."),
                max_tokens=200,
                temperature=0.1,
                json_mode=True,
                image_blocks=image_blocks,
            )
        else:
            request = LlmRequest(
                system_prompt=_TAGGER_SYSTEM,
                user_prompt=(
                    f"Classify the following document (file: {filename}) into subject "
                    f"tags:\n\n{extracted_text[:8000]}"
                ),
                max_tokens=200,
                temperature=0.1,
                json_mode=True,
            )
        try:
            completion = await self._llm_router.complete(request)
            tags = _parse_tag_list(completion.text)
            return tags[:8]
        except Exception:
            logger.warning("documents.tagger.failed")
            return []


def _parse_tag_list(text: str) -> list[str]:
    """Best-effort parse of a JSON array of tag strings from LLM output."""
    import json
    import re

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(t).strip() for t in parsed if str(t).strip()]
    except Exception:
        pass
    return []


def _chunk_for_embedding(text: str, counter: TokenCounter, max_tokens: int = 700) -> list[str]:
    """Split extracted text into ~700-token chunks for embedding."""
    tokens = counter.encode(text)
    chunk_size_tokens = max_tokens
    chunks: list[str] = []
    for i in range(0, len(tokens), chunk_size_tokens):
        chunk_ids = tokens[i : i + chunk_size_tokens]
        if chunk_ids:
            chunks.append(counter.decode(chunk_ids))
    return chunks


__all__ = [
    "DocumentEmbeddingStorePort",
    "DocumentOcrService",
    "DocumentProcessResult",
]
