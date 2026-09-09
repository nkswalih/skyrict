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
    get_l3_repository,
    get_quality_service,
)
from core.core.exceptions import SkyrictError, skyrict_error_handler
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

    # Gherkin: 403 with aggregates-only body - never empty, never L2 PII.
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
    assert captured["path"] == "/api/v1/ai/hr/copilot/chat"
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


# ---------------------------------------------------------------------------
# Payroll anomaly endpoints (HR-AI-001, Unit B)
# ---------------------------------------------------------------------------


class _FakePayrollAnomalyService:
    def __init__(self) -> None:
        self.org_calls: list[uuid.UUID] = []
        self.employee_calls: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.disposition_calls: list[tuple[uuid.UUID, uuid.UUID, str, uuid.UUID]] = []

    async def org_feed(self, tenant_id: uuid.UUID) -> object:
        self.org_calls.append(tenant_id)
        from core.features.ai_hr.payroll_anomaly_service import PayrollAnomalyOrgSummary

        return PayrollAnomalyOrgSummary(
            total_anomalies=4,
            open_anomalies=2,
            by_type={"net_pay_delta": 2, "ghost_employee": 1, "duplicate_account": 1},
            by_severity={"medium": 3, "critical": 1},
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            narrative="2 open payroll anomaly(-ies) ...",
        )

    async def employee_anomalies(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[object]:
        self.employee_calls.append((tenant_id, employee_id))
        return [_payroll_anomaly()]

    async def set_disposition(
        self,
        tenant_id: uuid.UUID,
        anomaly_id: uuid.UUID,
        *,
        status: str,
        actor_user_id: uuid.UUID,
    ) -> object:
        self.disposition_calls.append((tenant_id, anomaly_id, status, actor_user_id))
        return _payroll_anomaly(status=status)


def _payroll_anomaly(*, status: str = "open") -> object:
    from core.features.ai_hr.payroll_anomaly_repository import PayrollAnomaly

    return PayrollAnomaly(
        run_id=EMP_ID,
        employee_id=TENANT_ID,
        anomaly_type="net_pay_delta",
        severity="medium",
        status=status,
        title="Unusual change in net pay",
        description="1.75x swing.",
        evidence={"current_run": "PR-2026-04", "ratio": 1.75},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        anomaly_id=ACTOR_ID,
        department_name="Eng",
    )


def _build_payroll_app(service: _FakePayrollAnomalyService, *, individual: bool) -> TestClient:
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_acknowledge] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": ACTOR_ID,
    }
    from core.api.deps import get_payroll_anomaly_service

    app.dependency_overrides[get_payroll_anomaly_service] = lambda: service
    app.dependency_overrides[get_hr_ai_individual] = lambda: individual
    return TestClient(app)


