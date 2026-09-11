"""``/api/v1/ai/*`` proxy routes - permission checks BEFORE forwarding.

Permission matrix (SKY-68 / SKY-90, spec 6.3): every AI call needs
``erp.ai.invoke`` AND the module key for the touched domain -
``erp.inventory.read`` for reads, ``erp.inventory.write`` for anomaly
dispositions, ``erp.inventory.ai.approve`` for suggestion scan/approve/reject.
SKY-90 wave 2 adds Sales Coach AI (``erp.ai.coaching.read`` /
``erp.ai.coaching.review``) and Audit Guardian AI (``erp.ai.guardian.read`` /
``erp.ai.guardian.review``) proxy routes.

The JWT is forwarded verbatim; ai-agent re-verifies it against the
relayed tenant slug (spec 1.4: AI is a proxy, not an auth bypass).

Path ids are typed ``uuid.UUID`` so FastAPI rejects anything else with
422 before the handler runs - the forwarded URL only ever embeds the
canonical hyphenated form (no ``/``, ``?`` or traversal sequences can
reach the upstream request target).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from core.api.deps import require_all_permissions, require_permission
from core.core.permissions import (
    ERP_AI_COACHING_READ,
    ERP_AI_COACHING_REVIEW,
    ERP_AI_GUARDIAN_READ,
    ERP_AI_GUARDIAN_REVIEW,
    ERP_AI_INVOKE,
    ERP_AI_L3_REFRESH,
    ERP_AI_NARRATOR_REFRESH,
    ERP_CRM_READ,
    ERP_CRM_WRITE,
    ERP_FINANCE_READ,
    ERP_HR_AI_MANAGEMENT,
    ERP_INVENTORY_AI_APPROVE,
    ERP_INVENTORY_READ,
    ERP_INVENTORY_WRITE,
    ERP_REPORTS_CREATE,
    ERP_REPORTS_READ,
    ERP_SALES_READ,
)
from core.core.tenant_resolver import derive_tenant_slug
from core.features.ai.proxy import forward_to_ai_agent, relay_response

router = APIRouter(prefix="/ai", tags=["ai"])

# Module-level singletons so each permission closure is built once
# (same pattern as features/inventory/router.py).
_require_ai_invoke = require_permission(ERP_AI_INVOKE)
_require_inventory_read = require_permission(ERP_INVENTORY_READ)
_require_inventory_write = require_permission(ERP_INVENTORY_WRITE)
_require_inventory_ai_approve = require_permission(ERP_INVENTORY_AI_APPROVE)
_require_crm_read = require_permission(ERP_CRM_READ)
_require_crm_write = require_permission(ERP_CRM_WRITE)

_InvokeDep = Annotated[dict[str, Any], Depends(_require_ai_invoke)]
_ReadDep = Annotated[dict[str, Any], Depends(_require_inventory_read)]
_WriteDep = Annotated[dict[str, Any], Depends(_require_inventory_write)]
_AIApproveDep = Annotated[dict[str, Any], Depends(_require_inventory_ai_approve)]
_CrmReadDep = Annotated[dict[str, Any], Depends(_require_crm_read)]
_CrmWriteDep = Annotated[dict[str, Any], Depends(_require_crm_write)]
_require_reports_read = require_permission(ERP_REPORTS_READ)
# The save path persists a NEW definition, so the caller must hold the create
# gate IN ADDITION to the read gate every reporting endpoint enforces.
_require_reports_create = require_all_permissions(ERP_REPORTS_READ, ERP_REPORTS_CREATE)

# --- L3 HR/Payroll narratives (HR-AI-003) ----------------------------------
# L3 outputs require erp.hr.ai.management everywhere (spec: management-only).
# Force-refresh adds erp.ai.l3.refresh - the same two-tier convention as the
# SKY-63 narrator (reads + a dedicated refresh key).
_require_hr_ai_management = require_permission(ERP_HR_AI_MANAGEMENT)
_HrAiManagementDep = Annotated[dict[str, Any], Depends(_require_hr_ai_management)]
_require_hr_ai_l3_refresh = require_all_permissions(ERP_HR_AI_MANAGEMENT, ERP_AI_L3_REFRESH)
_HrAiL3RefreshDep = Annotated[dict[str, Any], Depends(_require_hr_ai_l3_refresh)]

# --- Cross-module narrator (SKY-63) strict matrix ---------------------------
# The digest spans all four ERP domains, so a caller must hold erp.ai.invoke
# AND every module read. Force-refresh additionally needs erp.ai.narrator.refresh.
_NARRATOR_READS = (
    ERP_AI_INVOKE,
    ERP_FINANCE_READ,
    ERP_SALES_READ,
    ERP_INVENTORY_READ,
    ERP_CRM_READ,
)


_require_narrator_reads = require_all_permissions(*_NARRATOR_READS)
_require_narrator_refresh = require_all_permissions(*_NARRATOR_READS, ERP_AI_NARRATOR_REFRESH)

_NarratorDep = Annotated[dict[str, Any], Depends(_require_narrator_reads)]
_NarratorRefreshDep = Annotated[dict[str, Any], Depends(_require_narrator_refresh)]

_ReportsReadDep = Annotated[dict[str, Any], Depends(_require_reports_read)]
_ReportsCreateDep = Annotated[dict[str, Any], Depends(_require_reports_create)]

# --- Sales Coach + Audit Guardian AI (SKY-90 wave 2) -------------------------
# Coaching review = accept/dismiss decisions; Guardian review = operator
# acknowledgement of the flagged-event integrity report.

_require_coaching_read = require_permission(ERP_AI_COACHING_READ)
_require_coaching_review = require_permission(ERP_AI_COACHING_REVIEW)
_require_guardian_read = require_permission(ERP_AI_GUARDIAN_READ)
_require_guardian_review = require_permission(ERP_AI_GUARDIAN_REVIEW)

_CoachingReadDep = Annotated[dict[str, Any], Depends(_require_coaching_read)]
_CoachingReviewDep = Annotated[dict[str, Any], Depends(_require_coaching_review)]
_GuardianReadDep = Annotated[dict[str, Any], Depends(_require_guardian_read)]
_GuardianReviewDep = Annotated[dict[str, Any], Depends(_require_guardian_review)]


def get_ai_client(request: Request) -> httpx.AsyncClient:
    """The lifespan-owned pooled client to ai-agent (never per-request)."""
    client: httpx.AsyncClient | None = getattr(request.app.state, "ai_client", None)
    if client is None:
        raise RuntimeError("AI agent HTTP client is not initialised")
    return client


_ClientDep = Annotated[httpx.AsyncClient, Depends(get_ai_client)]


async def _proxy(
    request: Request,
    client: httpx.AsyncClient,
    upstream_path: str,
) -> Response:
    """Forward one request after auth+authz deps have already passed."""
    authorization = request.headers.get("authorization")
    body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
    upstream = await forward_to_ai_agent(
        client,
        method=request.method,
        upstream_path=upstream_path,
        authorization=authorization,
        tenant_slug=derive_tenant_slug(request),
        body=body,
        # Raw query string round-trips verbatim (order + duplicates preserved).
        params=httpx.QueryParams(request.url.query),
    )
    return relay_response(upstream)


# --- NL inventory query (feature 1) ----------------------------------------


@router.get("/inventory/search")
async def proxy_semantic_search(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Hybrid exact+semantic product search (SKY-70) -> ai-agent.

    Forwarded verbatim to ai-agent /api/v1/ai/inventory/search; the caller
    must hold ``erp.ai.invoke`` + ``erp.inventory.read`` (the SKY-57 rule
    that AI is a proxy, never an auth bypass). The upstream service verifies
    the JWT against the relayed tenant slug and degrades to exact-only search
    when no embedding provider is configured.
    """
    return await _proxy(request, client, "/api/v1/ai/inventory/search")


