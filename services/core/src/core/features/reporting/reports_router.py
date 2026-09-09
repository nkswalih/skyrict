"""Reports API router (RPT-BE-001).

Endpoints:
    GET  /api/v1/reports             - list active definitions (optionally by module)
    POST /api/v1/reports             - create a report from a whitelisted template (RPT-AI-001)
    GET  /api/v1/reports/{slug}      - definition metadata
    POST /api/v1/reports/{slug}/run  - execute a parametrized report, store snapshot
    GET  /api/v1/reports/{slug}/snapshots - stored snapshot list (Commit 2)
    POST /api/v1/reports/{slug}/export   - CSV export, full set, audited (Commit 3)

Every read endpoint is gated by ``erp.reports.read``; the create endpoint is
gated by ``erp.reports.create``. The run path never accepts ``tenant_id`` from
the caller (it is bound from the authenticated session) and rejects
unknown/mistyped params with 422 BEFORE any SQL executes. The create path only
accepts SQL that exactly matches a whitelisted template.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse

from core.api.deps import get_report_service, require_permission
from core.core.permissions import ERP_REPORTS_CREATE, ERP_REPORTS_READ
from core.features.reporting.reports_schemas import (
    ReportCreateRequest,
    ReportCreateResult,
    ReportDefinitionRead,
    ReportRunRequest,
    ReportRunResult,
    ReportSnapshotRead,
)
from core.features.reporting.seeds import find_seed_for_sql
from core.features.reporting.service import ReportService
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/reports", tags=["reports"])

# Keep one dependency symbol for route wiring and unit-test overrides while the
# actual database composition remains in the API dependency layer.
_get_service = get_report_service
_require_reports_read = require_permission(ERP_REPORTS_READ)
_require_reports_create = require_permission(ERP_REPORTS_CREATE)


def _to_definition_read(definition: Any) -> ReportDefinitionRead:
    """Serialize a definition, overlaying the canonical seed's NL vocabulary.

    ``dataset``/``dimensions``/``measures`` are not stored columns - they are
    resolved from the canonical seed whose SQL matches the definition, so both
    seeded reports and user-created saved reports (whose SQL is always one of
    the whitelisted templates) expose the same selectable semantics to the NL
    report builder.
    """
    read = ReportDefinitionRead.model_validate(definition, from_attributes=True)
    sql = (
        definition.get("sql") if isinstance(definition, dict) else getattr(definition, "sql", None)
    )
    if sql:
        seed = find_seed_for_sql(sql)
        if seed is not None:
            read.dataset = seed.dataset
            read.dimensions = list(seed.dimensions)
            read.measures = list(seed.measures)
    return read


def _tenant_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["tenant_id"]
    return uuid.UUID(val) if isinstance(val, str) else val


def _user_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["user_id"]
    return uuid.UUID(val) if isinstance(val, str) else val


@router.get("", response_model=ResponseEnvelope[list[ReportDefinitionRead]])
async def list_reports(
    current_user: dict[str, Any] = Depends(_require_reports_read),
    service: ReportService = Depends(_get_service),
    module: str | None = Query(default=None, max_length=32),
) -> ResponseEnvelope[list[ReportDefinitionRead]]:
    """List the tenant's active report definitions, optionally by module."""
    definitions = await service.list_reports(tenant_id=_tenant_id(current_user), module=module)
    return ResponseEnvelope(
        data=[_to_definition_read(definition) for definition in definitions],
        message=f"{len(definitions)} reports",
    )


@router.post(
    "",
    response_model=ResponseEnvelope[ReportCreateResult],
    status_code=status.HTTP_201_CREATED,
)
async def create_report(
    body: ReportCreateRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(_require_reports_create),
    service: ReportService = Depends(_get_service),
) -> ResponseEnvelope[ReportCreateResult]:
    """Persist a generated report spec as a new runnable definition.

    Gated by ``erp.reports.create`` (always shipped alongside read). The SQL
    must exactly match the whitelisted template named by ``source_slug`` - no
    arbitrary or AI-generated SQL is ever accepted. The returned definition is
    immediately runnable via ``POST /api/v1/reports/{slug}/run``.
    """
    result = await service.create_definition(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        actor_ip=request.client.host if request.client is not None else None,
        actor_agent=request.headers.get("user-agent"),
        slug=body.slug,
        title=body.title,
        module=body.module,
        description=body.description,
        sql=body.sql,
        params=body.params,
        source_slug=body.source_slug,
        default_params=body.default_params,
    )
    return ResponseEnvelope(
        data=ReportCreateResult(
            definition=_to_definition_read(result["definition"]),
            default_params=result["default_params"],
        )
    )


@router.get("/{slug}", response_model=ResponseEnvelope[ReportDefinitionRead])
async def get_report_metadata(
    slug: str,
    current_user: dict[str, Any] = Depends(_require_reports_read),
    service: ReportService = Depends(_get_service),
) -> ResponseEnvelope[ReportDefinitionRead]:
    """Return one report definition's metadata (the UI's build contract)."""
    definition = await service.get_report(tenant_id=_tenant_id(current_user), slug=slug)
    return ResponseEnvelope(data=_to_definition_read(definition))


@router.post(
    "/{slug}/run",
    response_model=ResponseEnvelope[ReportRunResult],
    status_code=status.HTTP_200_OK,
)
async def run_report(
    slug: str,
    body: ReportRunRequest,
    current_user: dict[str, Any] = Depends(_require_reports_read),
    service: ReportService = Depends(_get_service),
) -> ResponseEnvelope[ReportRunResult]:
    """Execute a parametrized report, store its snapshot, and return rows."""
    result = await service.run_report(
        tenant_id=_tenant_id(current_user),
        slug=slug,
        raw_params=body.params,
    )
    return ResponseEnvelope(data=ReportRunResult.model_validate(result))


@router.get("/{slug}/snapshots", response_model=ResponseEnvelope[list[ReportSnapshotRead]])
async def list_snapshots(
    slug: str,
    current_user: dict[str, Any] = Depends(_require_reports_read),
    service: ReportService = Depends(_get_service),
    limit: int = Query(default=20, ge=1, le=100),
) -> ResponseEnvelope[list[ReportSnapshotRead]]:
    """List the newest stored snapshots for a report (newest first)."""
    snapshots = await service.list_snapshots(
        tenant_id=_tenant_id(current_user),
        slug=slug,
        limit=limit,
    )
    return ResponseEnvelope(
        data=[
            ReportSnapshotRead.model_validate(snapshot, from_attributes=True)
            for snapshot in snapshots
        ],
        message=f"{len(snapshots)} snapshots",
    )


@router.post("/{slug}/export", response_class=StreamingResponse)
async def export_report(
    slug: str,
    body: ReportRunRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(_require_reports_read),
    service: ReportService = Depends(_get_service),
) -> StreamingResponse:
    """Run a report full and return its CSV stream with an audit trail entry.

    The audit ``REPORT_EXPORTED`` row is written BEFORE the stream starts, so
    an export is on record even if the client disconnects mid-download. The
    CSV is produced by the same coerced values as report snapshots.
    """
    prepared = await service.export_report(
        tenant_id=_tenant_id(current_user),
        user_id=_user_id(current_user),
        actor_ip=request.client.host if request.client is not None else None,
        actor_agent=request.headers.get("user-agent"),
        slug=slug,
        raw_params=body.params,
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{prepared["filename"]}"',
        "X-Report-Rows": str(prepared["rows"]),
        "X-Report-Period": prepared["period"].isoformat(),
    }
    return StreamingResponse(
        iter([prepared["csv"].encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )
