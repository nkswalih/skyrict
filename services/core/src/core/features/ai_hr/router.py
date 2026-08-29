"""``/api/v1/ai/hr/*`` routes (HR-AI-001, Commits 2 + 3).

L1 aggregates (``/overview``, ``/tenure``) are computed in-core and never
proxied — no employee row leaves the service. The attrition endpoints
(``/attrition``, ``/attrition/{id}/acknowledge``) are the L1-L2 slice:

- ``GET /attrition`` requires ``erp.ai.invoke`` + ``erp.hr.ai.read``. Callers
  holding ``erp.hr.ai.individual`` (owner + exec only) get the full per-employee
  L2 body; everyone else gets a **403 with an aggregates-only (L1) body** per
  the Gherkin — never an empty failure. The lazy-on-read TTL re-score proxies
  anonymous feature vectors to ai-agent (Commit 3).
- ``POST /attrition/{id}/acknowledge`` requires ``erp.hr.ai.acknowledge`` and
  appends an audited ``hr.ai.risk.acknowledged`` event.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from core.api.deps import (
    get_ai_hr_service,
    get_anomaly_service,
    get_current_user,
    get_eval_repository,
    get_hr_ai_individual,
    get_pattern_data_repository,
    get_quality_service,
    get_suggestion_service,
    get_utilization_service,
    require_permission,
)
from core.core.permissions import (
    ERP_AI_INVOKE,
    ERP_HR_AI_ACKNOWLEDGE,
    ERP_HR_AI_COPILOT,
    ERP_HR_AI_EVAL,
    ERP_HR_AI_READ,
    ERP_HR_READ,
    ERP_HR_WRITE,
)
from core.core.tenant_resolver import derive_tenant_slug
from core.features.ai.proxy import forward_to_ai_agent, relay_response
from core.features.ai.router import get_ai_client
from core.features.ai_hr.anomaly_service import AnomalyService
from core.features.ai_hr.attrition_client import score_features
from core.features.ai_hr.attrition_repository import FeatureVector, ScoredRisk
from core.features.ai_hr.eval_repository import EvalRunRepository
from core.features.ai_hr.pattern_data_repository import AiHrPatternDataRepository
from core.features.ai_hr.quality_service import QualityService
from core.features.ai_hr.schemas import (
    AnomalyOrgOut,
    AttritionDetailOut,
    AttritionSummaryOut,
    EmployeeQualityOut,
    HrEvalRunWrite,
    HrEvalWriteOut,
    LeaveAnomalyOut,
    LeaveBlackoutOut,
    LeaveBlackoutWrite,
    LeaveSuggestionOut,
    OverviewOut,
    PublicHolidayOut,
    PublicHolidayWrite,
    QualityOrgOut,
    SuggestionOrgOut,
    TenureSummaryOut,
    UtilizationAlertOut,
    UtilizationOrgOut,
    anomaly_org_to_out,
    anomaly_to_out,
    attrition_l1_to_out,
    attrition_l2_to_out,
    employee_quality_to_out,
    leave_blackout_to_out,
    overview_to_out,
    public_holiday_to_out,
    quality_org_to_out,
    suggestion_org_to_out,
    suggestion_to_out,
    tenure_to_out,
    utilization_alert_to_out,
    utilization_org_to_out,
)
from core.features.ai_hr.service import AiHrService
from core.features.ai_hr.suggestion_service import SuggestionService
from core.features.ai_hr.utilization_service import UtilizationService
from skyrict_common.exceptions import NotFoundError
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/ai/hr", tags=["ai-hr"])

_require_ai_invoke = require_permission(ERP_AI_INVOKE)
_require_hr_ai_read = require_permission(ERP_HR_AI_READ)
_require_hr_ai_acknowledge = require_permission(ERP_HR_AI_ACKNOWLEDGE)
_require_hr_ai_copilot = require_permission(ERP_HR_AI_COPILOT)
_require_hr_ai_eval = require_permission(ERP_HR_AI_EVAL)
_require_hr_read = require_permission(ERP_HR_READ)
_require_hr_write = require_permission(ERP_HR_WRITE)

_AiInvokeDep = Annotated[dict[str, Any], Depends(_require_ai_invoke)]
_HrAiReadDep = Annotated[dict[str, Any], Depends(_require_hr_ai_read)]
_HrAiAckDep = Annotated[dict[str, Any], Depends(_require_hr_ai_acknowledge)]
_HrAiCopilotDep = Annotated[dict[str, Any], Depends(_require_hr_ai_copilot)]
_HrAiEvalDep = Annotated[dict[str, Any], Depends(_require_hr_ai_eval)]
_HrReadDep = Annotated[dict[str, Any], Depends(_require_hr_read)]
_HrWriteDep = Annotated[dict[str, Any], Depends(_require_hr_write)]
_CurrentUserDep = Annotated[dict[str, Any], Depends(get_current_user)]
_ServiceDep = Annotated[AiHrService, Depends(get_ai_hr_service)]
_QualityServiceDep = Annotated[QualityService, Depends(get_quality_service)]
_UtilizationServiceDep = Annotated[UtilizationService, Depends(get_utilization_service)]
_AnomalyServiceDep = Annotated[AnomalyService, Depends(get_anomaly_service)]
_SuggestionServiceDep = Annotated[SuggestionService, Depends(get_suggestion_service)]
_EvalRepositoryDep = Annotated[EvalRunRepository, Depends(get_eval_repository)]
_PatternDataRepositoryDep = Annotated[
    AiHrPatternDataRepository, Depends(get_pattern_data_repository)
]
_ClientDep = Annotated[httpx.AsyncClient, Depends(get_ai_client)]
_IndividualDep = Annotated[bool, Depends(get_hr_ai_individual)]


def _tenant_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["tenant_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


class _HttpxScorer:
    """Binds the request's auth + tenant slug to the outbound ai-agent call."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        authorization: str | None,
        tenant_slug: str | None,
    ) -> None:
        self._client = client
        self._authorization = authorization
        self._tenant_slug = tenant_slug

    async def score(
        self,
        tenant_id: uuid.UUID,
        features: Sequence[FeatureVector],
    ) -> list[ScoredRisk]:
        del tenant_id  # the tenant travels via X-Tenant-Slug / JWT
        return await score_features(
            self._client,
            authorization=self._authorization,
            tenant_slug=self._tenant_slug,
            features=features,
        )


