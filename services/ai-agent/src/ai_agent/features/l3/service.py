"""L3 Narrative service - orchestration between router and the L3 pipeline.

Owns cache reuse, force-refresh gate, LLM-disabled abstention, and audit logging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, cast

import structlog

from ai_agent.core.audit_events import (
    AI_L3_ABSTAINED,
    AI_L3_ACCESSED,
    AI_L3_COMPLIANCE_DIGESTED,
    AI_L3_LEAVE_PAY_CORRELATED,
    AI_L3_PAYROLL_COST_GENERATED,
)
from ai_agent.features.l3.extract import (
    build_compliance_digest_signals,
    build_leave_pay_signals,
    build_payroll_cost_signals,
    build_prompt,
    has_material_activity,
)
from ai_agent.features.l3.narrate import narrate_l3
from ai_agent.features.l3.render import render_narrative
from skyrict_common.exceptions import PermissionDeniedError

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.audit_service import AuditService
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.db.l3_narrative_repository import L3NarrativeRepository
    from ai_agent.features.l3.gateway import L3CoreGatewayPort
    from ai_agent.models.l3_narrative import AiL3NarrativeModel

logger = structlog.get_logger("ai_agent.l3_service")

_KIND_GATEWAY_DISPATCH = {
    "payroll_cost": "get_payroll_cost_movement",
    "leave_pay_correlation": "get_leave_pay_pairs",
    "compliance_digest": "get_compliance_risk",
}

_KIND_AUDIT_EVENT = {
    "payroll_cost": AI_L3_PAYROLL_COST_GENERATED,
    "leave_pay_correlation": AI_L3_LEAVE_PAY_CORRELATED,
    "compliance_digest": AI_L3_COMPLIANCE_DIGESTED,
}


@dataclass(frozen=True, slots=True)
class L3NarrativeResult:
    """Everything the L3 narrator returns for a request."""

    status: str
    source: str
    as_of: date
    kind: str
    title: str | None
    summary: str | None
    points: list[str]
    caveat: str | None
    generated_at: datetime | None
    model_used: str | None
    figures: dict[str, str] = field(default_factory=dict)


class L3NarrativeService:
    """One tenant's L3 narrative use case with cache, refresh gate and audit."""

    def __init__(
        self,
        *,
        gateway: L3CoreGatewayPort,
        llm_router: LlmRouter,
        cache: L3NarrativeRepository,
        audit: AuditService,
        allow_llm: bool,
        allow_refresh: bool,
    ) -> None:
        self._gateway = gateway
        self._llm_router = llm_router
        self._cache = cache
        self._audit = audit
        self._allow_llm = allow_llm
        self._allow_refresh = allow_refresh

    async def generate(
        self,
        *,
        kind: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        as_of: date,
        force_refresh: bool,
    ) -> L3NarrativeResult:
        """Return (or produce) the narrated L3 narrative for ``kind`` + ``as_of``."""
        if not force_refresh:
            cached = await self._cache.latest_for_kind(tenant_id, kind, as_of)
            if cached is not None and self._cache.is_fresh_for(cached, as_of):
                logger.info("l3.cache_hit", tenant_id=tenant_id, kind=kind)
                await self._audit.log(
                    action=AI_L3_ACCESSED,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    input_payload={
                        "as_of": as_of.isoformat(),
                        "kind": kind,
                        "force_refresh": False,
                    },
                    output_payload={
                        "status": cached.status,
                        "generated_at": (
                            cached.generated_at.isoformat()
                            if isinstance(cached.generated_at, datetime)
                            else str(cached.generated_at)
                        ),
                    }
                    if cached.generated_at
                    else {"status": cached.status},
                )
                return _from_row(cached, kind=kind, source="cache")

        if force_refresh and not self._allow_refresh:
            raise PermissionDeniedError("L3 narrative refresh is not permitted")

        signals = await self._gather_signals(kind, as_of)
        if not has_material_activity(kind, signals):
            return await self._persist_abstention(
                tenant_id=tenant_id,
                kind=kind,
                as_of=as_of,
                signals=signals,
                source="abstention",
                reason="No material activity for this L3 metric today.",
                user_id=user_id,
            )

        if not self._allow_llm:
            return await self._persist_abstention(
                tenant_id=tenant_id,
                kind=kind,
                as_of=as_of,
                signals=signals,
                source="llm_disabled",
                reason="LLM narration is disabled for this deployment.",
                user_id=user_id,
            )

        prompt = build_prompt(kind, signals)
        text = await narrate_l3(self._llm_router, prompt)
        if text is None:
            return await self._persist_abstention(
                tenant_id=tenant_id,
                kind=kind,
                as_of=as_of,
                signals=signals,
                source="unparseable",
                reason="The model did not produce a usable narrative.",
                user_id=user_id,
            )

        figures = cast("dict[str, str]", signals.get("figures", {}))
        rendered = render_narrative(text, figures)

        audit_action = _KIND_AUDIT_EVENT.get(kind)
        if audit_action:
            await self._audit.log(
                action=audit_action,
                tenant_id=tenant_id,
                user_id=user_id,
                input_payload={
                    "as_of": as_of.isoformat(),
                    "kind": kind,
                    "force_refresh": force_refresh,
                },
                output_payload={
                    "title": rendered.title,
                    "model_used": rendered.model_used,
                    "latency_ms": rendered.latency_ms,
                },
                model_used=rendered.model_used,
                latency_ms=rendered.latency_ms,
            )

        generated_at = datetime.now(tz=UTC)
        await self._cache.insert(
            tenant_id=tenant_id,
            kind=kind,
            status="generated",
            as_of=as_of,
            title=rendered.title,
            summary=rendered.summary,
            points=rendered.points,
            caveat=rendered.caveat or None,
            figures=figures,
            model_used=rendered.model_used,
            generated_at=generated_at,
        )
        logger.info("l3.generated", tenant_id=tenant_id, kind=kind, title=rendered.title)
        return L3NarrativeResult(
            status="generated",
            source="live",
            as_of=as_of,
            kind=kind,
            title=rendered.title,
            summary=rendered.summary,
            points=rendered.points,
            caveat=rendered.caveat or None,
            generated_at=generated_at,
            model_used=rendered.model_used,
            figures=figures,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def commit(self) -> None:
        """Commit pending snapshot/audit rows.

        Request flows commit via the request-session dependency; background
        jobs (weekly digest cron) that factory their own session call this.
        """
        await self._cache._session.commit()

    async def _gather_signals(self, kind: str, as_of: date) -> dict[str, object]:
        method_name = _KIND_GATEWAY_DISPATCH.get(kind)
        if method_name is None:
            raise ValueError(f"Unknown L3 narrative kind: {kind}")
        method = getattr(self._gateway, method_name)
        raw = await method(as_of)
        if kind == "payroll_cost":
            return build_payroll_cost_signals(raw)
        if kind == "leave_pay_correlation":
            return build_leave_pay_signals(raw)
        if kind == "compliance_digest":
            return build_compliance_digest_signals(raw)
        return cast("dict[str, object]", raw)

    async def _persist_abstention(
        self,
        *,
        tenant_id: uuid.UUID,
        kind: str,
        as_of: date,
        signals: dict[str, object],
        source: str,
        reason: str,
        user_id: uuid.UUID | None,
    ) -> L3NarrativeResult:
        generated_at = datetime.now(tz=UTC)
        await self._audit.log(
            action=AI_L3_ABSTAINED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"as_of": as_of.isoformat(), "kind": kind, "source": source},
            output_payload={"reason": reason},
        )
        await self._cache.insert(
            tenant_id=tenant_id,
            kind=kind,
            status="abstained",
            as_of=as_of,
            title=None,
            summary=None,
            points=[],
            caveat=reason,
            figures=None,
            model_used=None,
            generated_at=generated_at,
        )
        logger.info("l3.abstained", tenant_id=tenant_id, kind=kind, source=source)
        return L3NarrativeResult(
            status="abstained",
            source=source,
            as_of=as_of,
            kind=kind,
            title=None,
            summary=None,
            points=[],
            caveat=reason,
            generated_at=generated_at,
            model_used=None,
            figures={},
        )


def _from_row(row: AiL3NarrativeModel, *, kind: str, source: str) -> L3NarrativeResult:
    """Rebuild an L3NarrativeResult from a cached row."""
    return L3NarrativeResult(
        status=row.status,
        source=source,
        as_of=row.as_of,
        kind=kind,
        title=row.title,
        summary=row.summary,
        points=list(row.points or []),
        caveat=row.caveat,
        generated_at=row.generated_at,
        model_used=row.model_used,
        figures=dict(row.figures or {}),
    )