def test_payroll_anomaly_org_feed_returns_l1_aggregate() -> None:
    service = _FakePayrollAnomalyService()
    client = _build_payroll_app(service, individual=False)

    resp = client.get("/api/v1/ai/hr/alerts/payroll", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert service.org_calls == [TENANT_ID]
    body = resp.json()["data"]
    assert body["total_anomalies"] == 4
    assert body["open_anomalies"] == 2
    assert body["by_type"]["ghost_employee"] == 1
    assert body["by_severity"]["critical"] == 1
    assert "narrative" in body


def test_payroll_anomaly_employee_feed_403_without_individual() -> None:
    service = _FakePayrollAnomalyService()
    client = _build_payroll_app(service, individual=False)

    resp = client.get(
        f"/api/v1/ai/hr/alerts/payroll/{TENANT_ID}",
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 403
    assert service.employee_calls == []


def test_payroll_anomaly_employee_feed_200_with_individual() -> None:
    service = _FakePayrollAnomalyService()
    client = _build_payroll_app(service, individual=True)

    resp = client.get(
        f"/api/v1/ai/hr/alerts/payroll/{TENANT_ID}",
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 200
    assert service.employee_calls == [(TENANT_ID, TENANT_ID)]
    row = resp.json()["data"][0]
    assert row["anomaly_type"] == "net_pay_delta"
    assert row["severity"] == "medium"
    assert row["anomaly_id"] == str(ACTOR_ID)
    assert row["department_name"] == "Eng"


def test_payroll_anomaly_disposition_requires_ack_permission_and_returns_updated() -> None:
    service = _FakePayrollAnomalyService()
    client = _build_payroll_app(service, individual=False)

    resp = client.post(
        f"/api/v1/ai/hr/alerts/payroll/{ACTOR_ID}/disposition",
        json={"status": "acknowledged"},
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 200
    assert service.disposition_calls == [(TENANT_ID, ACTOR_ID, "acknowledged", ACTOR_ID)]
    assert resp.json()["data"]["status"] == "acknowledged"


# Compliance engine v1 endpoints (HR-AI-001, Unit C)
# ---------------------------------------------------------------------------


class _FakeComplianceService:
    def __init__(self) -> None:
        self.org_calls: list[uuid.UUID] = []
        self.employee_calls: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.status_calls: list[tuple[uuid.UUID, uuid.UUID, str, uuid.UUID]] = []

    async def org_feed(self, tenant_id: uuid.UUID) -> object:
        self.org_calls.append(tenant_id)
        from core.features.ai_hr.compliance_service import ComplianceOrgSummary, ComplianceRiskGroup

        return ComplianceOrgSummary(
            total_findings=3,
            open_findings=2,
            by_type={
                "document_expiry": 1,
                "training_overdue": 1,
                "contract_missing_field": 1,
            },
            by_severity={"high": 1, "medium": 1, "low": 1},
            risk_ranked=[
                ComplianceRiskGroup(
                    check_type="document_expiry",
                    weighted_open_score=3,
                    open_count=1,
                    total_count=1,
                ),
                ComplianceRiskGroup(
                    check_type="training_overdue",
                    weighted_open_score=1,
                    open_count=1,
                    total_count=1,
                ),
            ],
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            narrative="2 open compliance finding(-ies) ...",
        )

    async def employee_findings(self, tenant_id: uuid.UUID, employee_id: uuid.UUID) -> list[object]:
        self.employee_calls.append((tenant_id, employee_id))
        return [_compliance_finding()]

    async def set_status(
        self,
        tenant_id: uuid.UUID,
        check_id: uuid.UUID,
        *,
        status: str,
        actor_user_id: uuid.UUID,
    ) -> object:
        self.status_calls.append((tenant_id, check_id, status, actor_user_id))
        return _compliance_finding(status=status)


def _compliance_finding(*, status: str = "open") -> object:
    from core.features.ai_hr.compliance_repository import ComplianceFindingRow

    return ComplianceFindingRow(
        employee_id=EMP_ID,
        check_type="document_expiry",
        severity="high",
        owner_rule="compliance_officer",
        status=status,
        title="Identity document expiring",
        description="Visa document has expired (5 day(s) past due).",
        evidence={"doc_type": "visa", "days_left": -5},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        check_id=ACTOR_ID,
        owner_user_id=ACTOR_ID if status == "acknowledged" else None,
        department_name="Eng",
    )


def _build_compliance_app(service: _FakeComplianceService, *, individual: bool) -> TestClient:
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_read] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_ai_acknowledge] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": ACTOR_ID,
    }
    from core.api.deps import get_compliance_service

    app.dependency_overrides[get_compliance_service] = lambda: service
    app.dependency_overrides[get_hr_ai_individual] = lambda: individual
    return TestClient(app)


def test_compliance_org_feed_returns_l1_aggregate() -> None:
    service = _FakeComplianceService()
    client = _build_compliance_app(service, individual=False)

    resp = client.get("/api/v1/ai/hr/alerts/compliance", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert service.org_calls == [TENANT_ID]
    body = resp.json()["data"]
    assert body["total_findings"] == 3
    assert body["open_findings"] == 2
    assert body["by_type"]["document_expiry"] == 1
    assert body["by_type"]["contract_missing_field"] == 1
    assert body["by_severity"]["high"] == 1
    assert "narrative" in body
    assert body["risk_ranked"][0]["check_type"] == "document_expiry"
    assert body["risk_ranked"][0]["weighted_open_score"] == 3
    assert body["risk_ranked"][1]["check_type"] == "training_overdue"


def test_compliance_employee_feed_403_without_individual() -> None:
    service = _FakeComplianceService()
    client = _build_compliance_app(service, individual=False)

    resp = client.get(
        f"/api/v1/ai/hr/alerts/compliance/{TENANT_ID}",
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 403
    assert service.employee_calls == []


def test_compliance_employee_feed_200_with_individual() -> None:
    service = _FakeComplianceService()
    client = _build_compliance_app(service, individual=True)

    resp = client.get(
        f"/api/v1/ai/hr/alerts/compliance/{TENANT_ID}",
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 200
    assert service.employee_calls == [(TENANT_ID, TENANT_ID)]
    row = resp.json()["data"][0]
    assert row["check_type"] == "document_expiry"
    assert row["severity"] == "high"
    assert row["owner_rule"] == "compliance_officer"
    assert row["check_id"] == str(ACTOR_ID)
    assert row["department_name"] == "Eng"


def test_compliance_status_requires_ack_permission_and_returns_updated() -> None:
    service = _FakeComplianceService()
    client = _build_compliance_app(service, individual=False)

    resp = client.post(
        f"/api/v1/ai/hr/alerts/compliance/{ACTOR_ID}/status",
        json={"status": "acknowledged"},
        headers={"authorization": "Bearer tok"},
    )

    assert resp.status_code == 200
    assert service.status_calls == [(TENANT_ID, ACTOR_ID, "acknowledged", ACTOR_ID)]
    assert resp.json()["data"]["status"] == "acknowledged"


# ---------------------------------------------------------------------------
# L3 payroll-cost source data (HR-AI-003)
# ---------------------------------------------------------------------------


class _FakeL3Repository:
    def __init__(self) -> None:
        self.result: object | None = None
        self.pairs: list[object] = []
        self.calls: list[uuid.UUID] = []
        self.pair_calls: list[uuid.UUID] = []

    async def payroll_cost_movement(self, tenant_id: uuid.UUID) -> object | None:
        self.calls.append(tenant_id)
        return self.result

    async def leave_pay_pairs(self, tenant_id: uuid.UUID, *, limit: int = 12) -> list[object]:
        self.pair_calls.append(tenant_id)
        return self.pairs


def _l3_movement() -> object:
    from datetime import date
    from decimal import Decimal

    from core.features.ai_hr.l3_repository import (
        DepartmentCostDelta,
        PayrollCostMovement,
        RunPeriod,
    )

    return PayrollCostMovement(
        current_period=RunPeriod(date(2026, 3, 1), date(2026, 3, 31), "PR-2026-03"),
        previous_period=RunPeriod(date(2026, 2, 1), date(2026, 2, 28), "PR-2026-02"),
        current_headcount=12,
        previous_headcount=12,
        headcount_delta=0,
        current_gross=Decimal("132400.00"),
        previous_gross=Decimal("118000.00"),
        gross_delta=Decimal("14400.00"),
        current_net=Decimal("105520.00"),
        previous_net=Decimal("96400.00"),
        net_delta=Decimal("9120.00"),
        current_overtime=Decimal("21600.00"),
        previous_overtime=Decimal("0.00"),
        overtime_delta=Decimal("21600.00"),
        current_benefit_adjustments=Decimal("500.00"),
        previous_benefit_adjustments=Decimal("0.00"),
        benefit_delta=Decimal("500.00"),
        department_breakdown=[
            DepartmentCostDelta("Operations", Decimal("52060.00"), Decimal("41400.00"),
                                Decimal("10660.00")),
            DepartmentCostDelta("Engineering", Decimal("53460.00"), Decimal("55000.00"),
                                Decimal("-1540.00")),
        ],
    )


def _l3_app(repo: _FakeL3Repository) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(SkyrictError, skyrict_error_handler)
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_ai_invoke] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": ACTOR_ID,
    }
    app.dependency_overrides[ai_hr_router._require_hr_ai_management] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": ACTOR_ID,
    }
    app.dependency_overrides[get_l3_repository] = lambda: repo
    return TestClient(app)


def test_l3_payroll_cost_returns_movement_with_string_money() -> None:
    repo = _FakeL3Repository()
    repo.result = _l3_movement()
    client = _l3_app(repo)

    resp = client.get("/api/v1/ai/hr/l3/payroll-cost", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert repo.calls == [TENANT_ID]
    body = resp.json()["data"]
    assert body["current_run_code"] == "PR-2026-03"
    assert body["previous_run_code"] == "PR-2026-02"
    assert body["net_delta"] == "9120.00"
    assert body["overtime_delta"] == "21600.00"
    assert body["benefit_delta"] == "500.00"
    assert body["current_benefit_adjustments"] == "500.00"
    assert body["headcount_delta"] == 0
    assert body["department_breakdown"][0]["department_name"] == "Operations"
    assert body["department_breakdown"][0]["net_delta"] == "10660.00"


def test_l3_payroll_cost_insufficient_history_is_404() -> None:
    repo = _FakeL3Repository()
    repo.result = None
    client = _l3_app(repo)

    resp = client.get("/api/v1/ai/hr/l3/payroll-cost", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 404


def _l3_pair() -> object:
    from datetime import date
    from decimal import Decimal

    from core.features.ai_hr.l3_repository import LeavePayPair

    return LeavePayPair(
        period_start=date(2026, 3, 1),
        run_code="PR-2026-03",
        leave_days=10,
        overtime=Decimal("1500.00"),
    )


def test_l3_leave_pay_correlation_returns_pairs_with_string_money() -> None:
    repo = _FakeL3Repository()
    repo.pairs = [_l3_pair()]
    client = _l3_app(repo)

    resp = client.get("/api/v1/ai/hr/l3/leave-pay-correlation", headers={"authorization": "Bearer tok"})

    assert resp.status_code == 200
    assert repo.pair_calls == [TENANT_ID]
    body = resp.json()["data"]
    assert body["pairs"][0]["run_code"] == "PR-2026-03"
    assert body["pairs"][0]["leave_days"] == 10
    assert body["pairs"][0]["overtime"] == "1500.00"
