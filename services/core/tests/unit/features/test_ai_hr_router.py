"""Unit tests for ``/api/v1/ai/hr/*`` L1 aggregate routes (HR-AI-001, Commit 2).

Covers: the L1-only shape (never employee rows), the deterministic narrative
is forwarded from the service, `erp.ai.invoke` + `erp.hr.ai.read` are both
required, and tenant scoping uses the authenticated user's tenant. Auth deps
and the service are stubbed so no DB or ai-agent is needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.deps import (
    get_ai_hr_service,
    get_hr_ai_individual,
    get_quality_service,
)
from core.features.ai.router import get_ai_client
from core.features.ai_hr import router as ai_hr_router
from core.features.ai_hr.attrition_repository import ScoredRisk
from core.features.ai_hr.quality_repository import EmployeeQuality
from core.features.ai_hr.repository import (
    DepartmentCount,
    HeadcountPoint,
    Overview,
    TenureBand,
    TenureSummary,
)

if TYPE_CHECKING:
    from core.features.ai_hr.quality_service import QualityService

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ACTOR_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
EMP_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


class _FakeService:
    def __init__(self) -> None:
        self.overview_calls: list[uuid.UUID] = []
        self.tenure_calls: list[uuid.UUID] = []
        self.attrition_calls: list[uuid.UUID] = []
        self.ack_calls: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = []
        self.attrition_result: list[ScoredRisk] = []
        self.ack_error: Exception | None = None

    async def overview(self, tenant_id: uuid.UUID) -> Overview:
        self.overview_calls.append(tenant_id)
        return Overview(
            total_headcount=5,
            trend=[HeadcountPoint(year=2026, month=1, hires=2)],
            departments=[
                DepartmentCount(department_id=None, department_name="Unassigned", count=5)
            ],
            tenure_bands=[TenureBand(band="1-3", count=3), TenureBand(band="<1", count=2)],
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            narrative="Headcount is 5 across the tenant.",
        )

    async def tenure(self, tenant_id: uuid.UUID) -> TenureSummary:
        self.tenure_calls.append(tenant_id)
        return TenureSummary(
            total_headcount=5,
            bands=[TenureBand(band="1-3", count=3)],
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            narrative="Tenure is concentrated at 1-3 years (60.0%).",
        )

    async def attrition(self, tenant_id: uuid.UUID, *, scorer: object) -> list[ScoredRisk]:
        self.attrition_calls.append(tenant_id)
        return self.attrition_result

    async def acknowledge(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID, *, actor_user_id: uuid.UUID
    ) -> None:
        if self.ack_error is not None:
            raise self.ack_error
        self.ack_calls.append((tenant_id, employee_id, actor_user_id))


def _risk() -> ScoredRisk:
    return ScoredRisk(
        employee_id=EMP_ID,
        department_id=None,
        score=0.91,
        risk_band="high",
        confidence=0.98,
        factors=[{"feature": "tenure", "contribution": 0.05, "direction": "increases"}],
        model_version="v1-gbc-2026-08",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        employee_number="E-101",
        first_name="Ada",
        last_name="Lovelace",
        department_name="Eng",
    )


def _build_app(service: _FakeService) -> tuple[TestClient, FastAPI]:
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[get_ai_hr_service] = lambda: service
    return TestClient(app), app


def test_overview_requires_both_permissions_and_envelopes_l1_shape() -> None:
    service = _FakeService()
    client, _ = _build_app(service)
    resp = client.get("/api/v1/ai/hr/overview", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert service.overview_calls == [TENANT_ID]
    body = resp.json()["data"]
    assert body["total_headcount"] == 5
    assert body["trend"][0]["hires"] == 2
    # L1 shape: aggregate counts only, no employee identifiers/names.
    assert set(body) == {
        "total_headcount",
        "trend",
        "departments",
        "tenure_bands",
        "generated_at",
        "narrative",
    }
    assert body["narrative"] == "Headcount is 5 across the tenant."
    assert "generated_at" in body


def test_tenure_returns_bands_and_narrative() -> None:
    service = _FakeService()
    client, _ = _build_app(service)
    resp = client.get("/api/v1/ai/hr/tenure", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert service.tenure_calls == [TENANT_ID]
    data = resp.json()["data"]
    assert data["total_headcount"] == 5
    assert data["bands"] == [{"band": "1-3", "count": 3}]
    assert data["narrative"] == "Tenure is concentrated at 1-3 years (60.0%)."


def test_both_permission_guards_are_exercised() -> None:
    service = _FakeService()
    client, app = _build_app(service)
    hit: list[str] = []

    def spy_invoke() -> dict[str, object]:
        hit.append("invoke")
        return {"tenant_id": TENANT_ID}

    def spy_read() -> dict[str, object]:
        hit.append("read")
        return {"tenant_id": TENANT_ID}

    app.dependency_overrides[ai_hr_router._require_ai_invoke] = spy_invoke
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = spy_read
    client.get("/api/v1/ai/hr/overview", headers={"authorization": "Bearer tok"})

    assert hit == ["invoke", "read"]


def _build_attrition_app(service: _FakeService, *, individual: bool) -> TestClient:
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_acknowledge] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": ACTOR_ID,
    }
    app.dependency_overrides[get_ai_hr_service] = lambda: service
    app.dependency_overrides[get_ai_client] = lambda: httpx.AsyncClient()
    app.dependency_overrides[get_hr_ai_individual] = lambda: individual
    return TestClient(app)


def test_attrition_returns_l2_per_employee_when_individual_held() -> None:
    service = _FakeService()
    service.attrition_result = [_risk()]
    client = _build_attrition_app(service, individual=True)

    resp = client.get("/api/v1/ai/hr/attrition", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert service.attrition_calls == [TENANT_ID]
    body = resp.json()["data"]
    assert body["model_version"] == "v1-gbc-2026-08"
    emp = body["employees"][0]
    assert emp["employee_id"] == str(EMP_ID)
    assert emp["name"] == "Ada Lovelace"
    assert emp["department_name"] == "Eng"
    assert emp["risk_band"] == "high"
    assert emp["factors"] == [{"feature": "tenure", "contribution": 0.05, "direction": "increases"}]
    assert emp["acknowledged"] is False
    assert emp["acknowledged_by"] is None


def test_attrition_without_individual_returns_403_with_l1_aggregate_body() -> None:
    service = _FakeService()
    service.attrition_result = [
        _risk(),
        ScoredRisk(
            employee_id=EMP_ID,
            department_id=None,
            score=0.2,
            risk_band="low",
            confidence=0.9,
            factors=[],
            model_version="v1-gbc-2026-08",
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            department_name="Eng",
        ),
    ]
    client = _build_attrition_app(service, individual=False)

    resp = client.get("/api/v1/ai/hr/attrition", headers={"authorization": "Bearer tok"})

    # Gherkin: 403 with aggregates-only body — never empty, never L2 PII.
    assert resp.status_code == 403
    body = resp.json()["data"]
    assert body["high_risk_count"] == 1
    assert body["low_risk_count"] == 1
    assert body["top_risk_departments"][0]["department_name"] == "Eng"
    assert "employees" not in body
    assert "generated_at" in body and "narrative" in body


def test_acknowledge_requires_ack_permission_and_audits() -> None:
    service = _FakeService()
    client = _build_attrition_app(service, individual=False)

    resp = client.post(
        f"/api/v1/ai/hr/attrition/{EMP_ID}/acknowledge",
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 200
    assert service.ack_calls == [(TENANT_ID, EMP_ID, ACTOR_ID)]
    assert resp.json()["data"] == {"status": "acknowledged"}


def _build_copilot_app(
    upstream: httpx.AsyncClient,
) -> tuple[TestClient, FastAPI]:
    """App with the copilot proxy wired to a mock upstream ai-agent client."""
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_copilot] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": ACTOR_ID,
    }
    app.dependency_overrides[get_ai_client] = lambda: upstream
    return TestClient(app), app


def test_copilot_chat_forwards_to_ai_agent_and_relays_response() -> None:
    captured: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"answer": "drafted", "model_used": "m", "latency_ms": 3},
        )

    upstream = httpx.AsyncClient(
        base_url="https://ai-agent.internal",
        transport=httpx.MockTransport(handler),
    )
    client, _ = _build_copilot_app(upstream)

    resp = client.post(
        "/api/v1/ai/hr/copilot/chat",
        headers={"authorization": "Bearer tok", "x-tenant-slug": "acme"},
        json={"message": "How big is our headcount?"},
    )

    assert resp.status_code == 200
    # Upstream path + identity are relayed exactly.
    assert captured["path"] == "/ai/hr/copilot/chat"
    assert captured["auth"] == "Bearer tok"
    assert resp.json() == {"answer": "drafted", "model_used": "m", "latency_ms": 3}


def test_copilot_requires_copilot_permission() -> None:
    upstream = httpx.AsyncClient(
        base_url="https://ai-agent.internal",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"answer": "ok", "latency_ms": 1})
        ),
    )
    client, app = _build_copilot_app(upstream)
    hit: list[str] = []

    def spy_invoke() -> dict[str, object]:
        hit.append("invoke")
        return {"tenant_id": TENANT_ID}

    def spy_copilot() -> dict[str, object]:
        hit.append("copilot")
        return {"tenant_id": TENANT_ID, "user_id": ACTOR_ID}

    app.dependency_overrides[ai_hr_router._require_ai_invoke] = spy_invoke
    app.dependency_overrides[ai_hr_router._require_hr_ai_copilot] = spy_copilot

    client.post(
        "/api/v1/ai/hr/copilot/chat",
        headers={"authorization": "Bearer tok", "x-tenant-slug": "acme"},
        json={"message": "hello"},
    )

    assert hit == ["invoke", "copilot"]


# -- /quality/list (L2 admin drill-down, HR-AI-002 8.1.3) --------------------


def _quality_row(score: float, grade: str) -> EmployeeQuality:
    return EmployeeQuality(
        employee_id=EMP_ID,
        department_id=None,
        score=score,
        grade=grade,
        mandatory_score=0.3,
        contact_score=0.15,
        document_score=0.05,
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        employee_number="E-101",
        first_name="Ada",
        last_name="Lovelace",
        department_name="Eng",
    )


class _FakeQualityService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.rows: list[EmployeeQuality] = [_quality_row(0.5, "D")]
        self.refresh_calls: list[uuid.UUID] = []
        self.last_refresh: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    async def list_scores(
        self, tenant_id: uuid.UUID, *, limit: int = 100, offset: int = 0
    ) -> list[EmployeeQuality]:
        assert tenant_id == TENANT_ID
        self.calls.append((limit, offset))
        return self.rows

    async def recalculate(self, tenant_id: uuid.UUID, *, force: bool = True) -> int:
        assert force is True
        self.refresh_calls.append(tenant_id)
        return len(self.rows)

    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None:
        return self.last_refresh


def _build_quality_app(service: QualityService, *, individual: bool) -> TestClient:
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[get_quality_service] = lambda: service
    app.dependency_overrides[get_hr_ai_individual] = lambda: individual
    return TestClient(app)


def test_quality_list_returns_per_employee_rows_when_individual_held() -> None:
    service = _FakeQualityService()
    client = _build_quality_app(service, individual=True)

    resp = client.get(
        "/api/v1/ai/hr/quality/list",
        params={"limit": 20, "offset": 5},
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 200
    assert service.calls == [(20, 5)]
    row = resp.json()["data"][0]
    assert row["employee_id"] == str(EMP_ID)
    assert row["name"] == "Ada Lovelace"
    assert row["grade"] == "D"
    assert row["score"] == 0.5
    assert set(row["issues"]) == {"mandatory", "contact", "document"}


def test_quality_list_without_individual_returns_403() -> None:
    service = _FakeQualityService()
    client = _build_quality_app(service, individual=False)

    resp = client.get(
        "/api/v1/ai/hr/quality/list",
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 403
    assert "individual" in resp.json()["data"]["detail"]


# -- /quality/refresh (weekly recalc maintenance, HR-AI-002 8.1.3) ------------


def test_quality_refresh_forces_recompute_and_returns_l1_body() -> None:
    service = _FakeQualityService()
    client = _build_quality_app(service, individual=True)

    resp = client.post("/api/v1/ai/hr/quality/refresh", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert service.refresh_calls == [TENANT_ID]
    body = resp.json()["data"]
    # L1 maintenance shape: aggregate count + run time, never employee rows.
    assert set(body) == {"recount", "generated_at"}
    assert body["recount"] == 1
    parsed = datetime.fromisoformat(body["generated_at"].replace("Z", "+00:00"))
    assert parsed == datetime(2026, 1, 1, tzinfo=UTC)


def test_quality_refresh_exercises_invoke_and_read_guards() -> None:
    service = _FakeQualityService()
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[get_quality_service] = lambda: service
    hit: list[str] = []

    def spy_invoke() -> dict[str, object]:
        hit.append("invoke")
        return {"tenant_id": TENANT_ID}

    def spy_read() -> dict[str, object]:
        hit.append("read")
        return {"tenant_id": TENANT_ID}

    app.dependency_overrides[ai_hr_router._require_ai_invoke] = spy_invoke
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = spy_read
    client = TestClient(app)

    resp = client.post("/api/v1/ai/hr/quality/refresh", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert hit == ["invoke", "read"]
    assert service.refresh_calls == [TENANT_ID]
