"""Unit tests for the scheduled weekly per-tenant Guardian report job.

Exercises ``generate_reports_for_all_tenants`` orchestration with fakes for
the session factory and a stub report factory; the service + reader paths are
covered by the guardian service and reader tests respectively.
"""

from __future__ import annotations

import uuid

from ai_agent.api.scheduled.guardian_report import generate_reports_for_all_tenants
from ai_agent.core.tenant_context import TenantContext
from ai_agent.models.tenant import TenantModel

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()

_ROUTER = object()


class _FakeScalars:
    def __init__(self, rows: list[TenantModel]) -> None:
        self._rows = rows

    def all(self) -> list[TenantModel]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[TenantModel]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows: list[TenantModel]) -> None:
        self._rows = rows

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def execute(self, stmt: object) -> _FakeResult:
        return _FakeResult(self._rows)


def _session_factory(rows: list[TenantModel]) -> object:
    def factory() -> _FakeSession:
        return _FakeSession(rows)

    return factory


def _tenant(slug: str, tenant_id: uuid.UUID) -> TenantModel:
    return TenantModel(id=tenant_id, name=slug.title(), slug=slug, plan_tier="free", is_active=True)


class TestGenerateReportsForAllTenants:
    async def test_skips_when_no_active_tenants(self) -> None:
        await generate_reports_for_all_tenants(
            session_factory=_session_factory([]),  # type: ignore[arg-type]
        )

    async def test_reports_each_tenant_with_context_and_isolates_failures(self) -> None:
        record: dict = {"reported": [], "ctx": [], "slug": [], "llm": []}

        async def stub_report(**kwargs: object) -> None:
            assert kwargs["tenant_id"]
            TenantContext.set(str(kwargs["tenant_id"]))
            TenantContext.set_tenant_slug(kwargs["tenant_slug"])
            if kwargs["tenant_id"] == TENANT_A:
                raise RuntimeError("generate failed")
            record["reported"].append(kwargs["tenant_id"])
            record["ctx"].append(TenantContext.get())
            record["slug"].append(kwargs["tenant_slug"])
            record["llm"].append(kwargs["llm_router"])

        tenants = [_tenant("acme", TENANT_A), _tenant("globex", TENANT_B)]
        await generate_reports_for_all_tenants(
            session_factory=_session_factory(tenants),  # type: ignore[arg-type]
            report_factory=stub_report,  # type: ignore[arg-type]
            llm_router=_ROUTER,
        )

        # TENANT_A raised; the pass must continue to TENANT_B.
        assert record["reported"] == [TENANT_B]
        assert record["ctx"] == [str(TENANT_B)]
        assert record["slug"] == ["globex"]
        assert record["llm"] == [_ROUTER]
