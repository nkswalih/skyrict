"""Unit tests for the production ``AiAuditLogReader`` (guardian reader).

Checks the event-dict mapping (id/user_id/action/created_at/input/output/
source_table) and the cross-service source guard. The session is faked; the
real query path is covered by the integration suite.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from ai_agent.db.ai_audit_log_reader import AiAuditLogReader
from ai_agent.models.ai_audit_log import AiAuditLogModel

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
NOW = datetime.now(UTC)


class _FakeScalars:
    def __init__(self, rows: list[AiAuditLogModel]) -> None:
        self._rows = rows

    def all(self) -> list[AiAuditLogModel]:
        return self._rows


class _FakeResult:
    def __init__(self, rows: list[AiAuditLogModel]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows: list[AiAuditLogModel]) -> None:
        self._rows = rows

    async def execute(self, stmt: object) -> _FakeResult:
        return _FakeResult(self._rows)


def _row(*, action: str = "inventory.read") -> AiAuditLogModel:
    return AiAuditLogModel(
        tenant_id=TENANT_ID,
        id=uuid.uuid4(),
        user_id=USER_ID,
        action=action,
        input={"query": "what is on hand?"},
        output={"count": 3},
        model_used=None,
        latency_ms=None,
        created_at=NOW,
    )


def _reader(rows: list[AiAuditLogModel]) -> AiAuditLogReader:
    return AiAuditLogReader(_FakeSession(rows))  # type: ignore[arg-type]


class TestAiAuditLogReader:
    async def test_maps_ai_agent_events_to_guardian_dicts(self) -> None:
        row = _row()
        events = await _reader([row]).read_recent_events(
            tenant_id=TENANT_ID,
            since=date(2026, 9, 1),
            source="ai_agent",
        )

        assert len(events) == 1
        event = events[0]
        assert event["id"] == str(row.id)
        assert event["user_id"] == str(USER_ID)
        assert event["action"] == "inventory.read"
        assert event["created_at"] == NOW.isoformat()
        assert event["input"] == {"query": "what is on hand?"}
        assert event["output"] == {"count": 3}
        assert event["source_table"] == "ai_audit_log"

    async def test_sets_blank_user_and_empty_payloads_when_null(self) -> None:
        row = _row()
        row.user_id = None
        row.input = None
        row.output = None
        events = await _reader([row]).read_recent_events(
            tenant_id=TENANT_ID,
            since=date(2026, 9, 1),
            source="ai_agent",
        )

        assert events[0]["user_id"] == ""
        assert events[0]["input"] == {}
        assert events[0]["output"] == {}

    async def test_cross_service_sources_return_empty(self) -> None:
        for source in ("core", "identity", "unknown"):
            events = await _reader([_row()]).read_recent_events(
                tenant_id=TENANT_ID,
                since=date(2026, 9, 1),
                source=source,
            )
            assert events == []
