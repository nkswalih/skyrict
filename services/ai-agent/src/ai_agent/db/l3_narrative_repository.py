"""Persistence for L3 narrative snapshots.

``ai_l3_narrative_snapshots`` is append-per-generation; "cache" is a derived view
(the newest row for a tenant + kind + ``as_of`` date).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from ai_agent.models.l3_narrative import AiL3NarrativeModel

if TYPE_CHECKING:
    from datetime import date

    from sqlalchemy.ext.asyncio import AsyncSession


class L3NarrativeRepository:
    """Tenant-scoped access to L3 narrative snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def insert(
        self,
        *,
        tenant_id: uuid.UUID,
        kind: str,
        status: str,
        as_of: date,
        title: str | None,
        summary: str | None,
        points: list[str] | None,
        caveat: str | None,
        figures: dict[str, str] | None,
        model_used: str | None,
        generated_at: datetime,
    ) -> AiL3NarrativeModel:
        row = AiL3NarrativeModel(
            tenant_id=tenant_id,
            id=uuid.uuid4(),
            kind=kind,
            status=status,
            as_of=as_of,
            title=title,
            summary=summary,
            points=points,
            caveat=caveat,
            figures=figures,
            model_used=model_used,
            generated_at=generated_at,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def latest_for_kind(
        self, tenant_id: uuid.UUID, kind: str, as_of: date
    ) -> AiL3NarrativeModel | None:
        """Newest snapshot for a tenant + kind on a given date."""
        result = await self._session.execute(
            select(AiL3NarrativeModel)
            .where(
                AiL3NarrativeModel.tenant_id == tenant_id,
                AiL3NarrativeModel.kind == kind,
                AiL3NarrativeModel.as_of == as_of,
            )
            .order_by(AiL3NarrativeModel.generated_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    def is_fresh_for(row: AiL3NarrativeModel, as_of: date) -> bool:
        """A row is fresh when it matches the calendar date AND was generated within 24h."""
        if row.as_of != as_of:
            return False
        return (datetime.now(tz=UTC) - row.generated_at).total_seconds() < 86400
