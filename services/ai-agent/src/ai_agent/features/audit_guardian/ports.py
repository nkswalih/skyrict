"""Audit Guardian domain port — protocols for watchers and report generation.

Tests provide fake implementations; production wires the repository and
gateway. The port does NOT import ORM models (import-linter contract).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Protocol


class GuardianReportPort(Protocol):
    """Write-only port for creating reports and events."""

    async def create_report(
        self,
        *,
        tenant_id: uuid.UUID,
        report_week_start: date,
        report_week_end: date,
        summary: str,
        total_events_scanned: int,
        flagged_count: int,
    ) -> uuid.UUID: ...

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
    ) -> uuid.UUID: ...


class AuditLogReaderPort(Protocol):
    """Read-only port for querying audit logs across modules."""

    async def read_recent_events(
        self,
        *,
        tenant_id: uuid.UUID,
        since: date,
        source: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Read recent audit events from the specified source.

        ``source`` is one of: "ai_agent", "core", "identity".
        Returns a list of dicts with keys: id, user_id, action, created_at,
        input, output.
        """
        ...