@router.get("/overview", response_model=ResponseEnvelope[OverviewOut])
async def overview(
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    service: _ServiceDep,
) -> ResponseEnvelope[OverviewOut]:
    """L1 headcount/tenure overview with a deterministic narrative."""
    result = await service.overview(_tenant_id(current_user))
    return ResponseEnvelope(data=overview_to_out(result), message="HR AI overview retrieved")


@router.get("/tenure", response_model=ResponseEnvelope[TenureSummaryOut])
async def tenure(
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    service: _ServiceDep,
) -> ResponseEnvelope[TenureSummaryOut]:
    """L1 tenure-band summary with a deterministic narrative."""
    result = await service.tenure(_tenant_id(current_user))
    return ResponseEnvelope(data=tenure_to_out(result), message="HR AI tenure summary retrieved")


@router.get("/quality", response_model=ResponseEnvelope[QualityOrgOut])
async def quality_org(
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    quality_service: _QualityServiceDep,
) -> ResponseEnvelope[QualityOrgOut]:
    """L1 org data-quality KPI (8.1.3). Never carries per-person values."""
    kpi = await quality_service.org_kpi(_tenant_id(current_user))
    return ResponseEnvelope(
        data=quality_org_to_out(kpi), message="HR AI data-quality KPI retrieved"
    )


@router.get("/quality/{employee_id}", response_model=ResponseEnvelope[EmployeeQualityOut])
async def quality_employee(
    employee_id: uuid.UUID,
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    quality_service: _QualityServiceDep,
    show_individual: _IndividualDep,
) -> ResponseEnvelope[EmployeeQualityOut] | JSONResponse:
    """L2 per-employee quality for ``individual`` callers; 403 otherwise."""
    row = await quality_service.employee_quality(_tenant_id(current_user), employee_id)
    if row is None:
        raise NotFoundError(f"no quality score for employee {employee_id}")
    if not show_individual:
        limited: ResponseEnvelope[dict[str, Any]] = ResponseEnvelope(
            data={"detail": "erp.hr.ai.individual required for the individual view"},
            message="erp.hr.ai.individual required",
        )
        return JSONResponse(status_code=403, content=limited.model_dump(mode="json"))
    return ResponseEnvelope(
        data=employee_quality_to_out(row), message="HR AI employee quality retrieved"
    )


