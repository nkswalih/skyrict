"""Core documents gateway - fetch byte streams + write OCR results (SKY-87).

ai-agent owns the AI enrichment (OCR, tagging, embeddings) but core owns the
byte stream and the document master. This adapter:
  * fetches a document's bytes from core's ``GET /documents/{id}/download``
  * posts results back to core's ``POST /documents/{id}/ocr/result`` (m2m,
    authenticated with the shared ``CORE_AI_SYNC_TOKEN``)
  * lists documents to re-process via core's ``GET /documents``

Docstrings cite the core contract from docs/modules/documents.md. Tests fake
the :class:`DocumentGatewayPort` protocol.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from ai_agent.core.config import settings
from ai_agent.core.exceptions import AiUnavailableError

logger = structlog.get_logger("ai_agent.documents_gateway")


@dataclass(frozen=True, slots=True)
class CoreDocument:
    """Document metadata as surfaced by core's GET /documents/{id}."""

    document_id: uuid.UUID
    filename: str
    mime_type: str
    module_ref: str | None = None


@dataclass(frozen=True, slots=True)
class OcrWriteResult:
    """Outcome of posting an OCR result back to core."""

    ok: bool
    status_code: int | None = None
    error: str | None = None


class DocumentGatewayPort(Protocol):
    """Boundary ai-agent depends on to reach core's documents API."""

    async def fetch_document_bytes(
        self, tenant_slug: str, document_id: uuid.UUID
    ) -> tuple[CoreDocument, bytes]: ...

    async def write_ocr_result(
        self,
        tenant_slug: str,
        document_id: uuid.UUID,
        *,
        ocr_status: str,
        extracted_text: str | None = None,
        ai_tags: list[str] | None = None,
        error_message: str | None = None,
    ) -> OcrWriteResult: ...

    async def list_documents_for_reindex(
        self,
        tenant_slug: str,
        *,
        ocr_status: str,
        limit: int,
    ) -> list[CoreDocument]: ...


class HttpDocumentGateway:
    """Production adapter - talks to the core monolith over HTTP."""

    def __init__(
        self,
        *,
        core_url: str | None = None,
        sync_token: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._core_url = (core_url or settings.CORE_DOCUMENT_URL).rstrip("/")
        self._sync_token = sync_token or settings.INVENTORY_SYNC_TOKEN
        self._timeout = timeout or settings.CORE_DOCUMENT_TIMEOUT_SECONDS

    def _headers(self, tenant_slug: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._sync_token}",
            "X-Tenant-Slug": tenant_slug,
        }

    def _safe_document_id(self, document_id: uuid.UUID) -> str:
        """Return the canonical UUID string - never interpolate raw input.

        The document id is validated here (not just at the router edge) so the
        id flowed into core's URL path is always a strict ``8-4-4-4-12`` hex
        UUID. Core's base URL is pinned to the configured
        ``CORE_DOCUMENT_URL`` and the request targets are fixed relative
        paths, so user input can never steer the host or scheme (SSRF).
        """
        try:
            parsed = uuid.UUID(str(document_id))
        except (AttributeError, TypeError, ValueError) as exc:
            raise AiUnavailableError(f"invalid document id: {document_id!r}") from exc
        return str(parsed)

    async def fetch_document_bytes(
        self, tenant_slug: str, document_id: uuid.UUID
    ) -> tuple[CoreDocument, bytes]:
        """Fetch document bytes from core's download endpoint.

        Core routes the storage backend (local or S3) off the document row, so
        ai-agent always streams through the HTTP contract - never reaches into
        the storage adapter directly.
        """
        doc_id = self._safe_document_id(document_id)
        try:
            async with httpx.AsyncClient(base_url=self._core_url, timeout=self._timeout) as client:
                resp = await client.get(
                    f"/documents/{doc_id}/download", headers=self._headers(tenant_slug)
                )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AiUnavailableError(
                f"core returned {exc.response.status_code} for document download"
            ) from exc
        except httpx.HTTPError as exc:
            raise AiUnavailableError(f"core document download failed: {exc}") from exc

        # Pull metadata from response headers (Content-Disposition carries filename)
        filename = resp.headers.get("X-Document-Filename", "document.pdf")
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return (
            CoreDocument(
                document_id=document_id,
                filename=filename,
                mime_type=content_type,
            ),
            resp.content,
        )

    async def write_ocr_result(
        self,
        tenant_slug: str,
        document_id: uuid.UUID,
        *,
        ocr_status: str,
        extracted_text: str | None = None,
        ai_tags: list[str] | None = None,
        error_message: str | None = None,
    ) -> OcrWriteResult:
        """Post an OCR result back to core's m2m callback.

        The callback is authenticated by core's ``require_ingest_m2m_or_permission``
        (either the shared sync token OR an api-key user with document write).
        """
        doc_id = self._safe_document_id(document_id)
        payload: dict[str, object] = {"ocr_status": ocr_status}
        if extracted_text is not None:
            payload["extracted_text"] = extracted_text
        if ai_tags is not None:
            payload["ai_tags"] = ai_tags
        if error_message is not None:
            payload["error_message"] = error_message
        headers = self._headers(tenant_slug)
        headers["Content-Type"] = "application/json"
        try:
            async with httpx.AsyncClient(base_url=self._core_url, timeout=self._timeout) as client:
                resp = await client.post(
                    f"/documents/{doc_id}/ocr/result", headers=headers, json=payload
                )
            if resp.status_code >= 400:
                logger.warning(
                    "documents.ocr.write_failed",
                    document_id=str(document_id),
                    status=resp.status_code,
                )
                return OcrWriteResult(ok=False, status_code=resp.status_code)
            return OcrWriteResult(ok=True, status_code=resp.status_code)
        except httpx.HTTPError as exc:
            logger.warning(
                "documents.ocr.write_error", document_id=str(document_id), error=str(exc)
            )
            return OcrWriteResult(ok=False, error=str(exc))

    async def list_documents_for_reindex(
        self,
        tenant_slug: str,
        *,
        ocr_status: str,
        limit: int,
    ) -> list[CoreDocument]:
        """List documents needing re-processing from core's list endpoint."""
        try:
            async with httpx.AsyncClient(base_url=self._core_url, timeout=self._timeout) as client:
                resp = await client.get(
                    "/documents",
                    params={"ocr_status": ocr_status, "page": 1, "page_size": limit},
                    headers=self._headers(tenant_slug),
                )
            resp.raise_for_status()
            body = resp.json()
            data = (body or {}).get("data") or []
        except (httpx.HTTPStatusError, httpx.HTTPError, ValueError) as exc:
            logger.warning("documents.reindex.list_error", error=str(exc))
            return []
        docs: list[CoreDocument] = []
        for item in data:
            doc_id = item.get("id")
            if doc_id is None:
                continue
            try:
                uid = uuid.UUID(str(doc_id))
            except ValueError:
                continue
            docs.append(
                CoreDocument(
                    document_id=uid,
                    filename=item.get("filename", ""),
                    mime_type=item.get("mime_type", "application/octet-stream"),
                    module_ref=item.get("module_ref"),
                )
            )
        return docs


__all__ = ["CoreDocument", "DocumentGatewayPort", "HttpDocumentGateway", "OcrWriteResult"]
