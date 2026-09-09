"""Unit tests for the weekly L3 compliance digest cron (HR-AI-003).

Exercises the scheduler's ``_run_all`` orchestration with fakes for the
tenant provider and service factory; the real repository + gateway + service
paths are covered by the L3 feature tests and the gateway tests.
"""

from __future__ import annotations

import uuid
from datetime import date

from ai_agent.api.scheduled.l3_weekly_digest import L3WeeklyDigestScheduler

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()


class _FakeL3Service:
    def __init__(self, record: dict, tenant_id: uuid.UUID) -> None:
        self._record = record
        self._tenant_id = tenant_id

    async def generate(
        self,
        *,
        kind: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        as_of: date,
        force_refresh: bool,
) -> None:
        self._record["calls"].append(
            {
                "kind": kind,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "as_of": as_of,
                "force_refresh": force_refresh,
            }
        )

    async def commit(self) -> None:
        self._record["commits"].append(self._tenant_id)


async def _build_scheduler(record: dict) -> L3WeeklyDigestScheduler:
    async def tenants() -> list[tuple[uuid.UUID, str]]:
        return [(TENANT_A, "acme"), (TENANT_B, "globex")]

    async def service_factory(tenant_id: uuid.UUID, slug: str) -> _FakeL3Service:
        return _FakeL3Service(record, tenant_id)

    return L3WeeklyDigestScheduler(
        tenant_provider=tenants,
        service_factory=service_factory,  # type: ignore[arg-type]
        day_of_week="mon",
        hour=8,
        minute=0,
        timezone="UTC",
    )


class TestL3WeeklyDigestScheduler:
    async def test_generates_compliance_digest_for_each_tenant(self) -> None:
        record: dict = {"calls": [], "commits": []}
        scheduler = await _build_scheduler(record)

        await scheduler._run_all()

        assert len(record["calls"]) == 2
        for call, tenant_id in zip(record["calls"], [TENANT_A, TENANT_B], strict=True):
            assert call["kind"] == "compliance_digest"
            assert call["tenant_id"] == tenant_id
            assert call["user_id"] is None
            assert call["as_of"] == date.today()
            assert call["force_refresh"] is False
        assert record["commits"] == [TENANT_A, TENANT_B]

    async def test_single_tenant_failure_is_isolated(self) -> None:
        record: dict = {"calls": []}

        async def tenants() -> list[tuple[uuid.UUID, str]]:
            return [(TENANT_A, "acme"), (TENANT_B, "globex")]

        async def flaky_factory(tenant_id: uuid.UUID, slug: str) -> _FakeL3Service:
            if tenant_id == TENANT_A:

                class _BoomService:
                    async def generate(self, **kwargs: object) -> None:
                        raise RuntimeError("core unreachable")

                return _BoomService()  # type: ignore[return-value]
            return _FakeL3Service(record, tenant_id)

        scheduler = L3WeeklyDigestScheduler(
            tenant_provider=tenants,
            service_factory=flaky_factory,  # type: ignore[arg-type]
            day_of_week="mon",
            hour=8,
            minute=0,
            timezone="UTC",
        )

        await scheduler._run_all()

        assert len(record["calls"]) == 1, "pass must continue past failures"
        assert record["calls"][0]["tenant_id"] == TENANT_B