@router.get("/alerts/utilization", response_model=ResponseEnvelope[UtilizationOrgOut])
async def utilization_org(
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    utilization_service: _UtilizationServiceDep,
) -> ResponseEnvelope[UtilizationOrgOut]:
    """L1 usage-balance alert feed (8.1.4). Never carries per-person values."""
    summary = await utilization_service.org_feed(_tenant_id(current_user))
    return ResponseEnvelope(
        data=utilization_org_to_out(summary),
        message="HR AI utilization alerts retrieved",
    )


@router.get(
    "/alerts/utilization/{employee_id}",
    response_model=ResponseEnvelope[list[UtilizationAlertOut]],
)
async def utilization_employee(
    employee_id: uuid.UUID,
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    utilization_service: _UtilizationServiceDep,
    show_individual: _IndividualDep,
) -> ResponseEnvelope[list[UtilizationAlertOut]] | JSONResponse:
    """L2 per-employee utilization alerts for ``individual`` callers; 403 else."""
    if not show_individual:
        limited: ResponseEnvelope[dict[str, Any]] = ResponseEnvelope(
            data={"detail": "erp.hr.ai.individual required for the individual view"},
            message="erp.hr.ai.individual required",
        )
        return JSONResponse(status_code=403, content=limited.model_dump(mode="json"))
    alerts = await utilization_service.employee_alerts(_tenant_id(current_user), employee_id)
    return ResponseEnvelope(
        data=[utilization_alert_to_out(a) for a in alerts],
        message="HR AI employee utilization alerts retrieved",
    )


@router.get("/alerts/anomalies", response_model=ResponseEnvelope[AnomalyOrgOut])
async def anomaly_org(
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    anomaly_service: _AnomalyServiceDep,
) -> ResponseEnvelope[AnomalyOrgOut]:
    """L1 leave-pattern anomaly feed (8.2.1). Never carries per-person values."""
    summary = await anomaly_service.org_feed(_tenant_id(current_user))
    return ResponseEnvelope(
        data=anomaly_org_to_out(summary),
        message="HR AI leave anomaly feed retrieved",
    )


@router.get(
    "/alerts/anomalies/{employee_id}",
    response_model=ResponseEnvelope[list[LeaveAnomalyOut]],
)
async def anomaly_employee(
    employee_id: uuid.UUID,
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    anomaly_service: _AnomalyServiceDep,
    show_individual: _IndividualDep,
) -> ResponseEnvelope[list[LeaveAnomalyOut]] | JSONResponse:
    """L2 per-employee anomaly findings for ``individual`` callers; 403 else."""
    if not show_individual:
        limited: ResponseEnvelope[dict[str, Any]] = ResponseEnvelope(
            data={"detail": "erp.hr.ai.individual required for the individual view"},
            message="erp.hr.ai.individual required",
        )
        return JSONResponse(status_code=403, content=limited.model_dump(mode="json"))
    anomalies = await anomaly_service.employee_anomalies(_tenant_id(current_user), employee_id)
    return ResponseEnvelope(
        data=[anomaly_to_out(a) for a in anomalies],
        message="HR AI employee leave anomaly findings retrieved",
    )


@router.get("/suggestions", response_model=ResponseEnvelope[SuggestionOrgOut])
async def suggestion_org(
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    suggestion_service: _SuggestionServiceDep,
) -> ResponseEnvelope[SuggestionOrgOut]:
    """L1 smart leave-suggestion aggregate (8.2.4). No per-person data."""
    summary = await suggestion_service.org_feed(_tenant_id(current_user))
    return ResponseEnvelope(
        data=suggestion_org_to_out(summary),
        message="HR AI leave suggestions retrieved",
    )


