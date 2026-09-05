"""Narrator service - orchestration between router and the digest pipeline.

Owns the cross-cutting concerns the pipeline deliberately stays clean of:
day-cache reuse, the force-refresh gate, LLM-disabled abstention, and audit
logging. A digest is produced only when (a) no fresh cached row exists, and
(b) the day has material activity worth narrating - empty days persist an
``abstained`` snapshot instead of letting the LLM pad boilerplate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.audit_events import AI_NARRATOR_GENERATED
from ai_agent.features.narrator.extract import (
    build_prompt,
    build_signals_dict,
    has_material_activity,
)
from ai_agent.features.narrator.narrate import narrate
from skyrict_common.exceptions import PermissionDeniedError

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.audit_service import AuditService
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.db.digest_repository import DigestCacheRepository
    from ai_agent.features.narrator.gateway import CoreGatewayPort
    from ai_agent.models.ai_digest import AiDigestModel

logger = structlog.get_logger("ai_agent.narrator_service")


@dataclass(frozen=True, slots=True)
class DigestResult:
    """Everything the narrator returns for a digest request."""

    status: str
    source: str
    as_of: date
    title: str | None
    summary: str | None
    points: list[str]
    caveat: str | None
    generated_at: datetime | None
    model_used: str | None
    signals: dict[str, object] = field(default_factory=dict)


class NarratorService:
    """One tenant's digest use case with cache, refresh gate and audit."""

    def __init__(
        self,
        *,
        gateway: CoreGatewayPort,
        llm_router: LlmRouter,
        cache: DigestCacheRepository,
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

    async def digest(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        as_of: date,
        force_refresh: bool,
    ) -> DigestResult:
        """Return (or produce) the narrated digest for ``as_of``."""
        if not force_refresh:
            cached = await self._cache.latest_for_date(tenant_id, as_of)
            if cached is not None and self._cache.is_fresh_for(cached, as_of):
                logger.info("narrator.cache_hit", tenant_id=tenant_id)
                return _from_row(cached, source="cache")

        if force_refresh and not self._allow_refresh:
            raise PermissionDeniedError("Narrator refresh is not permitted")

        signals = await self._gather_signals(as_of)
        if not has_material_activity(signals):
            return await self._persist_abstention(
                tenant_id=tenant_id,
                as_of=as_of,
                signals=signals,
                source="abstention",
                reason="No material activity across Finance, Sales, Inventory or CRM today.",
                user_id=user_id,
                audit_action=None,
            )

        if not self._allow_llm:
            return await self._persist_abstention(
                tenant_id=tenant_id,
                as_of=as_of,
                signals=signals,
                source="llm_disabled",
                reason="LLM narration is disabled for this deployment.",
                user_id=user_id,
                audit_action=None,
            )

        text = await narrate(self._llm_router, build_prompt(signals))
        if text is None:
            return await self._persist_abstention(
                tenant_id=tenant_id,
                as_of=as_of,
                signals=signals,
                source="unparseable",
                reason="The model did not produce a usable digest.",
                user_id=user_id,
                audit_action=None,
            )

        await self._audit.log(
            action=AI_NARRATOR_GENERATED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"as_of": as_of.isoformat(), "force_refresh": force_refresh},
            output_payload={
                "title": text.title,
                "model_used": text.model_used,
                "latency_ms": text.latency_ms,
            },
            model_used=text.model_used,
            latency_ms=text.latency_ms,
        )
        generated_at = datetime.now(tz=UTC)
        await self._cache.insert(
            tenant_id=tenant_id,
            status="generated",
            as_of=as_of,
            title=text.title,
            summary=text.summary,
            points=text.points,
            caveat=text.caveat or None,
            signals=signals,
            model_used=text.model_used,
            latency_ms=text.latency_ms,
            generated_at=generated_at,
        )
        logger.info("narrator.generated", tenant_id=tenant_id, title=text.title)
        return DigestResult(
            status="generated",
            source="live",
            as_of=as_of,
            title=text.title,
            summary=text.summary,
            points=text.points,
            caveat=text.caveat or None,
            generated_at=generated_at,
            model_used=text.model_used,
            signals=signals,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _gather_signals(self, as_of: date) -> dict[str, object]:
        finance = await self._gateway.get_finance(as_of)
        sales = await self._gateway.get_sales(as_of)
        inventory = await self._gateway.get_inventory()
        inventory_health = await self._gateway.get_inventory_health()
        crm = await self._gateway.get_crm(as_of)
        return build_signals_dict(
            as_of=as_of,
            finance=finance,
            sales=sales,
            inventory=inventory,
            inventory_health=inventory_health,
            crm=crm,
        )

    async def _persist_abstention(
        self,
        *,
        tenant_id: uuid.UUID,
        as_of: date,
        signals: dict[str, object],
        source: str,
        reason: str,
        user_id: uuid.UUID | None,
        audit_action: str | None,
    ) -> DigestResult:
        generated_at = datetime.now(tz=UTC)
        await self._cache.insert(
            tenant_id=tenant_id,
            status="abstained",
            as_of=as_of,
            title=None,
            summary=None,
            points=[],
            caveat=reason,
            signals=signals,
            model_used=None,
            latency_ms=None,
            generated_at=generated_at,
        )
        logger.info("narrator.abstained", tenant_id=tenant_id, source=source)
        return DigestResult(
            status="abstained",
            source=source,
            as_of=as_of,
            title=None,
            summary=None,
            points=[],
            caveat=reason,
            generated_at=generated_at,
            model_used=None,
            signals=signals,
        )


def _from_row(row: AiDigestModel, *, source: str) -> DigestResult:
    """Rebuild a DigestResult from a cached row (attribute-based, test-friendly)."""
    return DigestResult(
        status=row.status,
        source=source,
        as_of=row.as_of,
        title=row.title,
        summary=row.summary,
        points=list(row.points or []),
        caveat=row.caveat,
        generated_at=row.generated_at,
        model_used=row.model_used,
        signals=dict(row.signals or {}),
    )
