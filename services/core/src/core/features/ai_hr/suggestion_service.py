"""Smart leave-window suggestion service (HR-AI-002, 8.2.4).

Lazy-on-read TTL scan of pending suggestions (mirrors quality/utilization/
anomaly services), then:

  - ``org_feed`` (L1, ``erp.hr.ai.read``): aggregate counts by leave type and
    status plus a deterministic narrative — never per-person data.
  - ``employee_suggestions`` (L2, ``erp.hr.ai.individual``): one employee's
    suggestions.
  - ``own_suggestions`` (self-scoped, ``erp.leave.self``): the employee's own
    suggestions for the portal surface.

A suggestion never auto-submits leave: ``use_suggestion`` merely records that
the portal chose to prefill a form (status ``used``) and ``dismiss_suggestion``
records the opt-out (status ``dismissed``).
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.features.ai_hr.models.leave_suggestion import LeaveSuggestionStatus
from core.features.ai_hr.suggestion_repository import LeaveSuggestion
from skyrict_common.exceptions import NotFoundError


class AiHrSuggestionRepositoryPort(Protocol):
    async def latest_generated_at(self, tenant_id: uuid.UUID) -> datetime | None: ...

    async def build_suggestion_rows(self, tenant_id: uuid.UUID) -> list[LeaveSuggestion]: ...

    async def replace_pending_suggestions(
        self, tenant_id: uuid.UUID, rows: list[LeaveSuggestion]
    ) -> None: ...

    async def set_status(
        self, tenant_id: uuid.UUID, suggestion_id: uuid.UUID, status: str
    ) -> bool: ...

    async def list_suggestions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID | None = None
    ) -> list[LeaveSuggestion]: ...


@dataclass(frozen=True, slots=True)
class SuggestionOrgSummary:
    """L1 aggregates across the tenant (no per-person data)."""

    total_suggestions: int
    pending: int
    by_leave_type: dict[str, int]
    generated_at: datetime
    narrative: str


class SuggestionService:
    def __init__(
        self,
        repository: AiHrSuggestionRepositoryPort,
        refresh_days: int = 7,
    ) -> None:
        self._repository = repository
        self._refresh_days = refresh_days

    async def _ensure_scan(self, tenant_id: uuid.UUID) -> None:
        latest = await self._repository.latest_generated_at(tenant_id)
        now = datetime.now(UTC)
        stale = latest is None or (now - latest) >= timedelta(days=self._refresh_days)
        if stale:
            rows = await self._repository.build_suggestion_rows(tenant_id)
            await self._repository.replace_pending_suggestions(tenant_id, rows)

    async def org_feed(self, tenant_id: uuid.UUID) -> SuggestionOrgSummary:
        await self._ensure_scan(tenant_id)
        suggestions = await self._repository.list_suggestions(tenant_id)
        return self._build_summary(suggestions)

    async def employee_suggestions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[LeaveSuggestion]:
        await self._ensure_scan(tenant_id)
        return await self._repository.list_suggestions(tenant_id, employee_id=employee_id)

    async def own_suggestions(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> list[LeaveSuggestion]:
        """Self-scoped suggestions for the employee's portal."""
        await self._ensure_scan(tenant_id)
        return await self._repository.list_suggestions(tenant_id, employee_id=employee_id)

    async def use_suggestion(
        self, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> LeaveSuggestion:
        """Record a portal prefill selection (never auto-submits)."""
        return await self._mark(tenant_id, suggestion_id, LeaveSuggestionStatus.USED, "prefilled")

    async def dismiss_suggestion(
        self, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> LeaveSuggestion:
        """Record the employee/AI's opt-out of a suggestion."""
        return await self._mark(
            tenant_id, suggestion_id, LeaveSuggestionStatus.DISMISSED, "dismissed"
        )

    async def _mark(
        self,
        tenant_id: uuid.UUID,
        suggestion_id: uuid.UUID,
        status: str,
        _verb: str,
    ) -> LeaveSuggestion:
        applied = await self._repository.set_status(tenant_id, suggestion_id, status)
        if not applied:
            raise NotFoundError(f"no pending suggestion {suggestion_id}")
        matches = await self._repository.list_suggestions(tenant_id)
        for s in matches:
            if s.suggestion_id == suggestion_id:
                return s
        raise NotFoundError(f"no pending suggestion {suggestion_id}")

    @staticmethod
    def _build_summary(
        suggestions: Sequence[LeaveSuggestion],
    ) -> SuggestionOrgSummary:
        by_leave_type = Counter(s.leave_type for s in suggestions)
        pending = sum(1 for s in suggestions if s.status == LeaveSuggestionStatus.PENDING)
        narrative = (
            f"{len(suggestions)} leave suggestion(s), {pending} pending "
            f"(prefill-only; nothing is auto-submitted)."
        )
        return SuggestionOrgSummary(
            total_suggestions=len(suggestions),
            pending=pending,
            by_leave_type=dict(by_leave_type),
            generated_at=(suggestions[0].created_at if suggestions else datetime.now(UTC)),
            narrative=narrative,
        )


__all__ = [
    "AiHrSuggestionRepositoryPort",
    "LeaveSuggestion",
    "SuggestionOrgSummary",
    "SuggestionService",
]