@router.get(
    "/suggestions/{employee_id}",
    response_model=ResponseEnvelope[list[LeaveSuggestionOut]],
)
async def suggestion_employee(
    employee_id: uuid.UUID,
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    suggestion_service: _SuggestionServiceDep,
    show_individual: _IndividualDep,
) -> ResponseEnvelope[list[LeaveSuggestionOut]] | JSONResponse:
    """L2 per-employee leave suggestions for ``individual`` callers; 403 else."""
    if not show_individual:
        limited: ResponseEnvelope[dict[str, Any]] = ResponseEnvelope(
            data={"detail": "erp.hr.ai.individual required for the individual view"},
            message="erp.hr.ai.individual required",
        )
        return JSONResponse(status_code=403, content=limited.model_dump(mode="json"))
    suggestions = await suggestion_service.employee_suggestions(
        _tenant_id(current_user), employee_id
    )
    return ResponseEnvelope(
        data=[suggestion_to_out(s) for s in suggestions],
        message="HR AI employee leave suggestions retrieved",
    )


# --- AI pattern-engine config (holidays + blackouts; migration 0024) ---------
# Tenant lookup data consumed server-side by the anomaly detector (8.2.1) and
# the suggestion engine (8.2.4). Writes are the existing HR config gate
# (``erp.hr.write`` — the same key that governs leave types/balances); reads
# need ``erp.hr.read``. No AI-specific key: these are config rows, not signals.


@router.get("/pattern-data/holidays", response_model=ResponseEnvelope[list[PublicHolidayOut]])
async def list_public_holidays(
    current_user: _HrReadDep,
    pattern_data: _PatternDataRepositoryDep,
) -> ResponseEnvelope[list[PublicHolidayOut]]:
    holidays = await pattern_data.list_holidays(_tenant_id(current_user))
    return ResponseEnvelope(
        data=[public_holiday_to_out(h) for h in holidays],
        message="Public holidays retrieved",
    )


