"""Production ``AuditLogReaderPort`` implementation - in-service audit trail.

The Audit Guardian needs to read recent audit events from the sources named by
its port contract (``ai_agent``, ``core``, ``identity``). Only the ``ai_agent``
source is readable from this service's own database (``ai_audit_log``); the
``core`` audit trail (``core_audit_logs``) and the identity trail
(``audit_logs``) live in other services' databases with no read-only projection
or HTTP gateway in this service yet, so those sources return no events here and
the scheduled pass logs the service's designed ``reader_missing`` degradation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from ai_agent.models.ai_audit_log import AiAuditLogModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# The only audit source this service can read directly.
_IN_SERVICE_SOURCE = "ai_agent"


class AiAuditLogReader:
    """Read the tenant's ``ai_audit_log`` trail as guardian event dicts."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_recent_events(
        self,
        *,
        tenant_id: uuid.UUID,
        since: date,
        source: str,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return events since ``since`` for the ai_agent source, newest first.

        ``source`` must be ``"ai_agent"``; other sources are cross-service and
        return an empty list (the guardian service logs the missing reader and
        continues). Each event carries ``source_table`` so the watchers can
        partition by physical table (the same key the fake readers in tests
        use to name ``ai_audit_log``).
        """
        if source != _IN_SERVICE_SOURCE:
            return []

        since_dt = datetime.combine(since, datetime.min.time(), tzinfo=UTC)
        result = await self._session.execute(
            select(AiAuditLogModel)
            .where(
                AiAuditLogModel.tenant_id == tenant_id,
                AiAuditLogModel.created_at >= since_dt,
            )
            .order_by(AiAuditLogModel.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {
                "id": str(row.id),
                "user_id": str(row.user_id) if row.user_id else "",
                "action": row.action,
                "created_at": row.created_at.isoformat(),
                "input": row.input or {},
                "output": row.output or {},
                "source_table": AiAuditLogModel.__tablename__,
            }
            for row in rows
        ]
