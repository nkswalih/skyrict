"""``/api/v1/ai/*`` proxy routes — permission checks BEFORE forwarding.

Permission matrix (ticket SKY-68, spec 6.3): every AI call needs
``erp.ai.invoke`` AND the module key for the touched domain —
``erp.inventory.read`` for reads, ``erp.inventory.write`` for anomaly
dispositions, ``erp.inventory.ai.approve`` for suggestion scan/approve/reject.

The JWT is forwarded verbatim; ai-agent re-verifies it against the
relayed tenant slug (spec 1.4: AI is a proxy, not an auth bypass).

Path ids are typed ``uuid.UUID`` so FastAPI rejects anything else with
422 before the handler runs — the forwarded URL only ever embeds the
canonical hyphenated form (no ``/``, ``?`` or traversal sequences can
reach the upstream request target).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from core.api.deps import require_permission
from core.core.permissions import (
    ERP_AI_INVOKE,
    ERP_INVENTORY_AI_APPROVE,
    ERP_INVENTORY_READ,
    ERP_INVENTORY_WRITE,
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

_InvokeDep = Annotated[dict[str, Any], Depends(_require_ai_invoke)]
_ReadDep = Annotated[dict[str, Any], Depends(_require_inventory_read)]
_WriteDep = Annotated[dict[str, Any], Depends(_require_inventory_write)]
_AIApproveDep = Annotated[dict[str, Any], Depends(_require_inventory_ai_approve)]


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
    """Approve one pending suggestion (spec 3.4 human-in-the-loop)."""
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