@router.post(
    "/pattern-data/holidays",
    response_model=ResponseEnvelope[PublicHolidayOut],
    status_code=201,
)
async def create_public_holiday(
    body: PublicHolidayWrite,
    current_user: _HrWriteDep,
    pattern_data: _PatternDataRepositoryDep,
) -> ResponseEnvelope[PublicHolidayOut]:
    try:
        holiday = await pattern_data.create_holiday(
            _tenant_id(current_user),
            body.calendar_date,
            body.name,
            department_id=body.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ResponseEnvelope(data=public_holiday_to_out(holiday), message="Public holiday created")


@router.delete("/pattern-data/holidays/{holiday_id}")
async def delete_public_holiday(
    holiday_id: uuid.UUID,
    current_user: _HrWriteDep,
    pattern_data: _PatternDataRepositoryDep,
) -> ResponseEnvelope[dict[str, bool]]:
    deleted = await pattern_data.delete_holiday(_tenant_id(current_user), holiday_id)
    if not deleted:
        raise NotFoundError(f"no public holiday {holiday_id}")
    return ResponseEnvelope(data={"deleted": True}, message="Public holiday deleted")


@router.get("/pattern-data/blackouts", response_model=ResponseEnvelope[list[LeaveBlackoutOut]])
async def list_leave_blackouts(
    current_user: _HrReadDep,
    pattern_data: _PatternDataRepositoryDep,
) -> ResponseEnvelope[list[LeaveBlackoutOut]]:
    blackouts = await pattern_data.list_blackouts(_tenant_id(current_user))
    return ResponseEnvelope(
        data=[leave_blackout_to_out(b) for b in blackouts],
        message="Leave blackout periods retrieved",
    )


@router.post(
    "/pattern-data/blackouts",
    response_model=ResponseEnvelope[LeaveBlackoutOut],
    status_code=201,
)
async def create_leave_blackout(
    body: LeaveBlackoutWrite,
    current_user: _HrWriteDep,
    pattern_data: _PatternDataRepositoryDep,
) -> ResponseEnvelope[LeaveBlackoutOut]:
    try:
        blackout = await pattern_data.create_blackout(
            _tenant_id(current_user),
            body.start_date,
            body.end_date,
            body.reason,
            department_id=body.department_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return ResponseEnvelope(data=leave_blackout_to_out(blackout), message="Leave blackout created")


@router.delete("/pattern-data/blackouts/{blackout_id}")
async def delete_leave_blackout(
    blackout_id: uuid.UUID,
    current_user: _HrWriteDep,
    pattern_data: _PatternDataRepositoryDep,
) -> ResponseEnvelope[dict[str, bool]]:
    deleted = await pattern_data.delete_blackout(_tenant_id(current_user), blackout_id)
    if not deleted:
        raise NotFoundError(f"no leave blackout {blackout_id}")
    return ResponseEnvelope(data={"deleted": True}, message="Leave blackout deleted")


@router.get("/attrition", response_model=ResponseEnvelope[AttritionDetailOut])
async def attrition(
    request: Request,
    _invoke: _AiInvokeDep,
    current_user: _HrAiReadDep,
    client: _ClientDep,
    service: _ServiceDep,
    show_individual: _IndividualDep,
) -> ResponseEnvelope[AttritionDetailOut] | JSONResponse:
    """L2 per-employee risk for ``individual`` callers; L1 aggregates otherwise."""
    tenant_id = _tenant_id(current_user)
    scorer = _HttpxScorer(client, request.headers.get("authorization"), derive_tenant_slug(request))
    scored = await service.attrition(tenant_id, scorer=scorer)
    if not show_individual:
        summary = attrition_l1_to_out(scored)
        limited: ResponseEnvelope[AttritionSummaryOut] = ResponseEnvelope(
            data=summary,
            message="erp.hr.ai.individual required; aggregates returned",
        )
        return JSONResponse(status_code=403, content=limited.model_dump(mode="json"))
    return ResponseEnvelope(
        data=attrition_l2_to_out(scored),
        message="HR AI attrition detail retrieved",
    )


@router.post(
    "/attrition/{employee_id}/acknowledge", response_model=ResponseEnvelope[dict[str, str]]
)
async def acknowledge(
    employee_id: uuid.UUID,
    _invoke: _AiInvokeDep,
    current_user: _HrAiAckDep,
    service: _ServiceDep,
) -> ResponseEnvelope[dict[str, str]]:
    """Audit a manager's acknowledgement of one employee's attrition risk."""
    await service.acknowledge(
        _tenant_id(current_user),
        employee_id,
        actor_user_id=current_user["user_id"],
    )
    return ResponseEnvelope(
        data={"status": "acknowledged"},
        message="Attrition risk acknowledged",
    )


@router.post("/copilot/chat")
async def copilot_chat(
    request: Request,
    _invoke: _AiInvokeDep,
    current_user: _HrAiCopilotDep,
    client: _ClientDep,
) -> Response:
    """Forward one HR Copilot message to ai-agent (spec §9 feature 5).

    Gated by ``erp.ai.invoke`` + ``erp.hr.ai.copilot``. The caller's JWT and
    tenant slug are relayed so ai-agent makes its aggregate reads (and any PII
    redaction) under exactly that identity. The upstream RFC 7807 response
    passes through untouched.
    """
    del current_user
    body = await request.body()
    upstream = await forward_to_ai_agent(
        client,
        method=request.method,
        upstream_path="/ai/hr/copilot/chat",
        authorization=request.headers.get("authorization"),
        tenant_slug=derive_tenant_slug(request),
        body=body,
    )
    return relay_response(upstream)


@router.post("/eval-runs", response_model=ResponseEnvelope[HrEvalWriteOut])
async def record_eval_runs(
    runs: list[HrEvalRunWrite],
    _invoke: _AiInvokeDep,
    current_user: _HrAiEvalDep,
    eval_repository: _EvalRepositoryDep,
) -> ResponseEnvelope[HrEvalWriteOut]:
    """Record ai-agent model-eval precision metrics (SKY-72, append-only).

    One row per metric; gated by ``erp.hr.ai.eval`` (owner wildcard passes).
    Each metric's ``precision``/``threshold`` are validated to [0, 1] here, so
    the operator CLI can warn-not-fail without trusting its own input math.
    """
    rows = [run.model_dump() for run in runs]
    recorded = await eval_repository.append_many(
        tenant_id=_tenant_id(current_user),
        rows=rows,
    )
    return ResponseEnvelope(
        data=HrEvalWriteOut(recorded=recorded),
        message="HR AI eval metrics recorded",
    )
