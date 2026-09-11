"""Unit tests for the Audit Guardian report API (SKY-90).

The app is exercised through TestClient without lifespan, auth stubbed to a
fixed caller, and repository reads/writes replaced by scripted fakes. These
cover the wire contract: tenant-scoped report list/detail/review, evidence
links on the detail view, and 404 on unknown report ids.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from fastapi.testclient import TestClient

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.db.guardian_report_repository import GuardianReportRepository
from ai_agent.main import create_app

if TYPE_CHECKING:
    import pytest

_TENANT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_CALLER = {
    "user_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
    "tenant_id": _TENANT_ID,
    "token_payload": {"sub": "11111111-1111-4111-8111-111111111111"},
}


class _NullSession:
    async def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("repository is faked; session must not be touched")

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _Report:
    def __init__(self, report_id: uuid.UUID) -> None:
        self.id = report_id
        self.report_week_start = date(2026, 8, 31)
        self.report_week_end = date(2026, 9, 6)
        self.summary = "No suspicious activity detected."
        self.total_events_scanned = 120
        self.flagged_count = 0
        self.status = "generated"
        self.generated_at = datetime.now(tz=UTC)


class _Event:
    def __init__(self, event_id: uuid.UUID) -> None:
        self.id = event_id
        self.source_table = "ai_audit_log"
        self.source_id = uuid.uuid4()
        self.event_action = "ai.query.executed"
        self.severity = "high"
        self.reason = "Bulk read of customers table"
        self.evidence = {"user_id": "u-1", "ip": "203.0.113.7", "rows": 450}
        self.flagged_at = datetime.now(tz=UTC)


def _client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("ai_agent.api.middleware.is_tenant_required_path", lambda _path: False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    app.dependency_overrides[get_db] = lambda: _NullSession()
    return TestClient(app, raise_server_exceptions=True)


def test_list_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _Report(uuid.uuid4())
    second = _Report(uuid.uuid4())
    second.report_week_start = date(2026, 8, 24)
    second.report_week_end = date(2026, 8, 30)

    async def fake_list(self, *, tenant_id: uuid.UUID, limit: int) -> list[Any]:
        assert tenant_id == _TENANT_ID
        assert limit == 20
        return [report, second]

    monkeypatch.setattr(GuardianReportRepository, "list_reports", fake_list)
    client = _client(monkeypatch)

    response = client.get("/api/v1/ai/guardian/reports", headers={"authorization": "Bearer t"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"count": 2}
    assert body["data"][0]["summary"] == "No suspicious activity detected."
    assert body["data"][0]["status"] == "generated"


def test_get_report_detail_includes_evidence_links(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _Report(uuid.uuid4())
    event = _Event(uuid.uuid4())

    async def fake_get(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> Any | None:
        assert tenant_id == _TENANT_ID
        assert report_id == report.id
        return report

    async def fake_events(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> list[Any]:
        return [event]

    monkeypatch.setattr(GuardianReportRepository, "get_report", fake_get)
    monkeypatch.setattr(GuardianReportRepository, "list_events_for_report", fake_events)
    client = _client(monkeypatch)

    response = client.get(
        f"/api/v1/ai/guardian/reports/{report.id}", headers={"authorization": "Bearer t"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(report.id)
    (item,) = body["events"]
    assert item["source_table"] == "ai_audit_log"
    assert item["source_id"] == str(event.source_id)
    assert item["severity"] == "high"
    assert item["evidence"] == {"user_id": "u-1", "ip": "203.0.113.7", "rows": 450}


def test_get_report_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> Any | None:
        return None

    monkeypatch.setattr(GuardianReportRepository, "get_report", fake_get)
    client = _client(monkeypatch)

    response = client.get(
        f"/api/v1/ai/guardian/reports/{uuid.uuid4()}", headers={"authorization": "Bearer t"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Report not found"


def test_review_report_marks_reviewed(monkeypatch: pytest.MonkeyPatch) -> None:
    report = _Report(uuid.uuid4())

    async def fake_get(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> Any | None:
        assert report_id == report.id
        return report

    async def fake_review(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> None:
        report.status = "reviewed"

    monkeypatch.setattr(GuardianReportRepository, "get_report", fake_get)
    monkeypatch.setattr(GuardianReportRepository, "mark_report_reviewed", fake_review)
    client = _client(monkeypatch)

    response = client.post(
        f"/api/v1/ai/guardian/reports/{report.id}/review",
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"


def test_review_report_404(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, *, tenant_id: uuid.UUID, report_id: uuid.UUID) -> Any | None:
        return None

    monkeypatch.setattr(GuardianReportRepository, "get_report", fake_get)
    client = _client(monkeypatch)

    response = client.post(
        f"/api/v1/ai/guardian/reports/{uuid.uuid4()}/review",
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 404
