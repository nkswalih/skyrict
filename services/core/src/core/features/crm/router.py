"""CRM API routes - thin wrappers over :class:`CrmService`.

Authorization uses the ``erp.crm.*`` keys resolved at request time (read for
reads, write for mutations). Leads and opportunities are owner/team/all-scoped
- the request-resolved :class:`DataScope` (``core.db.rbac.resolve_user_scope``)
is passed straight to the service, which can only narrow it. Responses use the
standard ``skyrict_common`` envelope; list endpoints are offset/limit paged.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.api.deps import (
    get_crm_service,
    get_current_scope,
    require_permission,
)
from core.core.permissions import ERP_CRM_READ, ERP_CRM_WRITE
from core.db.session import commit_writes, get_db
from core.domain import entities as ent
from core.domain.value_objects import (
    DataScope,
    LeadStatus,
    Money,
    OpportunityStage,
)
from core.features.crm.schemas import (
    CustomerCreateRequest,
    CustomerResponse,
    CustomerUpdateRequest,
    LeadCreateRequest,
    LeadQualifyRequest,
    LeadResponse,
    LeadUpdateRequest,
    OpportunityCreateRequest,
    OpportunityResponse,
    OpportunityStageRequest,
    OpportunityStageResponse,
    OpportunityUpdateRequest,
)
from core.features.crm.service import CrmService
from skyrict_common.schemas import ListResponse, PaginationMeta, ResponseEnvelope

router = APIRouter(prefix="/crm", tags=["crm"])

_require_crm_read = require_permission(ERP_CRM_READ)
_require_crm_write = require_permission(ERP_CRM_WRITE)


def _tenant_id(current_user: dict[str, Any]) -> uuid.UUID:
    val = current_user["tenant_id"]
    return val if isinstance(val, uuid.UUID) else uuid.UUID(val)


def _user_id(current_user: dict[str, Any]) -> uuid.UUID:
    # get_current_user already normalizes the JWT ``sub`` to a real UUID.
    return cast("uuid.UUID", current_user["user_id"])


def _lead_out(lead: ent.Lead) -> LeadResponse:
    return LeadResponse.model_validate(lead)


def _opportunity_out(opportunity: ent.Opportunity) -> OpportunityResponse:
    assert opportunity.id is not None
    return OpportunityResponse(
        id=opportunity.id,
        tenant_id=opportunity.tenant_id,
        name=opportunity.name,
        lead_id=opportunity.lead_id,
        stage=opportunity.stage,
        amount=opportunity.amount.amount if opportunity.amount is not None else None,
        currency=opportunity.amount.currency if opportunity.amount is not None else None,
        probability=opportunity.probability,
        expected_close_date=opportunity.expected_close_date,
        owner_id=opportunity.owner_id,
        team_id=opportunity.team_id,
        won_at=opportunity.won_at,
        lost_at=opportunity.lost_at,
        lost_reason=opportunity.lost_reason,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
    )


def _customer_out(customer: ent.Customer) -> CustomerResponse:
    assert customer.id is not None
    return CustomerResponse(
        id=customer.id,
        tenant_id=customer.tenant_id,
        customer_code=customer.customer_code,
        name=customer.name,
        source_opportunity_id=customer.source_opportunity_id,
        email=customer.email,
        phone=customer.phone,
        credit_limit=customer.credit_limit.amount if customer.credit_limit is not None else None,
        currency=customer.credit_limit.currency if customer.credit_limit is not None else None,
        is_active=customer.is_active,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
    )


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------


@router.get("/leads", response_model=ListResponse[LeadResponse])
async def list_leads(
    status: str | None = None,
    source: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(_require_crm_read),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
) -> ListResponse[LeadResponse]:
    scope, team_id = scope_team
    leads = await svc.list_leads(
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        status=_parse_lead_status(status),
        source=source,
        offset=offset,
        limit=limit,
    )
    total = await svc.count_leads(
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        status=_parse_lead_status(status),
        source=source,
    )
    return ListResponse(
        data=[_lead_out(lead) for lead in leads],
        meta=PaginationMeta.create(total=total, page=(offset // limit) + 1, page_size=limit),
    )


@router.post("/leads", response_model=ResponseEnvelope[LeadResponse], status_code=201)
async def create_lead(
    body: LeadCreateRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[LeadResponse]:
    lead = await svc.create_lead(
        tenant_id=_tenant_id(current_user),
        source=body.source,
        first_name=body.first_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
        company=body.company,
        owner_id=body.owner_id,
        team_id=body.team_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_lead_out(lead), message="Lead created")


@router.get("/leads/{lead_id}", response_model=ResponseEnvelope[LeadResponse])
async def get_lead(
    lead_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_crm_read),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
) -> ResponseEnvelope[LeadResponse]:
    scope, team_id = scope_team
    lead = await svc.get_lead(
        lead_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
    )
    return ResponseEnvelope(data=_lead_out(lead))


@router.patch("/leads/{lead_id}", response_model=ResponseEnvelope[LeadResponse])
async def update_lead(
    lead_id: uuid.UUID,
    body: LeadUpdateRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[LeadResponse]:
    scope, team_id = scope_team
    changes = body.model_dump(exclude_unset=True)
    lead = await svc.update_lead(
        lead_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        changes=changes,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_lead_out(lead), message="Lead updated")


@router.post(
    "/leads/{lead_id}/qualify",
    response_model=ResponseEnvelope[OpportunityResponse],
    status_code=201,
)
async def qualify_lead(
    lead_id: uuid.UUID,
    body: LeadQualifyRequest | None = None,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[OpportunityResponse]:
    scope, team_id = scope_team
    amount = None
    if body is not None and body.amount is not None:
        amount = _money_from_request(body.amount, body.currency)
    opportunity = await svc.qualify_lead(
        lead_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        amount=amount,
        probability=body.probability if body is not None else None,
        expected_close_date=body.expected_close_date if body is not None else None,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_opportunity_out(opportunity), message="Lead qualified")


@router.post("/leads/{lead_id}/disqualify", response_model=ResponseEnvelope[LeadResponse])
async def disqualify_lead(
    lead_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[LeadResponse]:
    scope, team_id = scope_team
    lead = await svc.disqualify_lead(
        lead_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_lead_out(lead), message="Lead disqualified")


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


@router.get("/opportunities", response_model=ListResponse[OpportunityResponse])
async def list_opportunities(
    stage: str | None = None,
    from_close_date: str | None = None,
    to_close_date: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(_require_crm_read),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
) -> ListResponse[OpportunityResponse]:
    scope, team_id = scope_team
    opportunities = await svc.list_opportunities(
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        stage=_parse_opportunity_stage(stage),
        from_close_date=_parse_date(from_close_date),
        to_close_date=_parse_date(to_close_date),
        offset=offset,
        limit=limit,
    )
    total = await svc.count_opportunities(
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        stage=_parse_opportunity_stage(stage),
        from_close_date=_parse_date(from_close_date),
        to_close_date=_parse_date(to_close_date),
    )
    return ListResponse(
        data=[_opportunity_out(opportunity) for opportunity in opportunities],
        meta=PaginationMeta.create(total=total, page=(offset // limit) + 1, page_size=limit),
    )


@router.post(
    "/opportunities", response_model=ResponseEnvelope[OpportunityResponse], status_code=201
)
async def create_opportunity(
    body: OpportunityCreateRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[OpportunityResponse]:
    opportunity = await svc.create_opportunity(
        tenant_id=_tenant_id(current_user),
        name=body.name,
        lead_id=body.lead_id,
        amount=_money_from_request(body.amount, body.currency) if body.amount is not None else None,
        probability=body.probability,
        expected_close_date=body.expected_close_date,
        owner_id=body.owner_id,
        team_id=body.team_id,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_opportunity_out(opportunity), message="Opportunity created")


@router.get("/opportunities/{opportunity_id}", response_model=ResponseEnvelope[OpportunityResponse])
async def get_opportunity(
    opportunity_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_crm_read),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
) -> ResponseEnvelope[OpportunityResponse]:
    scope, team_id = scope_team
    opportunity = await svc.get_opportunity(
        opportunity_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
    )
    return ResponseEnvelope(data=_opportunity_out(opportunity))


@router.patch(
    "/opportunities/{opportunity_id}", response_model=ResponseEnvelope[OpportunityResponse]
)
async def update_opportunity(
    opportunity_id: uuid.UUID,
    body: OpportunityUpdateRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[OpportunityResponse]:
    scope, team_id = scope_team
    changes = body.model_dump(exclude_unset=True)
    opportunity = await svc.update_opportunity(
        opportunity_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        changes=changes,
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_opportunity_out(opportunity), message="Opportunity updated")


@router.post(
    "/opportunities/{opportunity_id}/stage",
    response_model=ResponseEnvelope[OpportunityStageResponse],
)
async def change_stage(
    opportunity_id: uuid.UUID,
    body: OpportunityStageRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    scope_team: tuple[DataScope, uuid.UUID | None] = Depends(get_current_scope),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[OpportunityStageResponse]:
    scope, team_id = scope_team
    opportunity, customer = await svc.change_stage(
        opportunity_id,
        tenant_id=_tenant_id(current_user),
        scope=scope,
        user_id=_user_id(current_user),
        team_id=team_id,
        stage=body.stage,
        lost_reason=body.lost_reason,
    )
    # The pipeline board re-reads the deal right after this 2xx, so the move
    # must be durable before the response goes out - see commit_writes.
    await commit_writes(db)
    return ResponseEnvelope(
        data=OpportunityStageResponse(
            opportunity=_opportunity_out(opportunity),
            customer=_customer_out(customer) if customer is not None else None,
        ),
        message=f"Opportunity moved to '{body.stage.value}'",
    )


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


@router.get("/customers", response_model=ListResponse[CustomerResponse])
async def list_customers(
    include_inactive: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(_require_crm_read),
    svc: CrmService = Depends(get_crm_service),
) -> ListResponse[CustomerResponse]:
    customers = await svc.list_customers(
        tenant_id=_tenant_id(current_user),
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )
    total = await svc.count_customers(
        tenant_id=_tenant_id(current_user),
        include_inactive=include_inactive,
    )
    return ListResponse(
        data=[_customer_out(customer) for customer in customers],
        meta=PaginationMeta.create(total=total, page=(offset // limit) + 1, page_size=limit),
    )


@router.post("/customers", response_model=ResponseEnvelope[CustomerResponse], status_code=201)
async def create_customer(
    body: CustomerCreateRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[CustomerResponse]:
    customer = await svc.create_customer(
        tenant_id=_tenant_id(current_user),
        name=body.name,
        email=body.email,
        phone=body.phone,
        credit_limit=(
            _money_from_request(body.credit_limit, body.currency)
            if body.credit_limit is not None
            else None
        ),
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_customer_out(customer), message="Customer created")


@router.get("/customers/{customer_id}", response_model=ResponseEnvelope[CustomerResponse])
async def get_customer(
    customer_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_crm_read),
    svc: CrmService = Depends(get_crm_service),
) -> ResponseEnvelope[CustomerResponse]:
    customer = await svc.get_customer(customer_id, tenant_id=_tenant_id(current_user))
    return ResponseEnvelope(data=_customer_out(customer))


@router.patch("/customers/{customer_id}", response_model=ResponseEnvelope[CustomerResponse])
async def update_customer(
    customer_id: uuid.UUID,
    body: CustomerUpdateRequest,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[CustomerResponse]:
    changes = body.model_dump(exclude_unset=True)
    customer = await svc.update_customer(
        customer_id, tenant_id=_tenant_id(current_user), changes=changes
    )
    await commit_writes(db)
    return ResponseEnvelope(data=_customer_out(customer), message="Customer updated")


@router.delete("/customers/{customer_id}", response_model=ResponseEnvelope[CustomerResponse])
async def deactivate_customer(
    customer_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(_require_crm_write),
    svc: CrmService = Depends(get_crm_service),
    db: AsyncSession = Depends(get_db),
) -> ResponseEnvelope[CustomerResponse]:
    customer = await svc.deactivate_customer(customer_id, tenant_id=_tenant_id(current_user))
    await commit_writes(db)
    return ResponseEnvelope(data=_customer_out(customer), message="Customer deactivated")


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_lead_status(value: str | None) -> LeadStatus | None:
    if value is None:
        return None
    return LeadStatus(value)


def _parse_opportunity_stage(value: str | None) -> OpportunityStage | None:
    if value is None:
        return None
    return OpportunityStage(value)


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _money_from_request(amount: Decimal, currency: str) -> Money:
    """Build a :class:`Money` - currency validation happens in the constructor."""
    return Money(amount=amount, currency=currency)
