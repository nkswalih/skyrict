"""/ai/report-builder endpoints - natural-language report generation (SKY-80).

Authentication happens here; authorization happened upstream at the core
monolith's proxy (erp.reports.read / erp.reports.create checked before
forwarding - the SKY-57 "AI is a proxy, not a bypass" rule). This router
composes per-request dependencies: caller identity, a report gateway bound to
the CALLER'S token, and the engine wired to the shared LLM router from
app.state.

The gateway forwards the caller's own JWT + tenant slug to Core on every call,
so Core enforces the caller's report scopes on read AND create. The ai-agent
invents no catalog and holds no SQL.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.report_builder import (
    ReportBuilderGenerateRequest,
    ReportBuilderGenerateResponse,
    ReportBuilderSaveRequest,
    ReportBuilderSaveResponse,
)
from ai_agent.core.audit_service import AuditService
from ai_agent.core.config import settings
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.db.query_log_repository import QueryLogRepository
from ai_agent.features.report_builder.engine import ReportBuilderEngine
from ai_agent.features.report_builder.gateway import (
    HttpReportGateway,
    ReportGatewayPort,
)
from ai_agent.features.report_builder.service import ReportBuilderService

router = APIRouter(prefix="/ai/report-builder", tags=["ai-report-builder"])


def get_report_gateway(request: Request) -> ReportGatewayPort:
    """Gateway bound to THIS request's identity - never service credentials.

    Core sees the caller's own JWT and tenant slug, so every report read and
    create runs with exactly the access the human user already has - the AI
    never becomes a privilege escalator.
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    return HttpReportGateway(
        base_url=str(settings.REPORT_SERVICE_URL),
        bearer_token=token,
        # Middleware guarantees the slug exists on business routes.
        tenant_slug=TenantContext.get_tenant_slug() or "",
        timeout_seconds=settings.REPORT_SERVICE_TIMEOUT_SECONDS,
    )


def _build_service(
    request: Request,
    session: AsyncSession,
) -> ReportBuilderService:
    """Compose the report-builder stack for one request (test-visible seam)."""
    gateway = get_report_gateway(request)

    async def gateway_factory() -> ReportGatewayPort:
        return gateway

    engine = ReportBuilderEngine(
        llm_router=request.app.state.llm_router,
        gateway_factory=gateway_factory,
        confidence_threshold=settings.CONFIDENCE_THRESHOLD,
    )
    return ReportBuilderService(
        engine=engine,
        query_logs=QueryLogRepository(session),
        audit=AuditService(AiAuditLogRepository(session)),
        rate_limit_per_minute=settings.RATE_LIMIT_REPORT_BUILDER_PER_MIN,
        tenant_limit_per_minute=settings.RATE_LIMIT_TENANT_PER_MIN,
    )


def get_report_builder_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ReportBuilderService:
    """FastAPI dependency wrapping :func:`_build_service`."""
    return _build_service(request, session)


@router.post("/generate", response_model=ReportBuilderGenerateResponse)
async def generate_report(
    body: ReportBuilderGenerateRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportBuilderService, Depends(get_report_builder_service)],
) -> ReportBuilderGenerateResponse:
    """Build one natural-language report request - with chart hint + run params."""
    result = await service.generate(
        prompt=body.prompt,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
    )
    return ReportBuilderGenerateResponse(
        answer=result.answer,
        data=result.data,
        model_used=result.model_used,
        latency_ms=result.latency_ms,
    )


@router.post("/save", response_model=ReportBuilderSaveResponse)
async def save_report(
    body: ReportBuilderSaveRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[ReportBuilderService, Depends(get_report_builder_service)],
) -> ReportBuilderSaveResponse:
    """Persist a resolved report as a new Core definition (template SQL only)."""
    created = await service.save(
        template_slug=body.template_slug,
        title=body.title,
        description=body.description,
        slug=body.slug,
        params=body.params,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
    )
    return ReportBuilderSaveResponse(
        slug=created.definition.slug,
        title=created.definition.title,
        module=created.definition.module,
        answer=f"Report '{created.definition.title}' saved.",
        default_params=created.default_params,
    )
