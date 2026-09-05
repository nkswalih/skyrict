"""NL query service - request orchestration between router and engine.

Owns the cross-cutting concerns the engine deliberately knows nothing about:
rate limiting (spec §5.4), audit logging (§5.3), and query-log persistence
(§2.6). The engine stays a pure parse-resolve-execute pipeline; this layer
decides what happens around it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from ai_agent.core.audit_events import AI_QUERY_EXECUTED
from ai_agent.core.rate_limit import limiter

if TYPE_CHECKING:
    import uuid

    from ai_agent.core.audit_service import AuditService
    from ai_agent.db.query_log_repository import QueryLogRepository
    from ai_agent.features.nl_query.engine import NlQueryEngine, NlQueryResult

logger = structlog.get_logger("ai_agent.nl_service")


class NlQueryService:
    """One tenant's NL-query use cases with limits, logs, and audit."""

    def __init__(
        self,
        *,
        engine: NlQueryEngine,
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

    async def ask(
        self,
        *,
        question: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> NlQueryResult:
        """Enforce limits, run the engine, persist logs + audit event."""
        await limiter.enforce(
            key=f"ai:nl_query:{tenant_id}:{user_id}",
            limit=self._rate_limit_per_minute,
            window_seconds=60,
        )
        await limiter.enforce(
            key=f"ai:tenant_total:{tenant_id}",
            limit=self._tenant_limit_per_minute,
            window_seconds=60,
        )

        result = await self._engine.ask(
            question,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        summary = result.answer[:200]
        await self._query_logs.add(
            tenant_id=tenant_id,
            user_id=user_id,
            query_text=question.strip(),
            parsed_intent=result.parsed_intent,
            result_summary=summary,
            model_used=result.model_used,
            latency_ms=result.latency_ms,
        )
        await self._audit.log(
            action=AI_QUERY_EXECUTED,
            tenant_id=tenant_id,
            user_id=user_id,
            input_payload={"query": question.strip()},
            output_payload={"answer_summary": summary},
            model_used=result.model_used,
            latency_ms=result.latency_ms,
        )
        logger.info(
            "nl_query.completed",
            latency_ms=result.latency_ms,
            abstained=result.data is None,
        )
        return result
