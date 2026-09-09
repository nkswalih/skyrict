"""Report builder service - request orchestration between router and engine.

Owns the cross-cutting concerns the engine deliberately knows nothing about:
rate limiting, audit logging, and query-log persistence (mirroring the NL
query service, RPT-AI-001 / SKY-80). The engine stays a pure pipeline; this
layer decides what happens around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from ai_agent.core.audit_events import AI_REPORT_GENERATED, AI_REPORT_SAVED
from ai_agent.core.rate_limit import limiter

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.audit_service import AuditService
    from ai_agent.db.query_log_repository import QueryLogRepository
    from ai_agent.features.report_builder.engine import (
        ReportBuilderEngine,
        ReportBuilderResult,
    )
    from ai_agent.features.report_builder.gateway import CreatedReport

logger = structlog.get_logger("ai_agent.report_builder_service")


class ReportBuilderService:
    """One request's report-builder use cases with limits, logs, and audit."""

    def __init__(
        self,
        *,
        engine: ReportBuilderEngine,
        query_logs: QueryLogRepository,
        audit: AuditService,
        rate_limit_per_minute: int,
        tenant_limit_per_minute: int,
    ) -> None:
        self._engine = engine
        self._query_logs = query_logs
        self._audit = audit
        self._rate_limit_per_minute = rate_limit_per_minute
        self._tenant_limit_per_minute = tenant_limit_per_minute

    async def generate(
        self,
        *,
        prompt: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> ReportBuilderResult:
        """Enforce limits, run the engine, persist logs + audit event."""
        await limiter.enforce(
            key=f"ai:report_builder:{tenant_id}:{user_id}",
            limit=self._rate_limit_per_minute,
            window_seconds=60,
        )
        await limiter.enforce(
            key=f"ai:tenant_total:{tenant_id}",
            limit=self._tenant_limit_per_minute,
            window_seconds=60,
        )

        result = await self._engine.generate(
            prompt,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        summary = result.answer[:200]
        await self._query_logs.add(
            tenant_id=tenant_id,
            user_id=user_id,
            query_text=prompt.strip(),
            parsed_intent=result.parsed_spec,
            result_summary=summary,
            model_used=result.model_used,
            latency_ms=result.latency_ms,
        )
        await self._audit.log(
            action=AI_REPORT_GENERATED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"prompt": prompt.strip()},
            output_payload={"answer_summary": summary},
            model_used=result.model_used,
            latency_ms=result.latency_ms,
        )
        logger.info(
            "report_builder.completed",
            latency_ms=result.latency_ms,
            generated=result.data is not None,
        )
        return result

    async def save(
        self,
        *,
        template_slug: str,
        title: str,
        description: str | None,
        slug: str,
        params: dict[str, Any],
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> CreatedReport:
        """Persist a resolved report; bounded by the builder limit + audit trail."""
        await limiter.enforce(
            key=f"ai:report_builder:{tenant_id}:{user_id}",
            limit=self._rate_limit_per_minute,
            window_seconds=60,
        )

        created = await self._engine.save(
            template_slug=template_slug,
            title=title,
            description=description,
            slug=slug,
            params=params,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        await self._audit.log(
            action=AI_REPORT_SAVED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"slug": slug, "template_slug": template_slug},
            output_payload={"definition_slug": created.definition.slug},
            model_used=None,
            latency_ms=None,
        )
        logger.info(
            "report_builder.saved",
            slug=slug,
            template_slug=template_slug,
        )
        return created
