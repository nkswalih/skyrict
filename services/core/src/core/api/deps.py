"""FastAPI dependency injection — get_tenant_context, get_current_user, require_permission.

The api layer is the sole composition point: shared authentication and
authorization dependencies live here, mirroring identity/api/deps.py. Core owns
its ERP RBAC tables, so ``require_permission`` resolves roles -> permissions
from the database at request time (never from JWT claims) through
:class:`RbacRepository`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from core.core.logging import get_logger
from core.core.security import cross_check_jwt_tenant, verify_jwt
from core.core.tenant_context import TenantContext
from core.db.rbac import RbacRepository, grants_permission
from core.db.session import get_db
from core.domain.value_objects import DataScope
from core.features.audit.repository import AuditRepository
from core.features.inventory.repository import InventoryRepository
from skyrict_common.exceptions import AuthenticationError, PermissionDeniedError

if TYPE_CHECKING:
    from core.core.audit_service import AuditService as CoreAuditService
    from core.features.ai_hr.anomaly_service import AnomalyService
    from core.features.ai_hr.eval_repository import EvalRunRepository
    from core.features.ai_hr.pattern_data_repository import (
        AiHrPatternDataRepository as PatternDataRepository,
    )
    from core.features.ai_hr.quality_service import QualityService
    from core.features.ai_hr.service import AiHrService
    from core.features.ai_hr.suggestion_service import SuggestionService
    from core.features.ai_hr.utilization_service import UtilizationService
    from core.features.audit.service import AuditService
    from core.features.crm.service import CrmService
    from core.features.crm.workspace_service import CrmWorkspaceService
    from core.features.finance.ports import AuditSink
    from core.features.finance.service import FinanceService
    from core.features.hr.repository import HrRepository
    from core.features.hr.service import (
        AttendanceService,
        DepartmentService,
        EmployeeService,
        LeaveService,
    )
    from core.features.inventory.service import InventoryService
    from core.features.payroll.service import PayrollService
    from core.features.sales.service import SalesService

logger = get_logger("core.deps")

security = HTTPBearer(auto_error=False)


def get_tenant_context() -> str:
    """Return the current request's tenant ID (resolved by the middleware)."""
    return TenantContext.get()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, Any]:
    """Extract and verify the JWT from the Authorization header.

    Uses ``verify_jwt`` — the ONE AND ONLY decode path. The routed tenant is
    consumed from ``TenantContext`` (resolved once by the middleware) and the
    JWT-vs-routed cross-check is enforced here again as defense in depth, so a
    token can never be used against a different tenant even if a route is
    reached without going through the middleware.

    Raises:
        AuthenticationError: If no token, the token is invalid/expired, or the
            token ``type`` is not ``access``.
        TenantContextMissingError: If the middleware hasn't resolved a tenant.
        TenantMismatchError: If the token's tenant claim differs from the routed tenant.
    """
    if credentials is None:
        raise AuthenticationError("Missing Authorization header")

    payload = verify_jwt(credentials.credentials)

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type")

    # Single source of truth: the routed tenant was resolved by the middleware.
    routed_tenant_id = TenantContext.get()
    cross_check_jwt_tenant(payload.get("tenant_id"), routed_tenant_id)
    TenantContext.set_user_id(payload["sub"])

    # The JWT ``sub`` is identity's user UUID as text; every core user_id
    # column (core_user_roles, core_audit_log, hr employees) is a UUID, so
    # normalize once here — downstream permission resolution, audit actors,
    # and route handlers all receive a real UUID.
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, TypeError):
        raise AuthenticationError("Invalid token subject") from None

    return {
        "user_id": user_id,
        "tenant_id": routed_tenant_id,
        "token_payload": payload,
    }


def require_permission(permission: str) -> Callable[[], Awaitable[dict[str, Any]]]:
    """Dependency factory — returns a dependency that checks a specific permission.

    Resolves the user's grants from the database (core_roles / core_user_roles)
    at request time and fails closed with ``PermissionDeniedError`` when the
    required key (or the wildcard ``"*"``) is not present.
    """

    async def _check(
        current_user: dict[str, Any] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        granted = await RbacRepository(db).resolve_user_permissions(
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
        )
        if not grants_permission(granted, permission):
            raise PermissionDeniedError(f"Missing required permission: {permission}")
        return current_user

    return _check


def require_any_permission(*permissions: str) -> Callable[[], Awaitable[dict[str, Any]]]:
    """Dependency factory — grants access when ANY of ``permissions`` is held.

    Used for actions the spec allows under either of two keys (e.g. cancelling
    a leave request under ``erp.hr.write`` OR ``erp.hr.approve``, §7). Each
    alternative resolves through the same DB-backed grant path as
    :func:`require_permission` and fails closed with ``PermissionDeniedError``
    when none is held.
    """

    async def _check(
        current_user: dict[str, Any] = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> dict[str, Any]:
        granted = await RbacRepository(db).resolve_user_permissions(
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
        )
        if not any(grants_permission(granted, permission) for permission in permissions):
            alternatives = ", ".join(permissions)
            raise PermissionDeniedError(f"Missing required permission: one of {alternatives}")
        return current_user

    return _check


def get_tenant_id() -> uuid.UUID:
    """Return the current request's tenant id as a UUID (resolved by the middleware)."""
    return uuid.UUID(TenantContext.get())


class _NoopIdentityUserPort:
    """ACCEPTED Phase-1 deviation: identity-service stand-in for :class:`IdentityUserPort`.

    ``IdentityUserPort`` exists so ``EmployeeService`` can validate
    ``employee.user_id`` against the identity service (in-process or HTTP) and
    this class is its wiring point at the composition root — the one place to
    swap it when the identity-integration ticket lands. Phase 1 deliberately
    FAILS OPEN (logs a warning) so ``POST /hr/employees`` works without an
    identity round-trip; until then ``user_id`` on hire is accepted as-is, so
    a hire may reference a nonexistent or cross-tenant user id.

    This is a recorded deviation, not an oversight — see the callout in
    ``docs/modules/hr-payroll.md`` §2.4. The security matrix's "validated"
    row for ``user_id`` is green ONLY under this deviation; no test asserts
    the no-op, and the swap must land with the identity-integration ticket.
    """

    async def validate_user(self, user_id: uuid.UUID, *, tenant_id: uuid.UUID) -> None:
        logger.warning(
            "identity.validate_user_noop",
            user_id=str(user_id),
            tenant_id=str(tenant_id),
            message="identity-service user validation is not wired yet (Phase 1)",
        )


def get_hr_repo(db: AsyncSession = Depends(get_db)) -> HrRepository:
    from core.db.sequence_repository import SequenceRepository
    from core.features.hr.repository import HrRepository

    return HrRepository(db, next_sequence=SequenceRepository(db).next_value)


def get_core_audit_service(db: AsyncSession = Depends(get_db)) -> CoreAuditService:
    from core.core.audit_service import AuditService
    from core.db.audit_repository import AuditLogRepository

    return AuditService(AuditLogRepository(db))


def get_department_service(
    repo: HrRepository = Depends(get_hr_repo),
    audit: CoreAuditService = Depends(get_core_audit_service),
) -> DepartmentService:
    from core.features.hr.service import DepartmentService

    return DepartmentService(repository=repo, audit=audit)


def get_employee_service(
    repo: HrRepository = Depends(get_hr_repo),
    audit: CoreAuditService = Depends(get_core_audit_service),
) -> EmployeeService:
    from core.features.hr.service import EmployeeService

    return EmployeeService(repository=repo, audit=audit, identity=_NoopIdentityUserPort())


def get_leave_service(
    repo: HrRepository = Depends(get_hr_repo),
    audit: CoreAuditService = Depends(get_core_audit_service),
) -> LeaveService:
    from core.features.hr.service import LeaveService

    return LeaveService(repository=repo, audit=audit)


async def require_employee_self_service(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    repo: HrRepository = Depends(get_hr_repo),
) -> dict[str, Any]:
    """Portal gate — permission check + employee binding in one dependency.

    The caller must hold ``erp.leave.self`` (the ``employee_self_service`` role
    grants exactly that key; the owner wildcard also passes). The linked
    ``erp_employees`` row is resolved via ``user_id`` — bound on the identity
    side at invite-accept (shared-DB mirror). Fails closed when the permission
    is missing or no employee record is (yet) linked to the account.
    """
    from core.core.permissions import ERP_LEAVE_SELF

    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]
    granted = await RbacRepository(db).resolve_user_permissions(
        user_id=user_id,
        tenant_id=tenant_id,
    )
    if not grants_permission(granted, ERP_LEAVE_SELF):
        raise PermissionDeniedError(f"Missing required permission: {ERP_LEAVE_SELF}")
    employee = await repo.get_employee_by_user_id(user_id, tenant_id)
    if employee is None:
        raise PermissionDeniedError(
            "Your account is not linked to an employee record. Ask HR to check "
            "that your work email matches your employee profile."
        )
    return {**current_user, "employee": employee}


def get_attendance_service(
    repo: HrRepository = Depends(get_hr_repo),
    audit: CoreAuditService = Depends(get_core_audit_service),
) -> AttendanceService:
    from core.features.hr.service import AttendanceService

    return AttendanceService(repository=repo, audit=audit)


def get_payroll_service(
    db: AsyncSession = Depends(get_db),
    audit: CoreAuditService = Depends(get_core_audit_service),
) -> PayrollService:
    """Payroll service with ``LeaveService`` injected as the leave ledger.

    ``LeaveService`` implements the whole ``LeaveLedgerPort`` (approved unpaid
    leave days, accrual-type catalogue, idempotent annual accrual — Rule 4), so
    the payroll feature never imports the HR feature directly. The HR repository
    is shared (same ``db`` session), keeping payroll-driven accrual in the same
    transaction as the compute.
    """
    from core.db.sequence_repository import SequenceRepository
    from core.features.hr.repository import HrRepository
    from core.features.hr.service import LeaveService
    from core.features.payroll.repository import PayrollRepository
    from core.features.payroll.service import PayrollService

    return PayrollService(
        repository=PayrollRepository(db, next_sequence=SequenceRepository(db).next_value),
        leave_ledger=LeaveService(
            repository=HrRepository(db, next_sequence=SequenceRepository(db).next_value),
            audit=audit,
        ),
        audit=audit,
    )


def get_ai_hr_service(
    db: AsyncSession = Depends(get_db),
    audit: CoreAuditService = Depends(get_core_audit_service),
) -> AiHrService:
    """Composition root for the HR/Payroll AI features (L1 + attrition).

    Shares ONE request-scoped session across the aggregate and attrition
    repositories so a lazy re-score upserts in the same transaction it reads.
    """
    from core.core.config import settings
    from core.features.ai_hr.attrition_repository import AiHrAttritionRepository
    from core.features.ai_hr.repository import AiHrRepository
    from core.features.ai_hr.service import AiHrService

    return AiHrService(
        repository=AiHrRepository(db),
        attrition_repository=AiHrAttritionRepository(db),
        audit=audit,
        attrition_refresh_days=settings.AI_HR_REFRESH_INTERVAL_DAYS,
    )


def get_quality_service(
    db: AsyncSession = Depends(get_db),
) -> QualityService:
    """Composition root for the HR data-quality scorer (HR-AI-002, 8.1.3)."""
    from core.core.config import settings
    from core.features.ai_hr.quality_repository import AiHrQualityRepository
    from core.features.ai_hr.quality_service import QualityService

    return QualityService(
        repository=AiHrQualityRepository(db),
        refresh_days=settings.AI_HR_REFRESH_INTERVAL_DAYS,
    )


def get_utilization_service(
    db: AsyncSession = Depends(get_db),
) -> UtilizationService:
    """Composition root for the leave-balance utilization scanner (8.1.4)."""
    from core.core.config import settings
    from core.features.ai_hr.utilization_repository import AiHrUtilizationRepository
    from core.features.ai_hr.utilization_service import UtilizationService

    return UtilizationService(
        repository=AiHrUtilizationRepository(db),
        refresh_days=settings.AI_HR_UTILIZATION_SCAN_INTERVAL_DAYS,
    )


def get_anomaly_service(
    db: AsyncSession = Depends(get_db),
) -> AnomalyService:
    """Composition root for the leave-pattern anomaly scanner (8.2.1)."""
    from core.core.config import settings
    from core.features.ai_hr.anomaly_repository import AiHrAnomalyRepository
    from core.features.ai_hr.anomaly_service import AnomalyService

    return AnomalyService(
        repository=AiHrAnomalyRepository(db),
        refresh_days=settings.AI_HR_ANOMALY_SCAN_INTERVAL_DAYS,
    )


def get_suggestion_service(
    db: AsyncSession = Depends(get_db),
) -> SuggestionService:
    """Composition root for the smart leave-window suggestion engine (8.2.4)."""
    from core.core.config import settings
    from core.features.ai_hr.suggestion_repository import AiHrSuggestionRepository
    from core.features.ai_hr.suggestion_service import SuggestionService

    return SuggestionService(
        repository=AiHrSuggestionRepository(db),
        refresh_days=settings.AI_HR_SUGGESTION_SCAN_INTERVAL_DAYS,
    )


def get_eval_repository(db: AsyncSession = Depends(get_db)) -> EvalRunRepository:
    """Composition root for the model-eval telemetry repository (SKY-72)."""
    from core.features.ai_hr.eval_repository import EvalRunRepository

    return EvalRunRepository(db)


def get_pattern_data_repository(db: AsyncSession = Depends(get_db)) -> PatternDataRepository:
    """Composition root for the AI pattern-engine config tables (0024)."""
    from core.features.ai_hr.pattern_data_repository import AiHrPatternDataRepository

    return AiHrPatternDataRepository(db)


async def get_hr_ai_individual(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """True when the caller may view individual (L2) attrition scores.

    ``erp.hr.ai.individual`` is granted only to the owner and a dedicated exec
    role (spec §3) — NOT org_admin/dept_manager. The attrition endpoint uses
    this to downgrade to an aggregates-only (L1) 403 body when absent.
    """
    from core.core.permissions import ERP_HR_AI_INDIVIDUAL

    granted = await RbacRepository(db).resolve_user_permissions(
        user_id=current_user["user_id"],
        tenant_id=current_user["tenant_id"],
    )
    return grants_permission(granted, ERP_HR_AI_INDIVIDUAL)


def get_finance_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FinanceService:
    """Composition root for the finance feature.

    Wires the concrete repository, the shared audit sink, the after-commit
    event publisher, and the CRM customer port onto ONE request-scoped
    session — so audit rows, the business mutation, and (later) published
    events all commit atomically. The request ID becomes the correlation ID
    stamped on money-moment events.
    """
    from core.db.sequence_repository import SequenceRepository
    from core.events.producers import get_event_producer
    from core.events.producers.finance_events import FinanceEventPublisher
    from core.features.crm.repository import CrmRepository
    from core.features.finance.repository import FinanceRepository
    from core.features.finance.service import FinanceService
    from core.features.sales.repository import SalesRepository

    correlation_id = getattr(request.state, "request_id", None)
    crm_repo = CrmRepository(db)
    sales_repo = SalesRepository(db, next_sequence=SequenceRepository(db).next_value)
    return FinanceService(
        repo=FinanceRepository(db),
        audit=cast("AuditSink", AuditRepository(db)),
        events=FinanceEventPublisher(session=db, producer=get_event_producer()),
        correlation_id=correlation_id,
        customers=crm_repo,
        timeline=crm_repo,
        order_lookup=sales_repo,
    )


async def get_adjustment_authority(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """True when the caller may approve above-threshold inventory adjustments.

    Resolves ``erp.inventory.adjust.approve`` (or the ``*`` wildcard) from the
    DB grants at request time. The threshold itself is enforced by the service
    (``settings.INVENTORY_ADJUST_APPROVE_THRESHOLD``) — this dependency only
    answers "may this user approve?".
    """
    from core.core.permissions import ERP_INVENTORY_ADJUST_APPROVE

    granted = await RbacRepository(db).resolve_user_permissions(
        user_id=current_user["user_id"],
        tenant_id=current_user["tenant_id"],
    )
    return grants_permission(granted, ERP_INVENTORY_ADJUST_APPROVE)


# --- Repository deps ---


def get_audit_repo(db: AsyncSession = Depends(get_db)) -> AuditRepository:
    return AuditRepository(db)


def get_audit_service(audit_repo: AuditRepository = Depends(get_audit_repo)) -> AuditService:
    from core.features.audit.service import AuditService

    return AuditService(audit_repo)


def get_inventory_repo(db: AsyncSession = Depends(get_db)) -> InventoryRepository:
    return InventoryRepository(db)


def get_inventory_service(
    inventory_repo: InventoryRepository = Depends(get_inventory_repo),
    audit_service: AuditService = Depends(get_audit_service),
) -> InventoryService:
    from core.features.inventory.service import InventoryService

    return InventoryService(inventory_repo, audit_service)


# --- CRM & Sales deps ---


async def get_current_scope(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[DataScope, uuid.UUID | None]:
    """Resolve the request's effective data scope + team id from the DB grants.

    CRM repository queries narrow owner/team-scoped rows by this pair, so the
    scope is resolved ONCE here at the API boundary and never re-derived by
    route handlers. ``scope_id`` (team id) is None when the caller holds no
    team-scoped grant; ``DataScope.ALL`` callers ignore it.
    """
    return await RbacRepository(db).resolve_user_scope(
        user_id=current_user["user_id"],
        tenant_id=current_user["tenant_id"],
    )


def get_crm_service(
    db: AsyncSession = Depends(get_db),
    audit_service: AuditService = Depends(get_audit_service),
) -> CrmService:
    """Composition root for the CRM feature.

    ``CrmRepository`` backs the CrmRepositoryPort (leads/opportunities/
    customers) AND the CrmTimelinePort (curated timeline writes) — so the
    repository instance is shared, not rebuilt, across the two roles.
    """
    from core.db.sequence_repository import SequenceRepository
    from core.features.crm.repository import CrmRepository
    from core.features.crm.service import CrmService

    crm_repo = CrmRepository(db, next_sequence=SequenceRepository(db).next_value)
    return CrmService(
        repository=crm_repo,
        audit=audit_service,
        timeline=crm_repo,
    )


def get_crm_workspace_service(
    db: AsyncSession = Depends(get_db),
    audit_service: AuditService = Depends(get_audit_service),
) -> CrmWorkspaceService:
    """Composition root for the CRM workspace surface."""
    from core.features.crm.repository import CrmRepository
    from core.features.crm.workspace_service import CrmWorkspaceService

    return CrmWorkspaceService(
        repository=CrmRepository(db),
        audit=audit_service,
    )


def get_sales_service(
    db: AsyncSession = Depends(get_db),
    audit_service: AuditService = Depends(get_audit_service),
    finance: FinanceService = Depends(get_finance_service),
) -> SalesService:
    """Composition root for the sales feature.

    Wires every port the service depends on without importing another feature
    module: the sales repository (with the shared per-tenant sequence), CRM's
    repository as the customer port AND the timeline port (an order creation
    appends its business event to the customer's timeline), inventory's
    repository for product and warehouse resolution, inventory's service as
    the whole-order stock lifecycle port, and finance's service as the
    invoicing port (so an order's fulfilment creates the invoice in the same
    request transaction).
    """
    from core.db.sequence_repository import SequenceRepository
    from core.features.crm.repository import CrmRepository
    from core.features.inventory.service import InventoryService
    from core.features.sales.repository import SalesRepository
    from core.features.sales.service import SalesService

    inventory_repo = InventoryRepository(db)
    crm_repo = CrmRepository(db)
    return SalesService(
        repository=SalesRepository(db, next_sequence=SequenceRepository(db).next_value),
        customers=crm_repo,
        stock=InventoryService(inventory_repo, audit_service),
        products=inventory_repo,
        warehouses=inventory_repo,
        invoice=finance,
        audit=audit_service,
        timeline=crm_repo,
        cogs=finance,
    )
