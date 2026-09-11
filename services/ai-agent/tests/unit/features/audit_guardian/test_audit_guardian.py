"""Unit tests for Audit Guardian watchers and weekly report service (SKY-90).

Watcher rule tests are pure and deterministic. Service tests use fakes for
the report port, audit log readers, and audit service - no DB, no LLM, no
network.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

from ai_agent.features.audit_guardian.service import GuardianReportService
from ai_agent.features.audit_guardian.watchers import (
    FlaggedEvent,
    run_all_watchers,
    watch_auth_bursts,
    watch_bulk_reads,
    watch_off_hours_access,
)

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
TENANT_ID = uuid.uuid4()
REPORT_ID = uuid.uuid4()
SOURCE_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Watcher rules
# ---------------------------------------------------------------------------


def _event(
    *, event_id: str, action: str, created_at: datetime, user_id: str = "u1"
) -> dict[str, Any]:
    return {
        "id": event_id,
        "action": action,
        "created_at": created_at.isoformat(),
        "user_id": user_id,
    }


class TestWatchOffHoursAccess:
    def test_business_hours_are_not_flagged(self) -> None:
        events = [_event(event_id="e1", action="inventory.read", created_at=NOW)]
        flagged = watch_off_hours_access(events, source_table="ai_audit_log")
        assert flagged == []

    def test_off_hours_read_is_flagged_medium(self) -> None:
        events = [_event(event_id="e1", action="crm.lead.read", created_at=NOW.replace(hour=3))]
        flagged = watch_off_hours_access(events, source_table="core_audit_log")
        assert len(flagged) == 1
        assert flagged[0].severity == "medium"
        assert flagged[0].reason

    def test_off_hours_export_is_flagged_high(self) -> None:
        events = [_event(event_id="e1", action="report.export", created_at=NOW.replace(hour=23))]
        flagged = watch_off_hours_access(events, source_table="ai_audit_log")
        assert len(flagged) == 1
        assert flagged[0].severity == "high"

    def test_ignores_unparseable_timestamps(self) -> None:
        events = [
            {
                "id": "e1",
                "action": "inventory.read",
                "created_at": "not-a-date",
                "user_id": "u1",
            }
        ]
        flagged = watch_off_hours_access(events, source_table="ai_audit_log")
        assert flagged == []


class TestWatchBulkReads:
    def test_no_flag_under_threshold(self) -> None:
        events = [
            _event(
                event_id=f"e{i}",
                action="inventory.read",
                created_at=NOW + timedelta(minutes=i),
            )
            for i in range(5)
        ]
        flagged = watch_bulk_reads(events, source_table="ai_audit_log")
        assert flagged == []

    def test_flags_when_window_exceeded(self) -> None:
        events = [
            _event(
                event_id=f"e{i}",
                action="inventory.read",
                created_at=NOW + timedelta(seconds=i * 10),
            )
            for i in range(21)
        ]
        flagged = watch_bulk_reads(events, source_table="ai_audit_log")
        assert len(flagged) == 1
        assert flagged[0].severity == "medium"
        assert "21" in flagged[0].reason

    def test_ignores_non_read_actions(self) -> None:
        events = [
            _event(
                event_id=f"e{i}",
                action="inventory.write",
                created_at=NOW + timedelta(seconds=i),
            )
            for i in range(25)
        ]
        flagged = watch_bulk_reads(events, source_table="ai_audit_log")
        assert flagged == []


class TestWatchAuthBursts:
    def test_no_flag_under_threshold(self) -> None:
        events = [
            _event(
                event_id=f"e{i}",
                action="auth.login.failed",
                created_at=NOW + timedelta(minutes=i),
                user_id="u9",
            )
            for i in range(3)
        ]
        flagged = watch_auth_bursts(events, source_table="identity_audit_log")
        assert flagged == []

    def test_flags_burst_from_one_source(self) -> None:
        events = [
            _event(
                event_id=f"e{i}",
                action="auth.login.failed",
                created_at=NOW + timedelta(seconds=i * 30),
                user_id="u9",
            )
            for i in range(6)
        ]
        flagged = watch_auth_bursts(events, source_table="identity_audit_log")
        assert len(flagged) == 1
        assert flagged[0].severity == "high"

    def test_run_all_watchers_with_mixed_events(self) -> None:
        events = [
            _event(event_id="e1", action="crm.lead.read", created_at=NOW.replace(hour=2)),
            _event(event_id="e2", action="inventory.read", created_at=NOW),
        ]
        flagged = run_all_watchers(events, source_table="ai_audit_log")
        assert len(flagged) == 1
        assert flagged[0].event_action == "crm.lead.read"


# ---------------------------------------------------------------------------
# Report service
# ---------------------------------------------------------------------------


class _FakeReportPort:
    def __init__(self) -> None:
        self.reports: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def create_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_week_start: date,
        report_week_end: date,
        summary: str,
        total_events_scanned: int,
        flagged_count: int,
    ) -> uuid.UUID:
        self.reports.append(
            {
                "tenant_id": tenant_id,
                "week_start": report_week_start,
                "week_end": report_week_end,
                "summary": summary,
                "total": total_events_scanned,
                "flagged": flagged_count,
            }
        )
        return REPORT_ID

    async def create_event(
        self,
        *,
        tenant_id: uuid.UUID,
        report_id: uuid.UUID | None,
        source_table: str,
        source_id: uuid.UUID,
        event_action: str,
        severity: str,
        reason: str,
        evidence: dict[str, Any],
    ) -> uuid.UUID:
        self.events.append(
            {
                "tenant_id": tenant_id,
                "report_id": report_id,
                "source_table": source_table,
                "source_id": source_id,
                "action": event_action,
                "severity": severity,
                "reason": reason,
                "evidence": evidence,
            }
        )
        return uuid.uuid4()


class _FakeReader:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    async def read_recent_events(
        self,
        *,
        tenant_id: uuid.UUID,
        since: date,
        source: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return self._events


def _fake_audit() -> Any:
    audit = AsyncMock()
    audit.log = AsyncMock()
    return audit


def _flagged_event(
    *,
    source_table: str = "ai_audit_log",
    action: str = "export_csv",
    severity: str = "high",
) -> FlaggedEvent:
    return FlaggedEvent(
        source_table=source_table,
        source_id=str(SOURCE_ID),
        event_action=action,
        severity=severity,
        reason="test rule fired",
        evidence={"user_id": "u1"},
    )


class TestGuardianReportService:
    async def test_generates_report_with_no_flags(self) -> None:
        reader = _FakeReader(
            [
                {
                    "id": str(SOURCE_ID),
                    "action": "inventory.read",
                    "created_at": NOW.isoformat(),
                    "user_id": "u1",
                    "source_table": "ai_audit_log",
                }
            ]
        )
        repo = _FakeReportPort()
        audit = _fake_audit()
        service = GuardianReportService(report_repo=repo, readers={"ai_agent": reader}, audit=audit)

        result = await service.generate_weekly_report(tenant_id=TENANT_ID)

        assert result["flagged_count"] == 0
        assert result["total_events_scanned"] == 1
        assert repo.reports[0]["total"] == 1
        assert repo.events == []
        audit.log.assert_awaited_once()

    async def test_generates_report_with_flagged_export(self) -> None:
        reader = _FakeReader(
            [
                {
                    "id": str(SOURCE_ID),
                    "action": "report.export",
                    "created_at": NOW.replace(hour=23).isoformat(),
                    "user_id": "u1",
                    "source_table": "ai_audit_log",
                }
            ]
        )
        repo = _FakeReportPort()
        audit = _fake_audit()
        service = GuardianReportService(report_repo=repo, readers={"ai_agent": reader}, audit=audit)

        result = await service.generate_weekly_report(tenant_id=TENANT_ID)

        assert result["flagged_count"] == 1
        assert repo.reports[0]["flagged"] == 1
        assert len(repo.events) == 1
        assert repo.events[0]["severity"] == "high"
        assert repo.events[0]["report_id"] == REPORT_ID
        audit.log.assert_awaited_once()

    async def test_flags_are_partitioned_by_source_table(self) -> None:
        ai_reader = _FakeReader(
            [
                {
                    "id": str(SOURCE_ID),
                    "action": "inventory.read",
                    "created_at": NOW.replace(hour=2).isoformat(),
                    "user_id": "u1",
                    "source_table": "ai_audit_log",
                }
            ]
        )
        core_reader = _FakeReader(
            [
                {
                    "id": str(uuid.uuid4()),
                    "action": "crm.lead.read",
                    "created_at": NOW.replace(hour=1).isoformat(),
                    "user_id": "u2",
                    "source_table": "core_audit_log",
                }
            ]
        )
        repo = _FakeReportPort()
        audit = _fake_audit()
        service = GuardianReportService(
            report_repo=repo,
            readers={"ai_agent": ai_reader, "core": core_reader},
            audit=audit,
        )

        await service.generate_weekly_report(tenant_id=TENANT_ID)

        source_tables = {event["source_table"] for event in repo.events}
        assert source_tables == {"ai_audit_log", "core_audit_log"}
        assert len(repo.events) == 2

    async def test_watcher_grouping_detects_bulk_reads_across_batch(self) -> None:
        events = [
            {
                "id": str(uuid.uuid4()),
                "action": "inventory.read",
                "created_at": (NOW + timedelta(seconds=i * 10)).isoformat(),
                "user_id": "u1",
                "source_table": "ai_audit_log",
            }
            for i in range(21)
        ]
        reader = _FakeReader(events)
        repo = _FakeReportPort()
        audit = _fake_audit()
        service = GuardianReportService(report_repo=repo, readers={"ai_agent": reader}, audit=audit)

        await service.generate_weekly_report(tenant_id=TENANT_ID)

        assert repo.reports[0]["flagged"] == 1
        assert repo.events[0]["action"] == "bulk_read_detected"

    async def test_uses_deterministic_summary_without_providers(self) -> None:
        reader = _FakeReader([])
        repo = _FakeReportPort()
        audit = _fake_audit()
        service = GuardianReportService(report_repo=repo, readers={"ai_agent": reader}, audit=audit)

        result = await service.generate_weekly_report(tenant_id=TENANT_ID)

        assert "No suspicious activity" in result["summary"]
        assert repo.reports[0]["flagged"] == 0
        assert repo.reports[0]["total"] == 0

    async def test_reader_failure_degrades_to_empty(self) -> None:
        class _BoomReader:
            async def read_recent_events(self, **kwargs: Any) -> list[dict[str, Any]]:
                raise RuntimeError("backend down")

        service = GuardianReportService(
            report_repo=_FakeReportPort(),
            readers={"ai_agent": _BoomReader()},
            audit=_fake_audit(),
        )

        result = await service.generate_weekly_report(tenant_id=TENANT_ID)

        assert result["total_events_scanned"] == 0
        assert result["flagged_count"] == 0

    def test_dedupe_keeps_highest_severity_per_event(self) -> None:
        from ai_agent.features.audit_guardian.service import _dedupe_flagged

        low = _flagged_event(action="export_csv", severity="low")
        high = _flagged_event(action="export_csv", severity="high")
        deduped = _dedupe_flagged([low, high])
        assert len(deduped) == 1
        assert deduped[0].severity == "high"
