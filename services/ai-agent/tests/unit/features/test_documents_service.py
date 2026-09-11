"""Unit tests for the document OCR/tag/embed service (SKY-87).

Feature-layer orchestration with fake adapters (no models/db - import-linter
contract): a successful run persists processing->ready and writes back to the
gateway callback, a hardware failure degrades to ready-even-without-embed, and
a gateway failure marks the document 'failed' with the error surfaced back.
"""

from __future__ import annotations

import uuid

from ai_agent.core.embedding import EmbeddingResult
from ai_agent.features.documents.gateway import CoreDocument, OcrWriteResult
from ai_agent.features.documents.service import DocumentOcrService

TENANT_ID = uuid.uuid4()
TENANT_SLUG = "acme"
DOC_ID = uuid.uuid4()

_TAG_JSON = '["invoice", "electronics order"]'


class FakeStore:
    def __init__(self) -> None:
        self.upserts: list[dict[str, object]] = []
        self.written_statuses: list[str] = []

    async def upsert(self, **kwargs: object) -> None:
        self.upserts.append(kwargs)
        self.written_statuses.append(str(kwargs["processing_status"]))

    async def get(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
        return None


class FakeGateway:
    def __init__(self) -> None:
        self.fetch_calls = 0
        self.byte_error: Exception | None = None
        self.write_calls: list[dict[str, object]] = []
        self.write_error: Exception | None = None

    async def fetch_document_bytes(
        self, tenant_slug: str, document_id: uuid.UUID
    ) -> tuple[CoreDocument, bytes]:
        self.fetch_calls += 1
        if self.byte_error is not None:
            raise self.byte_error
        return (
            CoreDocument(
                document_id=document_id,
                filename="invoice.pdf",
                mime_type="application/pdf",
                module_ref="finance",
            ),
            b"%PDF-1.4 fake",
        )

    async def write_ocr_result(self, *args: object, **kwargs: object) -> OcrWriteResult:
        self.write_calls.append({"args": args, "kwargs": kwargs})
        if self.write_error is not None:
            raise self.write_error
        return OcrWriteResult(ok=True, status_code=200)


class FakeLlmRouter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def complete(self, request: object) -> object:
        if self.fail:
            raise RuntimeError("llm down")
        return type("C", (), {"text": _TAG_JSON})()


class FakeEmbeddingProvider:
    name = "openai"
    model = "text-embedding-3-small"
    dims = 768

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[0.1] * 4 for _ in texts],
            model_used=self.model,
            dims=4,
            latency_ms=7,
        )


def _service(
    *,
    store: FakeStore,
    gateway: FakeGateway,
    llm: FakeLlmRouter | None = None,
) -> DocumentOcrService:
    return DocumentOcrService(
        store=store,
        gateway=gateway,
        llm_router=llm,
        embedding_provider=FakeEmbeddingProvider(),
    )


class TestProcessSuccessful:
    async def test_persists_processing_then_ready_and_writes_callback(self) -> None:
        store = FakeStore()
        gateway = FakeGateway()
        llm = FakeLlmRouter()

        result = await _service(store=store, gateway=gateway, llm=llm).process(
            tenant_id=TENANT_ID, tenant_slug=TENANT_SLUG, document_id=DOC_ID
        )

        assert result.ocr_status == "ready"
        assert result.ai_tags == ["invoice", "electronics order"]
        assert store.written_statuses == ["processing", "ready"]
        assert gateway.fetch_calls == 1

        assert len(gateway.write_calls) == 1
        write = gateway.write_calls[0]["kwargs"]
        assert write["ocr_status"] == "ready"
        assert write["ai_tags"] == ["invoice", "electronics order"]

    async def test_degrades_to_ready_when_no_embedding_text(self) -> None:
        store = FakeStore()
        gateway = FakeGateway()

        async def no_bytes(tenant_slug: str, document_id: uuid.UUID) -> tuple[CoreDocument, bytes]:
            return (
                CoreDocument(document_id=document_id, filename="x", mime_type="text/plain"),
                b"",
            )

        gateway.fetch_document_bytes = no_bytes  # type: ignore[method-assign]
        result = await _service(store=store, gateway=gateway).process(
            tenant_id=TENANT_ID, tenant_slug=TENANT_SLUG, document_id=DOC_ID
        )
        assert result.ocr_status == "ready"

    async def test_no_llm_skips_tagging_but_still_readies(self) -> None:
        store = FakeStore()
        gateway = FakeGateway()

        result = await _service(store=store, gateway=gateway).process(
            tenant_id=TENANT_ID, tenant_slug=TENANT_SLUG, document_id=DOC_ID
        )
        assert result.ocr_status == "ready"
        assert result.ai_tags == []


class TestProcessFailure:
    async def test_gateway_failure_marks_document_failed(self) -> None:
        store = FakeStore()
        gateway = FakeGateway()
        gateway.byte_error = RuntimeError("core down")

        result = await _service(store=store, gateway=gateway).process(
            tenant_id=TENANT_ID, tenant_slug=TENANT_SLUG, document_id=DOC_ID
        )

        assert result.ocr_status == "failed"
        assert result.error_message
        assert store.written_statuses[-1] == "failed"
        write = gateway.write_calls[-1]["kwargs"]
        assert write["ocr_status"] == "failed"

    async def test_llm_failure_still_readies_with_empty_tags(self) -> None:
        store = FakeStore()
        gateway = FakeGateway()
        llm = FakeLlmRouter(fail=True)

        result = await _service(store=store, gateway=gateway, llm=llm).process(
            tenant_id=TENANT_ID, tenant_slug=TENANT_SLUG, document_id=DOC_ID
        )
        assert result.ocr_status == "ready"
        assert result.ai_tags == []
