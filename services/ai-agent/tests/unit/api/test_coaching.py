"""Unit tests for the Sales Coach suggestion API (SKY-90).

The app is exercised through TestClient without lifespan (no DB/Redis pools),
with the auth dependency stubbed to a fixed caller and repository reads/writes
replaced by scripted fakes (same seam as test_supplier_risk.py). These cover
the wire contract: tenant/rep scoping, review decision + audit event, 404 on
unknown id, and 422 on an invalid review status.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi.testclient import TestClient

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.core.audit_service import AuditService
from ai_agent.db.coaching_suggestion_repository import CoachingSuggestionRepository
from ai_agent.main import create_app

if TYPE_CHECKING:
    import pytest

_TENANT_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
_REP_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
_CALLER = {
    "user_id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
    "tenant_id": _TENANT_ID,
    "token_payload": {"sub": "11111111-1111-4111-8111-111111111111"},
}


class _NullSession:
    """Stands in for the async session (repository methods are faked)."""

    async def execute(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError("repository is faked; session must not be touched")

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class _Suggestion:
    """Row-shaped object the router maps to the wire schema."""

    def __init__(self, suggestion_id: uuid.UUID, status: str = "pending") -> None:
        now = datetime.now(tz=UTC)
        self.id = suggestion_id
        self.rep_user_id = _REP_ID
        self.opportunity_id: uuid.UUID | None = None
        self.lead_id: uuid.UUID | None = None
        self.suggestion_type = "follow_up"
        self.title = "Follow up with Acme"
        self.body = "Acme's quote has been open for 10 days without activity."
        self.status = status
        self.reviewed_by: uuid.UUID | None = None
        self.reviewed_at: datetime | None = None
        self.created_at = now
        self.updated_at = now


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, list[dict[str, Any]]]:
    """App with stubbed auth/db; returns client + recorded audit events."""
    monkeypatch.setattr("ai_agent.api.middleware.is_tenant_required_path", lambda _path: False)
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: _CALLER
    app.dependency_overrides[get_db] = lambda: _NullSession()

    audits: list[dict[str, Any]] = []

    async def fake_log(self, **kwargs: Any) -> object:
        audits.append(kwargs)
        return None

    monkeypatch.setattr(AuditService, "log", fake_log)
    return TestClient(app, raise_server_exceptions=True), audits


def test_list_suggestions_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_list_all_pending(self, *, tenant_id: uuid.UUID) -> list[Any]:
        assert tenant_id == _TENANT_ID
        return []

    monkeypatch.setattr(CoachingSuggestionRepository, "list_all_pending", fake_list_all_pending)
    client, _ = _client(monkeypatch)

    response = client.get("/api/v1/ai/coaching/suggestions", headers={"authorization": "Bearer t"})

    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"count": 0}}


def test_list_suggestions_scoped_to_rep(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _Suggestion(uuid.uuid4())

    async def fake_list_for_rep(self, *, tenant_id: uuid.UUID, rep_user_id: uuid.UUID) -> list[Any]:
        assert tenant_id == _TENANT_ID
        assert rep_user_id == _REP_ID
        return [row]

    monkeypatch.setattr(CoachingSuggestionRepository, "list_pending_for_rep", fake_list_for_rep)
    client, _ = _client(monkeypatch)

    response = client.get(
        f"/api/v1/ai/coaching/suggestions?rep_user_id={_REP_ID}",
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"] == {"count": 1}
    assert body["data"][0]["title"] == "Follow up with Acme"
    assert body["data"][0]["rep_user_id"] == str(_REP_ID)


def test_review_accepts_suggestion(monkeypatch: pytest.MonkeyPatch) -> None:
    suggestion = _Suggestion(uuid.uuid4())

    async def fake_get(self, *, tenant_id: uuid.UUID, suggestion_id: uuid.UUID) -> Any:
        assert tenant_id == _TENANT_ID
        assert suggestion_id == suggestion.id
        return suggestion

    async def fake_mark_reviewed(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        status: str,
        reviewed_by: uuid.UUID,
    ) -> None:
        assert tenant_id == _TENANT_ID
        assert suggestion_id == suggestion.id
        assert status == "accepted"
        assert reviewed_by == _CALLER["user_id"]
        suggestion.status = status

    monkeypatch.setattr(CoachingSuggestionRepository, "get_suggestion", fake_get)
    monkeypatch.setattr(CoachingSuggestionRepository, "mark_reviewed", fake_mark_reviewed)
    client, audits = _client(monkeypatch)

    response = client.post(
        f"/api/v1/ai/coaching/suggestions/{suggestion.id}/review",
        json={"status": "accepted"},
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(suggestion.id)
    assert response.json()["status"] == "accepted"
    assert audits == [
        {
            "action": "ai.coaching.suggestion.accepted",
            "tenant_id": _TENANT_ID,
            "user_id": _CALLER["user_id"],
            "input_payload": {"suggestion_id": str(suggestion.id), "rep_user_id": str(_REP_ID)},
        }
    ]


def test_review_dismisses_suggestion_and_audits(monkeypatch: pytest.MonkeyPatch) -> None:
    suggestion = _Suggestion(uuid.uuid4())

    async def fake_get(self, *, tenant_id: uuid.UUID, suggestion_id: uuid.UUID) -> Any:
        return suggestion

    async def fake_mark_reviewed(
        self,
        *,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        status: str,
        reviewed_by: uuid.UUID,
    ) -> None:
        suggestion.status = status

    monkeypatch.setattr(CoachingSuggestionRepository, "get_suggestion", fake_get)
    monkeypatch.setattr(CoachingSuggestionRepository, "mark_reviewed", fake_mark_reviewed)
    client, audits = _client(monkeypatch)

    response = client.post(
        f"/api/v1/ai/coaching/suggestions/{suggestion.id}/review",
        json={"status": "dismissed"},
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert audits[0]["action"] == "ai.coaching.suggestion.dismissed"


def test_review_404_for_unknown_suggestion(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, *, tenant_id: uuid.UUID, suggestion_id: uuid.UUID) -> Any | None:
        return None

    monkeypatch.setattr(CoachingSuggestionRepository, "get_suggestion", fake_get)
    client, audits = _client(monkeypatch)

    response = client.post(
        f"/api/v1/ai/coaching/suggestions/{uuid.uuid4()}/review",
        json={"status": "dismissed"},
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Suggestion not found"
    assert audits == []


def test_review_rejects_invalid_status(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _client(monkeypatch)

    response = client.post(
        f"/api/v1/ai/coaching/suggestions/{uuid.uuid4()}/review",
        json={"status": "watched"},
        headers={"authorization": "Bearer t"},
    )

    assert response.status_code == 422
