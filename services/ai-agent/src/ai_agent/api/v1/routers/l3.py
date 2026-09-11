"""/ai/l3 endpoints - L3 HR/Payroll narrative feature.

Authentication happens here; authorization happens upstream at the core
monolith proxy. The force-refresh action is AND-gated there by
``erp.hr.ai.management`` (read) plus ``erp.ai.l3.refresh`` (refresh) - the
same two-tier convention as the SKY-63 narrator. As a second gate, the
service honours force-refresh only while ``settings.L3_ALLOW_REFRESH`` is set.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.api.deps import get_current_user, get_db
from ai_agent.api.v1.schemas.l3 import L3NarrativeResponse
from ai_agent.core.audit_service import AuditService
from ai_agent.core.config import settings
from ai_agent.core.tenant_context import TenantContext
from ai_agent.db.audit_repository import AiAuditLogRepository
from ai_agent.db.l3_narrative_repository import L3NarrativeRepository
from ai_agent.features.l3.gateway import HttpL3CoreGateway, L3CoreGatewayPort
from ai_agent.features.l3.service import L3NarrativeService

router = APIRouter(prefix="/ai/l3", tags=["ai-l3"])

_ALLOWED_KINDS = frozenset({"payroll_cost", "leave_pay_correlation", "compliance_digest"})


def _get_gateway(request: Request) -> L3CoreGatewayPort:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    return HttpL3CoreGateway(
        base_url=str(settings.INVENTORY_SERVICE_URL),
        bearer_token=token,
        tenant_slug=TenantContext.get_tenant_slug() or "",
    )


def _get_refresh_allowed() -> bool:
    return settings.L3_ALLOW_REFRESH


def _build_service(
    request: Request,
    session: AsyncSession,
    allow_refresh: bool,
) -> L3NarrativeService:
    gateway = _get_gateway(request)
    return L3NarrativeService(
        gateway=gateway,
        llm_router=request.app.state.llm_router,
        cache=L3NarrativeRepository(session),
        audit=AuditService(AiAuditLogRepository(session)),
        allow_llm=settings.NARRATOR_ALLOW_LLM,
        allow_refresh=allow_refresh,
    )


def get_l3_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    allow_refresh: Annotated[bool, Depends(_get_refresh_allowed)],
) -> L3NarrativeService:
    return _build_service(request, session, allow_refresh)


def _response(result: Any) -> L3NarrativeResponse:
    return L3NarrativeResponse(
        status=result.status,
        source=result.source,
        as_of=result.as_of,
        kind=result.kind,
        title=result.title,
        summary=result.summary,
        points=list(result.points),
        caveat=result.caveat,
        generated_at=result.generated_at,
        model_used=result.model_used,
        figures=result.figures or None,
    )


@router.get("/{kind}", response_model=L3NarrativeResponse)
async def get_l3_narrative(
    kind: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[L3NarrativeService, Depends(get_l3_service)],
    as_of: date | None = None,
) -> L3NarrativeResponse:
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(status_code=422, detail=f"Invalid kind: {kind}")
    day = as_of or datetime.now(tz=UTC).date()
    result = await service.generate(
        kind=kind,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        as_of=day,
        force_refresh=False,
    )
    return _response(result)


@router.post("/{kind}/refresh", response_model=L3NarrativeResponse)
async def refresh_l3_narrative(
    kind: str,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    service: Annotated[L3NarrativeService, Depends(get_l3_service)],
    as_of: date | None = None,
) -> L3NarrativeResponse:
    if kind not in _ALLOWED_KINDS:
        raise HTTPException(status_code=422, detail=f"Invalid kind: {kind}")
    day = as_of or datetime.now(tz=UTC).date()
    result = await service.generate(
        kind=kind,
        tenant_id=user["tenant_id"],
        user_id=user["user_id"],
        as_of=day,
        force_refresh=True,
    )
    return _response(result)
