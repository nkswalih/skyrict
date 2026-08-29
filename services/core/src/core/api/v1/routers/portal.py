"""Employee self-service portal — own leave balances and requests.

Endpoints live under ``/api/v1/portal/*`` and are gated by
:func:`core.api.deps.require_employee_self_service`, which checks the
``erp.leave.self`` permission AND resolves the caller's linked employee row.
Every query forces ``employee_id`` server-side — a portal user can only ever
see or create their own data; HR's admin endpoints are not reused for reads.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from core.api.deps import (
    get_leave_service,
    get_tenant_id,
    get_utilization_service,
    require_employee_self_service,
)
from core.api.v1.routers.errors import raise_from_service_error
from core.api.v1.schemas.hr import (
    EmployeeOut,
    LeaveBalanceOut,
    LeaveRequestOut,
    LeaveTypeOut,
    PortalLeaveRequestCreate,
    PortalMeOut,
)
from core.features.ai_hr.schemas import UtilizationAlertOut, utilization_alert_to_out
from core.features.ai_hr.utilization_service import UtilizationService
from core.features.hr.service import LeaveService
from skyrict_common.schemas import ResponseEnvelope

router = APIRouter(prefix="/portal", tags=["employee-portal"])


@router.get("/me", response_model=ResponseEnvelope[PortalMeOut])
async def portal_me(
    current_user: dict[str, Any] = Depends(require_employee_self_service),
    leave_svc: LeaveService = Depends(get_leave_service),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> ResponseEnvelope[PortalMeOut]:
    """Who am I + my leave-type catalogue + materialized balances.

    Balances exist only for accrual types (annual grants); non-accrual types
    render from the catalogue without a balance row.
    """
    employee = current_user["employee"]
    employee_id = employee.id
    assert employee_id is not None  # bound by require_employee_self_service
    balances = await leave_svc.list_balances(employee_id, tenant_id=tenant_id)
    leave_types = await leave_svc.list_leave_types(tenant_id)
    return ResponseEnvelope(
        data=PortalMeOut(
            employee=EmployeeOut.model_validate(employee),
            leave_types=[LeaveTypeOut.model_validate(t) for t in leave_types],
            balances=[LeaveBalanceOut.model_validate(b) for b in balances],
        )
    )


@router.get("/leave/requests", response_model=ResponseEnvelope[list[LeaveRequestOut]])
async def list_my_leave_requests(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(require_employee_self_service),
    leave_svc: LeaveService = Depends(get_leave_service),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> ResponseEnvelope[list[LeaveRequestOut]]:
    """Own request history, newest first (repository ordering), self-scoped."""
    requests = await leave_svc.list_leave_requests(
        tenant_id,
        status=status,
        employee_id=current_user["employee"].id,
        limit=limit,
        offset=offset,
    )
    return ResponseEnvelope(data=[LeaveRequestOut.model_validate(r) for r in requests])


@router.post("/leave/requests", response_model=ResponseEnvelope[LeaveRequestOut], status_code=201)
async def submit_my_leave_request(
    body: PortalLeaveRequestCreate,
    current_user: dict[str, Any] = Depends(require_employee_self_service),
    leave_svc: LeaveService = Depends(get_leave_service),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> ResponseEnvelope[LeaveRequestOut]:
    """Submit an own leave request — reuses HR's request() rules verbatim."""
    try:
        request = await leave_svc.request(
            tenant_id=tenant_id,
            employee_id=current_user["employee"].id,
            leave_type=body.leave_type,
            start_date=body.start_date,
            end_date=body.end_date,
            reason=body.reason,
            actor_user_id=current_user["user_id"],
        )
    except ValueError as exc:
        raise_from_service_error(exc)
    return ResponseEnvelope(
        data=LeaveRequestOut.model_validate(request), message="Leave request submitted"
    )


@router.get("/leave/alerts", response_model=ResponseEnvelope[list[UtilizationAlertOut]])
async def my_leave_alerts(
    current_user: dict[str, Any] = Depends(require_employee_self_service),
    utilization_service: UtilizationService = Depends(get_utilization_service),
    tenant_id: uuid.UUID = Depends(get_tenant_id),
) -> ResponseEnvelope[list[UtilizationAlertOut]]:
    """The caller's OWN utilization alerts (forfeit warnings), self-scoped."""
    employee = current_user["employee"]
    alerts = await utilization_service.own_alerts(tenant_id, employee.id)
    return ResponseEnvelope(
        data=[utilization_alert_to_out(a) for a in alerts],
        message="Your utilization alerts retrieved",
    )