@router.post("/inventory/query")
async def proxy_nl_query(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Natural-language question about stock -> ai-agent /api/v1/ai/query."""
    return await _proxy(request, client, "/api/v1/ai/query")


@router.get("/inventory/query/history")
async def proxy_query_history(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Recent queries for this tenant -> ai-agent /api/v1/ai/query/history."""
    return await _proxy(request, client, "/api/v1/ai/query/history")


# --- Restock suggestions (feature 2) ---------------------------------------


@router.get("/suggestions")
async def proxy_list_suggestions(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Pending suggestions feed -> ai-agent /api/v1/ai/suggestions."""
    return await _proxy(request, client, "/api/v1/ai/suggestions")


@router.post("/suggestions/scan")
async def proxy_suggestion_scan(
    request: Request,
    _invoke: _InvokeDep,
    _approve: _AIApproveDep,
    client: _ClientDep,
) -> Response:
    """Trigger the suggestion scan -> ai-agent /api/v1/ai/suggestions/scan."""
    return await _proxy(request, client, "/api/v1/ai/suggestions/scan")


@router.post("/suggestions/{suggestion_id}/approve")
async def proxy_approve_suggestion(
    request: Request,
    suggestion_id: uuid.UUID,
    _invoke: _InvokeDep,
    _approve: _AIApproveDep,
    client: _ClientDep,
) -> Response:
    """Approve one pending suggestion (spec §3.4 human-in-the-loop)."""
    return await _proxy(request, client, f"/api/v1/ai/suggestions/{suggestion_id}/approve")


@router.post("/suggestions/{suggestion_id}/reject")
async def proxy_reject_suggestion(
    request: Request,
    suggestion_id: uuid.UUID,
    _invoke: _InvokeDep,
    _approve: _AIApproveDep,
    client: _ClientDep,
) -> Response:
    """Reject one pending suggestion; note feeds the feedback loop."""
    return await _proxy(request, client, f"/api/v1/ai/suggestions/{suggestion_id}/reject")


# --- Stock anomalies (feature 3) --------------------------------------------


@router.get("/anomalies")
async def proxy_list_anomalies(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Anomaly feed -> ai-agent /api/v1/ai/anomalies."""
    return await _proxy(request, client, "/api/v1/ai/anomalies")


@router.post("/anomalies/scan")
async def proxy_anomaly_scan(
    request: Request,
    _invoke: _InvokeDep,
    _write: _WriteDep,
    client: _ClientDep,
) -> Response:
    """Trigger anomaly detection -> ai-agent /api/v1/ai/anomalies/scan."""
    return await _proxy(request, client, "/api/v1/ai/anomalies/scan")


@router.post("/anomalies/{anomaly_id}/resolve")
async def proxy_resolve_anomaly(
    request: Request,
    anomaly_id: uuid.UUID,
    _invoke: _InvokeDep,
    _write: _WriteDep,
    client: _ClientDep,
) -> Response:
    """Mark an anomaly resolved (human investigated)."""
    return await _proxy(request, client, f"/api/v1/ai/anomalies/{anomaly_id}/resolve")


@router.post("/anomalies/{anomaly_id}/dismiss")
async def proxy_dismiss_anomaly(
    request: Request,
    anomaly_id: uuid.UUID,
    _invoke: _InvokeDep,
    _write: _WriteDep,
    client: _ClientDep,
) -> Response:
    """Mark an anomaly as false positive (feeds tuning)."""
    return await _proxy(request, client, f"/api/v1/ai/anomalies/{anomaly_id}/dismiss")


@router.post("/anomalies/{anomaly_id}/escalate")
async def proxy_escalate_anomaly(
    request: Request,
    anomaly_id: uuid.UUID,
    _invoke: _InvokeDep,
    _write: _WriteDep,
    client: _ClientDep,
) -> Response:
    """Escalate an anomaly to admin attention."""
    return await _proxy(request, client, f"/api/v1/ai/anomalies/{anomaly_id}/escalate")


# --- Cross-module intelligence narrator (SKY-63) -----------------------------

# The narrator gate needs the request-scoped session (its own dependency),
# so these routes use the client directly rather than the shared _InvokeDep
# set - the combined narrator deps already enforce invoke + all module reads.


@router.get("/narrator/digest")
async def proxy_narrator_digest(
    request: Request,
    _narrator: _NarratorDep,
    client: _ClientDep,
) -> Response:
    """Daily executive digest -> ai-agent /api/v1/ai/narrator/digest."""
    return await _proxy(request, client, "/api/v1/ai/narrator/digest")


@router.post("/narrator/digest/refresh")
async def proxy_narrator_refresh(
    request: Request,
    _narrator_refresh: _NarratorRefreshDep,
    client: _ClientDep,
) -> Response:
    """Force-recompute today's digest -> ai-agent /api/v1/ai/narrator/digest/refresh."""
    return await _proxy(request, client, "/api/v1/ai/narrator/digest/refresh")


# --- L3 HR/Payroll narratives (HR-AI-003) -----------------------------------
# Narration happens in ai-agent; the gate lives HERE at the core edge
# (erp.hr.ai.management), mirroring the narrator/refresh convention.


@router.get("/l3/{kind}")
async def proxy_l3_narrative(
    request: Request,
    kind: str,
    _management: _HrAiManagementDep,
    client: _ClientDep,
) -> Response:
    """L3 narrative for a kind -> ai-agent /api/v1/ai/l3/{kind}."""
    return await _proxy(request, client, f"/api/v1/ai/l3/{kind}")


@router.post("/l3/{kind}/refresh")
async def proxy_l3_narrative_refresh(
    request: Request,
    kind: str,
    _refresh: _HrAiL3RefreshDep,
    client: _ClientDep,
) -> Response:
    """Force-recompute an L3 narrative -> ai-agent /api/v1/ai/l3/{kind}/refresh.

    Two-tier gate: erp.hr.ai.management (read) AND erp.ai.l3.refresh (refresh),
    mirroring the narrator/refresh convention.
    """
    return await _proxy(request, client, f"/api/v1/ai/l3/{kind}/refresh")


# --- Demand forecasting (feature 4) ------------------------------------------


@router.get("/forecast/{product_id}")
async def proxy_get_forecast(
    request: Request,
    product_id: uuid.UUID,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Demand forecast for one product -> ai-agent /api/v1/ai/forecast/{id}."""
    return await _proxy(request, client, f"/api/v1/ai/forecast/{product_id}")


# --- ABC inventory classification (feature 5) --------------------------------


@router.get("/abc")
async def proxy_list_abc_classifications(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """ABC banding for the tenant's products -> ai-agent /api/v1/ai/abc."""
    return await _proxy(request, client, "/api/v1/ai/abc")


@router.get("/abc/summary")
async def proxy_get_abc_summary(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """ABC band counts (A/B/C) -> ai-agent /api/v1/ai/abc/summary."""
    return await _proxy(request, client, "/api/v1/ai/abc/summary")


# --- Supplier risk (SKY-86) --------------------------------------------------


@router.get("/supplier-risk")
async def proxy_list_supplier_risk(
    request: Request,
    _invoke: _InvokeDep,
    _read: _ReadDep,
    client: _ClientDep,
) -> Response:
    """Supplier risk grades -> ai-agent /api/v1/ai/supplier-risk."""
    return await _proxy(request, client, "/api/v1/ai/supplier-risk")


# --- CRM AI (SKY-61) -------------------------------------------------------

CRM_READ_DEPS = (_require_ai_invoke, _require_crm_read)
CRM_WRITE_DEPS = (_require_ai_invoke, _require_crm_write)


@router.get("/crm/follow-ups")
async def proxy_list_crm_follow_ups(
    request: Request,
    _invoke: _InvokeDep,
    _crm_read: _CrmReadDep,
    client: _ClientDep,
) -> Response:
    """Pending CRM follow-up suggestions -> ai-agent /api/v1/ai/crm/follow-ups."""
    return await _proxy(request, client, "/api/v1/ai/crm/follow-ups")


@router.post("/crm/follow-ups/{suggestion_id}/apply")
async def proxy_apply_crm_follow_up(
    request: Request,
    suggestion_id: uuid.UUID,
    _invoke: _InvokeDep,
    _crm_write: _CrmWriteDep,
    client: _ClientDep,
) -> Response:
    """Apply a CRM follow-up suggestion -> ai-agent /api/v1/ai/crm/follow-ups/{id}/apply."""
    return await _proxy(request, client, f"/api/v1/ai/crm/follow-ups/{suggestion_id}/apply")


@router.post("/crm/follow-ups/{suggestion_id}/dismiss")
async def proxy_dismiss_crm_follow_up(
    request: Request,
    suggestion_id: uuid.UUID,
    _invoke: _InvokeDep,
    _crm_write: _CrmWriteDep,
    client: _ClientDep,
) -> Response:
    """Dismiss a CRM follow-up suggestion -> ai-agent /api/v1/ai/crm/follow-ups/{id}/dismiss."""
    return await _proxy(request, client, f"/api/v1/ai/crm/follow-ups/{suggestion_id}/dismiss")


@router.post("/crm/leads/{lead_id}/score")
async def proxy_score_crm_lead(
    request: Request,
    lead_id: uuid.UUID,
    _invoke: _InvokeDep,
    _crm_write: _CrmWriteDep,
    client: _ClientDep,
) -> Response:
    """Score a CRM lead -> ai-agent /api/v1/ai/crm/leads/{id}/score."""
    return await _proxy(request, client, f"/api/v1/ai/crm/leads/{lead_id}/score")


@router.get("/crm/opportunities/{opportunity_id}/health")
async def proxy_crm_deal_health(
    request: Request,
    opportunity_id: uuid.UUID,
    _invoke: _InvokeDep,
    _crm_read: _CrmReadDep,
    client: _ClientDep,
) -> Response:
    """CRM deal health assessment -> ai-agent /api/v1/ai/crm/opportunities/{id}/health."""
    return await _proxy(request, client, f"/api/v1/ai/crm/opportunities/{opportunity_id}/health")


@router.post("/crm/opportunities/sweep")
async def proxy_crm_deal_health_sweep(
    request: Request,
    _invoke: _InvokeDep,
    _crm_read: _CrmReadDep,
    client: _ClientDep,
) -> Response:
    """Recheck deal health for all open opportunities -> ai-agent /api/v1/ai/crm/opportunities/sweep."""
    return await _proxy(request, client, "/api/v1/ai/crm/opportunities/sweep")


# --- NL report builder (SKY-80) ---------------------------------------------

# generate builds a preview from report definitions the caller can already
# read (erp.reports.read); save persists a NEW definition and additionally
# requires erp.reports.create. The AI service is still only a proxy: Core
# authorizes first, then forwards the caller's JWT + tenant slug verbatim.


@router.post("/report-builder/generate")
async def proxy_report_builder_generate(
    request: Request,
    _invoke: _InvokeDep,
    _reports_read: _ReportsReadDep,
    client: _ClientDep,
) -> Response:
    """NL report generation -> ai-agent /api/v1/ai/report-builder/generate."""
    return await _proxy(request, client, "/api/v1/ai/report-builder/generate")


@router.post("/report-builder/save")
async def proxy_report_builder_save(
    request: Request,
    _invoke: _InvokeDep,
    _reports_create: _ReportsCreateDep,
    client: _ClientDep,
) -> Response:
    """Persist a generated report spec -> ai-agent /api/v1/ai/report-builder/save."""
    return await _proxy(request, client, "/api/v1/ai/report-builder/save")


# --- Sales Coach AI (SKY-90) -------------------------------------------------

# Read gate: list the pending coaching suggestion queue for the tenant (or a
# single rep). Review gate: accept/dismiss decisions that flip suggestion status.
# coaching.read for reads, coaching.review for the write-like decision action.


@router.get("/coaching/suggestions")
async def proxy_list_coaching_suggestions(
    request: Request,
    _invoke: _InvokeDep,
    _coaching_read: _CoachingReadDep,
    client: _ClientDep,
) -> Response:
    """Pending coaching suggestion queue -> ai-agent /api/v1/ai/coaching/suggestions."""
    return await _proxy(request, client, "/api/v1/ai/coaching/suggestions")


@router.post("/coaching/suggestions/{suggestion_id}/review")
async def proxy_review_coaching_suggestion(
    request: Request,
    suggestion_id: uuid.UUID,
    _invoke: _InvokeDep,
    _coaching_review: _CoachingReviewDep,
    client: _ClientDep,
) -> Response:
    """Accept or dismiss a coaching suggestion -> ai-agent /api/v1/ai/coaching/suggestions/{id}/review."""
    return await _proxy(request, client, f"/api/v1/ai/coaching/suggestions/{suggestion_id}/review")


# --- Audit Guardian AI (SKY-90) ----------------------------------------------

# Read gate: list weekly reports + fetch detail (flagged-event evidence).
# Review gate: operator acknowledgement of the integrity report.


@router.get("/guardian/reports")
async def proxy_list_guardian_reports(
    request: Request,
    _invoke: _InvokeDep,
    _guardian_read: _GuardianReadDep,
    client: _ClientDep,
) -> Response:
    """Weekly integrity report list -> ai-agent /api/v1/ai/guardian/reports."""
    return await _proxy(request, client, "/api/v1/ai/guardian/reports")


@router.get("/guardian/reports/{report_id}")
async def proxy_get_guardian_report(
    request: Request,
    report_id: uuid.UUID,
    _invoke: _InvokeDep,
    _guardian_read: _GuardianReadDep,
    client: _ClientDep,
) -> Response:
    """Report detail with flagged events + evidence -> ai-agent /api/v1/ai/guardian/reports/{id}."""
    return await _proxy(request, client, f"/api/v1/ai/guardian/reports/{report_id}")


@router.post("/guardian/reports/{report_id}/review")
async def proxy_review_guardian_report(
    request: Request,
    report_id: uuid.UUID,
    _invoke: _InvokeDep,
    _guardian_review: _GuardianReviewDep,
    client: _ClientDep,
) -> Response:
    """Mark a guardian report reviewed -> ai-agent /api/v1/ai/guardian/reports/{id}/review."""
    return await _proxy(request, client, f"/api/v1/ai/guardian/reports/{report_id}/review")
