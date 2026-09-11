"""Unit tests for the scheduled per-tenant deal-health sweep.

Exercises ``scan_all_tenants`` orchestration with fakes for the session
factory and a stub sweep factory; the engine + repository path is covered by
the CRM service and deal-health engine tests respectively.
"""

from __future__ import annotations

import uuid

from ai_agent.api.scheduled.deal_health_sweep import scan_all_tenants
from ai_agent.core.tenant_context import TenantContext
from ai_agent.models.tenant import TenantModel

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


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


async def _stub_sweep(**kwargs: object) -> None:
    record = kwargs["record"]  # type: ignore[assignment]
    assert isinstance(record, dict)
    TenantContext.set(str(kwargs["tenant_id"]))
    TenantContext.set_tenant_slug(kwargs["tenant_slug"])
    if kwargs["tenant_id"] == TENANT_A:
        raise RuntimeError("core unreachable")
    record["swept"].append(kwargs["tenant_id"])
    record["ctx"].append(TenantContext.get())
    record["slug"].append(kwargs["tenant_slug"])


class TestScanAllTenants:
    async def test_skipped_without_service_token(self) -> None:
        called = False

        def factory():
            nonlocal called
            called = True
            return _FakeSession([])

        await scan_all_tenants(
            service_token="",
            base_url="http://core:8000",
            session_factory=factory,  # type: ignore[arg-type]
        )
        assert called is False, "no session must be opened without a token"

    async def test_skips_when_no_active_tenants(self) -> None:
        await scan_all_tenants(
            service_token="tok",
            base_url="http://core:8000",
            session_factory=_session_factory([]),  # type: ignore[arg-type]
        )

    async def test_sweeps_each_tenant_with_context_and_isolates_failures(self) -> None:
        record: dict = {"swept": [], "ctx": [], "slug": []}
        tenants = [_tenant("acme", TENANT_A), _tenant("globex", TENANT_B)]
        await scan_all_tenants(
            service_token="svc-tok",
            base_url="http://core:8000",
            session_factory=_session_factory(tenants),  # type: ignore[arg-type]
            sweep_factory=lambda **kwargs: _stub_sweep(record=record, **kwargs),  # type: ignore[arg-type]
        )

        # TENANT_A raised; the pass must continue to TENANT_B.
        assert record["swept"] == [TENANT_B]
        assert record["ctx"] == [str(TENANT_B)]
        assert record["slug"] == ["globex"]
