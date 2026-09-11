"""Unit tests for the weekly revenue-forecast scheduler (SKY-82 A4).

Pins the narrator-cloned contract: ``_run_all`` refreshes every enabled
tenant and a single tenant failing never bubbles out of the cron.
"""

from __future__ import annotations

import uuid

from ai_agent.features.revenue_forecast.scheduler import RevenueForecastScheduler

TENANT_A = uuid.UUID("22222222-2222-2222-2222-222222222222")
TENANT_B = uuid.UUID("33333333-3333-3333-3333-333333333333")


async def test_run_all_refreshes_every_enabled_tenant() -> None:
    refreshed: list[uuid.UUID] = []

    async def tenant_provider() -> list[tuple[uuid.UUID, str]]:
        return [(TENANT_A, "a"), (TENANT_B, "b")]

    async def refresh_factory(tenant_id: uuid.UUID, slug: str):
        def make() -> object:
            return object()

        async def refresh() -> None:
            refreshed.append(tenant_id)

        return refresh

    scheduler = RevenueForecastScheduler(
        tenant_provider=tenant_provider,
        refresh_factory=refresh_factory,
        day_of_week="mon",
        hour=6,
        minute=0,
        timezone="UTC",
    )
    await scheduler._run_all()
    assert refreshed == [TENANT_A, TENANT_B]


async def test_run_all_survives_a_tenant_failure() -> None:
    refreshed: list[uuid.UUID] = []

    async def tenant_provider() -> list[tuple[uuid.UUID, str]]:
        return [(TENANT_A, "a"), (TENANT_B, "b")]

    async def refresh_factory(tenant_id: uuid.UUID, slug: str):
        async def refresh() -> None:
            if tenant_id == TENANT_A:
                raise RuntimeError("core unavailable")
            refreshed.append(tenant_id)

        return refresh

    scheduler = RevenueForecastScheduler(
        tenant_provider=tenant_provider,
        refresh_factory=refresh_factory,
        day_of_week="mon",
        hour=6,
        minute=0,
        timezone="UTC",
    )
    await scheduler._run_all()
    assert refreshed == [TENANT_B]


async def test_start_stop_is_idempotent() -> None:
    async def tenant_provider() -> list[tuple[uuid.UUID, str]]:
        return []

    async def refresh_factory(tenant_id: uuid.UUID, slug: str):
        async def refresh() -> None:
            return None

        return refresh

    scheduler = RevenueForecastScheduler(
        tenant_provider=tenant_provider,
        refresh_factory=refresh_factory,
        day_of_week="mon",
        hour=6,
        minute=0,
        timezone="UTC",
    )
    scheduler.start()
    scheduler.start()  # second start is a no-op
    scheduler.stop()
    scheduler.stop()  # second stop is a no-op
    assert scheduler._scheduler is None
