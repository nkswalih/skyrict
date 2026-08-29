"""Unit tests for the AI pattern-engine config (holidays + blackouts, 0024).

Covers the write/read endpoints (gated by ``erp.hr.read`` / ``erp.hr.write``),
tenant scoping, delete semantics, and the repository's input validation
(empty name/reason, inverted blackout range). Pure unit tests: the router
wires a fake repository and overrides the permission guards directly (no DB).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.api.deps import get_pattern_data_repository
from core.core.exceptions import skyrict_error_handler
from core.features.ai_hr import router as ai_hr_router
from core.features.ai_hr.pattern_data_repository import (
    AiHrPatternDataRepository,
    LeaveBlackoutPeriod,
    PublicHoliday,
)
from skyrict_common.exceptions import SkyrictError

pytestmark = pytest.mark.unit

TENANT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEPT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
_NOW = datetime(2026, 8, 29, tzinfo=UTC)


class _FakePatternRepo:
    def __init__(self) -> None:
        self.holidays: list[PublicHoliday] = []
        self.blackouts: list[LeaveBlackoutPeriod] = []
        self.read_calls: list[uuid.UUID] = []
        self.write_ops: list[tuple[str, uuid.UUID]] = []

    async def create_holiday(
        self, tenant_id: uuid.UUID, calendar_date: date, name: str, *, department_id=None
    ) -> PublicHoliday:
        self.write_ops.append(("holiday_create", tenant_id))
        row = PublicHoliday(
            holiday_id=uuid.uuid4(),
            calendar_date=calendar_date,
            name=name,
            department_id=department_id,
            created_at=_NOW,
        )
        self.holidays.append(row)
        return row

    async def delete_holiday(self, tenant_id: uuid.UUID, holiday_id: uuid.UUID) -> bool:
        self.write_ops.append(("holiday_delete", tenant_id))
        before = len(self.holidays)
        self.holidays = [h for h in self.holidays if h.holiday_id != holiday_id]
        return len(self.holidays) < before

    async def list_holidays(self, tenant_id: uuid.UUID) -> list[PublicHoliday]:
        self.read_calls.append(tenant_id)
        return list(self.holidays)

    async def create_blackout(
        self,
        tenant_id: uuid.UUID,
        start_date: date,
        end_date: date,
        reason: str,
        *,
        department_id=None,
    ) -> LeaveBlackoutPeriod:
        self.write_ops.append(("blackout_create", tenant_id))
        row = LeaveBlackoutPeriod(
            blackout_id=uuid.uuid4(),
            start_date=start_date,
            end_date=end_date,
            department_id=department_id,
            reason=reason,
            created_at=_NOW,
        )
        self.blackouts.append(row)
        return row

    async def delete_blackout(self, tenant_id: uuid.UUID, blackout_id: uuid.UUID) -> bool:
        self.write_ops.append(("blackout_delete", tenant_id))
        before = len(self.blackouts)
        self.blackouts = [b for b in self.blackouts if b.blackout_id != blackout_id]
        return len(self.blackouts) < before

    async def list_blackouts(self, tenant_id: uuid.UUID) -> list[LeaveBlackoutPeriod]:
        self.read_calls.append(tenant_id)
        return list(self.blackouts)


def _build_app(repo: _FakePatternRepo) -> tuple[TestClient, FastAPI]:
    app = FastAPI()
    app.add_exception_handler(SkyrictError, skyrict_error_handler)
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[ai_hr_router._require_hr_read] = lambda: {"tenant_id": TENANT_ID}
    app.dependency_overrides[ai_hr_router._require_hr_write] = lambda: {
        "tenant_id": TENANT_ID,
        "user_id": uuid.uuid4(),
    }
    app.dependency_overrides[get_pattern_data_repository] = lambda: repo
    return TestClient(app), app


# -- holidays ----------------------------------------------------------------


async def test_list_holidays_returns_stored_rows_under_read_gate() -> None:
    repo = _FakePatternRepo()
    client, _ = _build_app(repo)
    await repo.create_holiday(TENANT_ID, date(2026, 8, 31), "National Day")

    resp = client.get("/api/v1/ai/hr/pattern-data/holidays", headers={"authorization": "Bearer t"})

    assert resp.status_code == 200
    body = resp.json()["data"]
    assert len(body) == 1
    assert body[0]["name"] == "National Day"
    assert body[0]["calendar_date"] == "2026-08-31"
    assert body[0]["department_id"] is None
    assert repo.read_calls == [TENANT_ID]


def test_create_holiday_envelopes_created_row_and_scopes_tenant() -> None:
    repo = _FakePatternRepo()
    client, _ = _build_app(repo)

    resp = client.post(
        "/api/v1/ai/hr/pattern-data/holidays",
        headers={"authorization": "Bearer t"},
        json={"calendar_date": "2026-12-25", "name": "Christmas Day"},
    )

    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["name"] == "Christmas Day"
    assert body["calendar_date"] == "2026-12-25"
    assert repo.write_ops == [("holiday_create", TENANT_ID)]
    assert len(repo.holidays) == 1


async def test_delete_holiday_removes_row_and_404s_for_unknown() -> None:
    repo = _FakePatternRepo()
    client, _ = _build_app(repo)
    existing = await repo.create_holiday(TENANT_ID, date(2026, 9, 16), "Malaysia Day")
    unknown = uuid.uuid4()

    ok_resp = client.delete(
        f"/api/v1/ai/hr/pattern-data/holidays/{existing.holiday_id}",
        headers={"authorization": "Bearer t"},
    )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["data"] == {"deleted": True}
    assert repo.holidays == []

    missing_resp = client.delete(
        f"/api/v1/ai/hr/pattern-data/holidays/{unknown}",
        headers={"authorization": "Bearer t"},
    )
    assert missing_resp.status_code == 404


def test_pattern_read_gate_is_exercised() -> None:
    app = FastAPI()
    app.include_router(ai_hr_router.router, prefix="/api/v1")
    app.dependency_overrides[get_pattern_data_repository] = lambda: _FakePatternRepo()
    app.dependency_overrides[ai_hr_router._require_hr_write] = lambda: {"tenant_id": TENANT_ID}
    hit: list[str] = []

    def spy_read() -> dict[str, object]:
        hit.append("read")
        return {"tenant_id": TENANT_ID}

    app.dependency_overrides[ai_hr_router._require_hr_read] = spy_read
    TestClient(app).get(
        "/api/v1/ai/hr/pattern-data/holidays", headers={"authorization": "Bearer t"}
    )
    assert hit == ["read"]


# -- blackouts ---------------------------------------------------------------


def test_create_blackout_scopes_tenant_and_persists() -> None:
    repo = _FakePatternRepo()
    client, _ = _build_app(repo)

    resp = client.post(
        "/api/v1/ai/hr/pattern-data/blackouts",
        headers={"authorization": "Bearer t"},
        json={
            "start_date": "2026-12-20",
            "end_date": "2026-12-31",
            "reason": "Year-end financial close",
            "department_id": str(DEPT_ID),
        },
    )

    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["reason"] == "Year-end financial close"
    assert body["start_date"] == "2026-12-20"
    assert body["end_date"] == "2026-12-31"
    assert body["department_id"] == str(DEPT_ID)
    assert repo.write_ops == [("blackout_create", TENANT_ID)]
    assert len(repo.blackouts) == 1
    assert repo.blackouts[0].department_id == DEPT_ID


async def test_list_blackouts_returns_rows() -> None:
    repo = _FakePatternRepo()
    client, _ = _build_app(repo)
    await repo.create_blackout(TENANT_ID, date(2026, 12, 20), date(2026, 12, 31), "Close")

    resp = client.get("/api/v1/ai/hr/pattern-data/blackouts", headers={"authorization": "Bearer t"})

    assert resp.status_code == 200
    rows = resp.json()["data"]
    assert len(rows) == 1
    assert rows[0]["reason"] == "Close"
    assert repo.read_calls == [TENANT_ID]


# -- repository validation (no session needed for the failing paths) ---------


async def test_create_holiday_rejects_blank_name_without_session() -> None:
    repo = AiHrPatternDataRepository(session=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="holiday name cannot be empty"):
        await repo.create_holiday(TENANT_ID, date(2026, 1, 1), "   ")


async def test_create_blackout_rejects_inverted_range_without_session() -> None:
    repo = AiHrPatternDataRepository(session=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="end_date cannot precede start_date"):
        await repo.create_blackout(TENANT_ID, date(2026, 12, 31), date(2026, 12, 20), "Close")


async def test_create_blackout_rejects_blank_reason_without_session() -> None:
    repo = AiHrPatternDataRepository(session=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="blackout reason cannot be empty"):
        await repo.create_blackout(TENANT_ID, date(2026, 1, 1), date(2026, 1, 2), "   ")
