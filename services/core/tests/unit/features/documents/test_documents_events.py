"""Documents event dispatch tests (SKY-87).

Covers the publish_* envelope emitters and the fire-and-forget OCR dispatch
hook. The event producer is swapped for a recording double; the OCR dispatch
is exercised in the "skip" path (no sync token) by default.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from core.features.documents.events import (
    publish_document_deleted,
    publish_document_downloaded,
    publish_document_tags_confirmed,
    publish_document_uploaded,
    publish_document_version_added,
    reindex_failed,
)

if TYPE_CHECKING:
    from skyrict_events.base import BaseEvent

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Recording double
# ---------------------------------------------------------------------------


class RecordingProducer:
    def __init__(self) -> None:
        self.published: list[tuple[str, BaseEvent, str | None]] = []

    def publish(self, topic: str, event: BaseEvent, *, key: str | None = None) -> None:
        self.published.append((topic, event, key))

    async def apublish(self, topic: str, event: BaseEvent, *, key: str | None = None) -> None:
        self.publish(topic, key=key)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPublishDocumentUploaded:
    def test_emits_correct_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        producer = RecordingProducer()
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.get_event_producer",
            lambda: producer,
        )
        doc_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        publish_document_uploaded(tenant_id=str(tenant_id), document_id=str(doc_id))
        assert len(producer.published) == 1
        topic, event, key = producer.published[0]
        assert topic == "documents.document.uploaded"
        assert event.event_type == "documents.document.uploaded"
        assert event.metadata["document_id"] == str(doc_id)
        assert key == str(tenant_id)


class TestPublishDocumentVersionAdded:
    def test_emits_correct_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        producer = RecordingProducer()
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.get_event_producer",
            lambda: producer,
        )
        doc_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        publish_document_version_added(tenant_id=tenant_id, document_id=doc_id)
        assert len(producer.published) == 1
        topic, _event, _ = producer.published[0]
        assert topic == "documents.document.version_added"


class TestPublishDocumentDeleted:
    def test_emits_correct_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        producer = RecordingProducer()
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.get_event_producer",
            lambda: producer,
        )
        publish_document_deleted(tenant_id="t", document_id="d")
        assert producer.published[0][0] == "documents.document.deleted"


class TestPublishDocumentDownloaded:
    def test_emits_correct_envelope(self, monkeypatch: pytest.MonkeyPatch) -> None:
        producer = RecordingProducer()
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.get_event_producer",
            lambda: producer,
        )
        publish_document_downloaded(tenant_id="t", document_id="d")
        assert producer.published[0][0] == "documents.document.downloaded"


class TestPublishDocumentTagsConfirmed:
    def test_emits_correct_envelope_with_tags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        producer = RecordingProducer()
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.get_event_producer",
            lambda: producer,
        )
        publish_document_tags_confirmed(tenant_id="t", document_id="d", tags=["a", "b"])
        assert producer.published[0][0] == "documents.document.tags_confirmed"
        event = producer.published[0][1]
        assert event.metadata["tags"] == ["a", "b"]


class TestReindexFailed:
    def test_emits_no_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        producer = RecordingProducer()
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.get_event_producer",
            lambda: producer,
        )
        reindex_failed(tenant_id="t", document_id="d")
        # reindex_failed does NOT publish to the event bus; it only fires OCR dispatch
        assert len(producer.published) == 0


class TestSpawnOcrDispatch:
    def test_skips_when_no_sync_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.settings",
            type("S", (), {"AI_SYNC_TOKEN": "", "AI_AGENT_URL": "http://x"})(),
        )
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.TenantContext",
            type(
                "TC",
                (),
                {
                    "get_tenant_slug": staticmethod(lambda: None),
                    "get_optional": staticmethod(lambda: None),
                },
            )(),
        )
        # Should not raise; dispatch is skipped
        publish_document_uploaded(tenant_id="t", document_id="d")

    def test_skips_when_no_tenant_slug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.settings",
            type("S", (), {"AI_SYNC_TOKEN": "tok", "AI_AGENT_URL": "http://x"})(),
        )
        monkeypatch.setattr(
            "core.features.documents.events.dispatch.TenantContext",
            type(
                "TC",
                (),
                {
                    "get_tenant_slug": staticmethod(lambda: None),
                    "get_optional": staticmethod(lambda: None),
                },
            )(),
        )
        publish_document_uploaded(tenant_id="t", document_id="d")
