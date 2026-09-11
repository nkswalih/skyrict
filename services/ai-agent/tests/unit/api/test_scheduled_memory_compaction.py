"""Unit tests for the scheduled weekly per-tenant memory compaction job.

Exercises ``compact_all_tenants`` orchestration with fakes for the session
factory and a stub compact factory; the service + repository paths are
covered by the memory compaction tests and integration suite respectively.
"""

from __future__ import annotations

import uuid

from ai_agent.api.scheduled.memory_compaction import compact_all_tenants
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


class TestCompactAllTenants:
    async def test_skips_when_no_active_tenants(self) -> None:
        await compact_all_tenants(
            session_factory=_session_factory([]),  # type: ignore[arg-type]
        )

    async def test_compacts_each_tenant_with_context_and_isolates_failures(self) -> None:
        record: dict = {"compacted": [], "ctx": [], "slug": [], "llm": []}

        async def stub_compact(**kwargs: object) -> None:
            assert kwargs["tenant_id"]
            TenantContext.set(str(kwargs["tenant_id"]))
            TenantContext.set_tenant_slug(kwargs["tenant_slug"])
            if kwargs["tenant_id"] == TENANT_A:
                raise RuntimeError("repo unreachable")
            record["compacted"].append(kwargs["tenant_id"])
            record["ctx"].append(TenantContext.get())
            record["slug"].append(kwargs["tenant_slug"])
            record["llm"].append(kwargs["llm_router"])

        tenants = [_tenant("acme", TENANT_A), _tenant("globex", TENANT_B)]
        await compact_all_tenants(
            session_factory=_session_factory(tenants),  # type: ignore[arg-type]
            compact_factory=stub_compact,  # type: ignore[arg-type]
            llm_router=_ROUTER,
        )

        # TENANT_A raised; the pass must continue to TENANT_B.
        assert record["compacted"] == [TENANT_B]
        assert record["ctx"] == [str(TENANT_B)]
        assert record["slug"] == ["globex"]
        assert record["llm"] == [_ROUTER]
