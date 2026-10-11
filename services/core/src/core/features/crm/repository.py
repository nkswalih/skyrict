"""CRM repository - DB operations for leads, opportunities, and customers.

Concrete implementation of :class:`CrmRepositoryPort`. Every read is
tenant-scoped (``WHERE tenant_id = :tenant_id`` - defense in depth under RLS)
AND owner/team-scoped for leads and opportunities: the caller passes a
:class:`DataScope` (resolved once per request by ``core.db.rbac``) plus their
``user_id`` / ``team_id``, and :func:`_scope_filter` turns that into a SQL
predicate. The repository never sees a role name, so a role change cannot
silently broaden a query.

Scope semantics (fail closed - missing ids narrow, never broaden):

- ``OWNER``: rows where ``owner_id = user_id``; no user -> no rows.
- ``TEAM``: rows where ``owner_id = user_id`` OR ``team_id = team_id``;
  neither id -> no rows.
- ``ALL``: tenant filter only (RLS still bounds the tenant).

Unassigned rows (owner_id AND team_id NULL) are visible only to ``ALL``
scope - a deliberate strict default; the service layer can opt into broader
visibility explicitly.

Customers have no owner/team columns (locked SKY-43 decision), so they are
tenant-scoped only; ``is_active`` is their soft-delete flag.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, Select, String, cast, false, func, literal, or_, select
from sqlalchemy.orm import Mapped

from core.db.parallel import parallel_reads
from core.domain.entities import (
    Activity,
    Contact,
    CrmSearchHit,
    Customer,
    Lead,
    Note,
    Opportunity,
    TimelineEvent,
    TimelineItem,
)
from core.domain.value_objects import (
    ActivityKind,
    CrmEntityType,
    CrmTimelineEventType,
    DataScope,
    LeadStatus,
    Money,
    OpportunityStage,
)
from core.features.crm.models.activity import ErpCrmActivityModel
from core.features.crm.models.contact import ErpCrmContactModel
from core.features.crm.models.customer import ErpCrmCustomerModel
from core.features.crm.models.lead import ErpCrmLeadModel
from core.features.crm.models.note import ErpCrmNoteModel
from core.features.crm.models.opportunity import ErpCrmOpportunityModel
from core.features.crm.models.timeline_event import ErpCrmTimelineEventModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Per-tenant document sequences this repository can claim. The callable is
# injected at the composition root (``core.db.sequence_repository`` - features
# never import core.db), mirroring the HR repository's ``next_sequence``.
_CUSTOMER_CODE_SEQUENCE = "customer_code"

# Editable (PATCH) fields per entity. Unknown keys are programming errors and
# raise loudly - the service only ever forwards validated schema fields.
_LEAD_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {"source", "first_name", "last_name", "email", "phone", "company", "owner_id", "team_id"}
)
_OPPORTUNITY_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {"name", "amount", "probability", "expected_close_date", "owner_id", "team_id"}
)
_CUSTOMER_EDITABLE_FIELDS: frozenset[str] = frozenset({"name", "email", "phone", "credit_limit"})
_CONTACT_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {"first_name", "last_name", "email", "phone", "job_title", "is_primary"}
)
_ACTIVITY_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "kind",
        "subject",
        "description",
        "due_at",
        "notes",
        "transcript_text",
        "owner_id",
        "team_id",
    }
)
_NOTE_EDITABLE_FIELDS: frozenset[str] = frozenset({"body"})


def _assert_known_fields(changes: dict[str, object], known: frozenset[str]) -> None:
    """Reject unknown update keys - a service bug must not silently no-op."""
    unknown = set(changes) - known
    if unknown:
        raise ValueError(f"Unknown editable fields: {sorted(unknown)}")


def _scope_filter(
    *,
    scope: DataScope,
    owner: Mapped[uuid.UUID | None],
    team: Mapped[uuid.UUID | None],
    user_id: uuid.UUID | None,
    team_id: uuid.UUID | None,
) -> ColumnElement[bool] | None:
    """SQL predicate enforcing owner/team/all scoping on a lead/opportunity.

    Returns ``None`` for ALL scope (tenant filter only - RLS bounds the
    tenant). Fails closed: a missing user/team id narrows the result, never
    broadens it.
    """
    if scope is DataScope.OWNER:
        if user_id is None:
            return false()
        return owner == user_id
    if scope is DataScope.TEAM:
        predicates: list[ColumnElement[bool]] = []
        if user_id is not None:
            predicates.append(owner == user_id)
        if team_id is not None:
            predicates.append(team == team_id)
        if not predicates:
            return false()
        return or_(*predicates)
    return None


def _lead_to_orm(lead: Lead) -> ErpCrmLeadModel:
    kwargs: dict[str, object] = {
        "tenant_id": lead.tenant_id,
        "status": lead.status,
        "source": lead.source,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "email": lead.email,
        "phone": lead.phone,
        "company": lead.company,
        "owner_id": lead.owner_id,
        "team_id": lead.team_id,
    }
    if lead.id is not None:
        kwargs["id"] = lead.id
    return ErpCrmLeadModel(**kwargs)


def _lead_from_orm(model: ErpCrmLeadModel) -> Lead:
    return Lead(
        id=model.id,
        tenant_id=model.tenant_id,
        status=model.status,
        source=model.source,
        first_name=model.first_name,
        last_name=model.last_name,
        email=model.email,
        phone=model.phone,
        company=model.company,
        owner_id=model.owner_id,
        team_id=model.team_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _opportunity_to_orm(opportunity: Opportunity) -> ErpCrmOpportunityModel:
    kwargs: dict[str, object] = {
        "tenant_id": opportunity.tenant_id,
        "name": opportunity.name,
        "stage": opportunity.stage,
        "probability": opportunity.probability,
        "expected_close_date": opportunity.expected_close_date,
        "owner_id": opportunity.owner_id,
        "team_id": opportunity.team_id,
        "won_at": opportunity.won_at,
        "lost_at": opportunity.lost_at,
        "lost_reason": opportunity.lost_reason,
    }
    if opportunity.lead_id is not None:
        kwargs["lead_id"] = opportunity.lead_id
    if opportunity.amount is not None:
        kwargs["amount"] = opportunity.amount.amount
        kwargs["currency_code"] = opportunity.amount.currency
    if opportunity.id is not None:
        kwargs["id"] = opportunity.id
    return ErpCrmOpportunityModel(**kwargs)


def _opportunity_from_orm(model: ErpCrmOpportunityModel) -> Opportunity:
    if model.amount is not None:
        # DB CHECK ck_erp_crm_opportunities_currency_present guarantees the
        # currency travels with a non-null amount.
        assert model.currency_code is not None
        amount: Money | None = Money(model.amount, model.currency_code)
    else:
        amount = None
    return Opportunity(
        id=model.id,
        tenant_id=model.tenant_id,
        name=model.name,
        lead_id=model.lead_id,
        stage=model.stage,
        amount=amount,
        probability=model.probability,
        expected_close_date=model.expected_close_date,
        owner_id=model.owner_id,
        team_id=model.team_id,
        won_at=model.won_at,
        lost_at=model.lost_at,
        lost_reason=model.lost_reason,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _customer_to_orm(customer: Customer) -> ErpCrmCustomerModel:
    kwargs: dict[str, object] = {
        "tenant_id": customer.tenant_id,
        "customer_code": customer.customer_code,
        "name": customer.name,
        "email": customer.email,
        "phone": customer.phone,
        "is_active": customer.is_active,
    }
    if customer.source_opportunity_id is not None:
        kwargs["source_opportunity_id"] = customer.source_opportunity_id
    if customer.credit_limit is not None:
        kwargs["credit_limit"] = customer.credit_limit.amount
        kwargs["currency_code"] = customer.credit_limit.currency
    if customer.id is not None:
        kwargs["id"] = customer.id
    return ErpCrmCustomerModel(**kwargs)


def _customer_from_orm(model: ErpCrmCustomerModel) -> Customer:
    if model.credit_limit is not None:
        # DB CHECK ck_erp_crm_customers_currency_present guarantees the
        # currency travels with a non-null limit.
        assert model.currency_code is not None
        credit_limit: Money | None = Money(model.credit_limit, model.currency_code)
    else:
        credit_limit = None
    return Customer(
        id=model.id,
        tenant_id=model.tenant_id,
        customer_code=model.customer_code,
        name=model.name,
        source_opportunity_id=model.source_opportunity_id,
        email=model.email,
        phone=model.phone,
        credit_limit=credit_limit,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class CrmRepository:
    """Concrete SQLAlchemy implementation of :class:`CrmRepositoryPort`."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        next_sequence: Callable[[uuid.UUID, str], Awaitable[int]] | None = None,
    ) -> None:
        self.session = session
        self._next_sequence = next_sequence

    async def commit(self) -> None:
        """Commit the current transaction (write handlers, before the response)."""
        await self.session.commit()

    async def parallel(
        self,
        tenant_id: object,
        *jobs: Callable[[CrmRepository], Awaitable[Any]],
    ) -> list[Any]:
        """Run independent read queries concurrently on forked pooled sessions.

        Each job runs against a fresh ``CrmRepository`` bound to its own
        RLS-scoped session, so the queries genuinely overlap instead of
        serializing on this repository's single connection (a single
        ``AsyncSession`` serializes ``execute()`` on its one connection).
        Results come back in ``jobs`` order. Read-only only - forks are
        discarded after the gather and never flush.
        """

        def _with_forked_session(
            job: Callable[[CrmRepository], Awaitable[Any]],
        ) -> Callable[[AsyncSession], Awaitable[Any]]:
            async def _run(session: AsyncSession) -> Any:
                return await job(CrmRepository(session))

            return _run

        return await parallel_reads(tenant_id, [_with_forked_session(job) for job in jobs])

    async def next_customer_sequence(self, tenant_id: uuid.UUID) -> int:
        """Claim the next customer-code sequence value (entity ``customer_code``).

        Race-safe and never reused (row-locking counter); the service formats
        the value into ``CUST-{year}-{seq:05d}``.
        """
        if self._next_sequence is None:
            raise RuntimeError("CrmRepository was not wired with a sequence callable")
        return await self._next_sequence(tenant_id, _CUSTOMER_CODE_SEQUENCE)

    # ------------------------------------------------------------------
    # Leads
    # ------------------------------------------------------------------

    async def create_lead(self, lead: Lead) -> Lead:
        model = _lead_to_orm(lead)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _lead_from_orm(model)

    async def get_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Lead | None:
        stmt = select(ErpCrmLeadModel).where(
            ErpCrmLeadModel.tenant_id == tenant_id,
            ErpCrmLeadModel.id == lead_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _lead_from_orm(model) if model is not None else None

    async def list_leads(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        status: LeadStatus | None = None,
        source: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Lead]:
        stmt = select(ErpCrmLeadModel).where(ErpCrmLeadModel.tenant_id == tenant_id)
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        if status is not None:
            stmt = stmt.where(ErpCrmLeadModel.status == status)
        if source is not None:
            stmt = stmt.where(ErpCrmLeadModel.source == source)
        stmt = stmt.order_by(ErpCrmLeadModel.created_at.desc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_lead_from_orm(model) for model in result.scalars().all()]

    async def count_leads(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        status: LeadStatus | None = None,
        source: str | None = None,
    ) -> int:
        """Total rows matching :meth:`list_leads` filters (for pagination meta).

        Reuses the same scope predicate so a scoped caller's total never
        counts rows they cannot see.
        """
        stmt = (
            select(func.count())
            .select_from(ErpCrmLeadModel)
            .where(ErpCrmLeadModel.tenant_id == tenant_id)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        if status is not None:
            stmt = stmt.where(ErpCrmLeadModel.status == status)
        if source is not None:
            stmt = stmt.where(ErpCrmLeadModel.source == source)
        return int((await self.session.execute(stmt)).scalar_one())

    async def find_leads_by_email(self, email: str, *, tenant_id: uuid.UUID) -> list[Lead]:
        """Soft dedupe probe: every lead in the tenant with this email.

        Deliberately NON-unique at the DB level (locked SKY-43 decision) -
        the service layer decides how to act on duplicates. This probe is
        tenant-scoped only: it answers "has anyone in this tenant been
        approached at this address", not "can this user see them".
        """
        stmt = select(ErpCrmLeadModel).where(
            ErpCrmLeadModel.tenant_id == tenant_id,
            ErpCrmLeadModel.email == email,
        )
        result = await self.session.execute(stmt)
        return [_lead_from_orm(model) for model in result.scalars().all()]

    async def update_lead_status(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        status: LeadStatus,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Lead | None:
        stmt = select(ErpCrmLeadModel).where(
            ErpCrmLeadModel.tenant_id == tenant_id,
            ErpCrmLeadModel.id == lead_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.status = status
        await self.session.flush()
        await self.session.refresh(model)
        return _lead_from_orm(model)

    async def update_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Lead | None:
        """PATCH the editable lead fields (never ``status`` - use update_lead_status)."""
        _assert_known_fields(changes, _LEAD_EDITABLE_FIELDS)
        stmt = select(ErpCrmLeadModel).where(
            ErpCrmLeadModel.tenant_id == tenant_id,
            ErpCrmLeadModel.id == lead_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        for field, value in changes.items():
            setattr(model, field, value)
        await self.session.flush()
        await self.session.refresh(model)
        return _lead_from_orm(model)

    # ------------------------------------------------------------------
    # Opportunities
    # ------------------------------------------------------------------

    async def create_opportunity(self, opportunity: Opportunity) -> Opportunity:
        model = _opportunity_to_orm(opportunity)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _opportunity_from_orm(model)

    async def get_opportunity(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Opportunity | None:
        stmt = select(ErpCrmOpportunityModel).where(
            ErpCrmOpportunityModel.tenant_id == tenant_id,
            ErpCrmOpportunityModel.id == opportunity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _opportunity_from_orm(model) if model is not None else None

    async def get_opportunity_by_lead(
        self, lead_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Opportunity | None:
        """The opportunity qualified from ``lead_id`` (idempotency probe).

        Deliberately tenant-scoped only (like ``find_leads_by_email``): it
        answers "has this lead already qualified", and the caller has already
        read the lead under its scope to get here.
        """
        stmt = select(ErpCrmOpportunityModel).where(
            ErpCrmOpportunityModel.tenant_id == tenant_id,
            ErpCrmOpportunityModel.lead_id == lead_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _opportunity_from_orm(model) if model is not None else None

    async def list_opportunities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        stage: OpportunityStage | None = None,
        from_close_date: date | None = None,
        to_close_date: date | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Opportunity]:
        stmt = select(ErpCrmOpportunityModel).where(ErpCrmOpportunityModel.tenant_id == tenant_id)
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        if stage is not None:
            stmt = stmt.where(ErpCrmOpportunityModel.stage == stage)
        if from_close_date is not None:
            stmt = stmt.where(ErpCrmOpportunityModel.expected_close_date >= from_close_date)
        if to_close_date is not None:
            stmt = stmt.where(ErpCrmOpportunityModel.expected_close_date <= to_close_date)
        stmt = stmt.order_by(ErpCrmOpportunityModel.created_at.desc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_opportunity_from_orm(model) for model in result.scalars().all()]

    async def count_opportunities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        stage: OpportunityStage | None = None,
        from_close_date: date | None = None,
        to_close_date: date | None = None,
    ) -> int:
        """Total rows matching :meth:`list_opportunities` filters (pagination meta)."""
        stmt = (
            select(func.count())
            .select_from(ErpCrmOpportunityModel)
            .where(ErpCrmOpportunityModel.tenant_id == tenant_id)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        if stage is not None:
            stmt = stmt.where(ErpCrmOpportunityModel.stage == stage)
        if from_close_date is not None:
            stmt = stmt.where(ErpCrmOpportunityModel.expected_close_date >= from_close_date)
        if to_close_date is not None:
            stmt = stmt.where(ErpCrmOpportunityModel.expected_close_date <= to_close_date)
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_opportunity_stage(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        stage: OpportunityStage,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        won_at: datetime | None = None,
        lost_at: datetime | None = None,
        lost_reason: str | None = None,
    ) -> Opportunity | None:
        stmt = select(ErpCrmOpportunityModel).where(
            ErpCrmOpportunityModel.tenant_id == tenant_id,
            ErpCrmOpportunityModel.id == opportunity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.stage = stage
        model.won_at = won_at
        model.lost_at = lost_at
        model.lost_reason = lost_reason
        await self.session.flush()
        await self.session.refresh(model)
        return _opportunity_from_orm(model)

    async def update_opportunity(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Opportunity | None:
        """PATCH the editable opportunity fields (never ``stage`` - use update_opportunity_stage).

        ``amount`` may be a :class:`Money` (written with its currency tag) or
        ``None`` (clears the amount AND the currency - the DB CHECK forbids a
        bare amount).
        """
        _assert_known_fields(changes, _OPPORTUNITY_EDITABLE_FIELDS)
        stmt = select(ErpCrmOpportunityModel).where(
            ErpCrmOpportunityModel.tenant_id == tenant_id,
            ErpCrmOpportunityModel.id == opportunity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        if "amount" in changes:
            amount = changes["amount"]
            if amount is None:
                model.amount = None
                model.currency_code = None
            else:
                assert isinstance(amount, Money)
                model.amount = amount.amount
                model.currency_code = amount.currency
        for field, value in changes.items():
            if field == "amount":
                continue
            setattr(model, field, value)
        await self.session.flush()
        await self.session.refresh(model)
        return _opportunity_from_orm(model)

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    async def create_customer(self, customer: Customer) -> Customer:
        model = _customer_to_orm(customer)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _customer_from_orm(model)

    async def get_customer(
        self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer | None:
        stmt = select(ErpCrmCustomerModel).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            ErpCrmCustomerModel.id == customer_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _customer_from_orm(model) if model is not None else None

    async def get_customer_name(
        self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> str | None:
        """Return the customer's display name, or None if not found (CustomerPort)."""
        customer = await self.get_customer(customer_id, tenant_id=tenant_id)
        return customer.name if customer is not None else None

    async def get_customer_names(
        self, customer_ids: Sequence[uuid.UUID], *, tenant_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        """Batch-resolve customer names to avoid N+1 (CustomerPort)."""
        if not customer_ids:
            return {}
        stmt = select(ErpCrmCustomerModel.id, ErpCrmCustomerModel.name).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            ErpCrmCustomerModel.id.in_(customer_ids),
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_customer_by_code(self, code: str, *, tenant_id: uuid.UUID) -> Customer | None:
        stmt = select(ErpCrmCustomerModel).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            ErpCrmCustomerModel.customer_code == code,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _customer_from_orm(model) if model is not None else None

    async def get_customer_by_source_opportunity(
        self, opportunity_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer | None:
        """The customer promoted from ``opportunity_id`` (idempotency probe).

        Tenant-scoped only (like ``find_leads_by_email``): the caller has
        already read the opportunity under its scope to get here.
        """
        stmt = select(ErpCrmCustomerModel).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            ErpCrmCustomerModel.source_opportunity_id == opportunity_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _customer_from_orm(model) if model is not None else None

    async def list_customers(
        self,
        *,
        tenant_id: uuid.UUID,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Customer]:
        stmt = select(ErpCrmCustomerModel).where(ErpCrmCustomerModel.tenant_id == tenant_id)
        if not include_inactive:
            stmt = stmt.where(ErpCrmCustomerModel.is_active.is_(True))
        stmt = stmt.order_by(ErpCrmCustomerModel.name.asc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_customer_from_orm(model) for model in result.scalars().all()]

    async def count_customers(
        self,
        *,
        tenant_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> int:
        """Total rows matching :meth:`list_customers` filters (pagination meta)."""
        stmt = (
            select(func.count())
            .select_from(ErpCrmCustomerModel)
            .where(ErpCrmCustomerModel.tenant_id == tenant_id)
        )
        if not include_inactive:
            stmt = stmt.where(ErpCrmCustomerModel.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_customer(
        self,
        customer_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Customer | None:
        """PATCH the editable customer fields.

        Customers are tenant-scoped only (no owner/team columns). ``credit_limit``
        may be a :class:`Money` (written with its currency tag) or ``None``
        (clears the limit AND the currency - the DB CHECK forbids a bare limit).
        """
        _assert_known_fields(changes, _CUSTOMER_EDITABLE_FIELDS)
        stmt = select(ErpCrmCustomerModel).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            ErpCrmCustomerModel.id == customer_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        if "credit_limit" in changes:
            credit_limit = changes["credit_limit"]
            if credit_limit is None:
                model.credit_limit = None
                model.currency_code = None
            else:
                assert isinstance(credit_limit, Money)
                model.credit_limit = credit_limit.amount
                model.currency_code = credit_limit.currency
        for field, value in changes.items():
            if field == "credit_limit":
                continue
            setattr(model, field, value)
        await self.session.flush()
        await self.session.refresh(model)
        return _customer_from_orm(model)

    async def deactivate_customer(
        self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer | None:
        stmt = select(ErpCrmCustomerModel).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            ErpCrmCustomerModel.id == customer_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.is_active = False
        await self.session.flush()
        await self.session.refresh(model)
        return _customer_from_orm(model)

    # ------------------------------------------------------------------
    # CRM workspace - contacts
    # ------------------------------------------------------------------

    async def create_contact(self, contact: Contact) -> Contact:
        model = _contact_to_orm(contact)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _contact_from_orm(model)

    async def get_contact(self, contact_id: uuid.UUID, *, tenant_id: uuid.UUID) -> Contact | None:
        stmt = select(ErpCrmContactModel).where(
            ErpCrmContactModel.tenant_id == tenant_id,
            ErpCrmContactModel.id == contact_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _contact_from_orm(model) if model is not None else None

    async def list_contacts(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Contact]:
        stmt = select(ErpCrmContactModel).where(ErpCrmContactModel.tenant_id == tenant_id)
        if customer_id is not None:
            stmt = stmt.where(ErpCrmContactModel.customer_id == customer_id)
        if not include_inactive:
            stmt = stmt.where(ErpCrmContactModel.is_active.is_(True))
        stmt = stmt.order_by(ErpCrmContactModel.created_at.desc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_contact_from_orm(model) for model in result.scalars().all()]

    async def count_contacts(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        include_inactive: bool = False,
    ) -> int:
        """Total rows matching :meth:`list_contacts` filters (pagination meta)."""
        stmt = (
            select(func.count())
            .select_from(ErpCrmContactModel)
            .where(ErpCrmContactModel.tenant_id == tenant_id)
        )
        if customer_id is not None:
            stmt = stmt.where(ErpCrmContactModel.customer_id == customer_id)
        if not include_inactive:
            stmt = stmt.where(ErpCrmContactModel.is_active.is_(True))
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_contact(
        self,
        contact_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Contact | None:
        _assert_known_fields(changes, _CONTACT_EDITABLE_FIELDS)
        stmt = select(ErpCrmContactModel).where(
            ErpCrmContactModel.tenant_id == tenant_id,
            ErpCrmContactModel.id == contact_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        for field, value in changes.items():
            setattr(model, field, value)
        await self.session.flush()
        await self.session.refresh(model)
        return _contact_from_orm(model)

    async def deactivate_contact(
        self, contact_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Contact | None:
        stmt = select(ErpCrmContactModel).where(
            ErpCrmContactModel.tenant_id == tenant_id,
            ErpCrmContactModel.id == contact_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.is_active = False
        await self.session.flush()
        await self.session.refresh(model)
        return _contact_from_orm(model)

    # ------------------------------------------------------------------
    # CRM workspace - activities
    # ------------------------------------------------------------------

    async def create_activity(self, activity: Activity) -> Activity:
        model = _activity_to_orm(activity)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _activity_from_orm(model)

    async def get_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Activity | None:
        stmt = select(ErpCrmActivityModel).where(
            ErpCrmActivityModel.tenant_id == tenant_id,
            ErpCrmActivityModel.id == activity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _activity_from_orm(model) if model is not None else None

    async def list_activities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        entity_type: CrmEntityType | None = None,
        entity_id: uuid.UUID | None = None,
        kind: ActivityKind | None = None,
        status: str | None = None,
        assignee_id: uuid.UUID | None = None,
        day_start: datetime | None = None,
        day_end: datetime | None = None,
        completed_since: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Activity]:
        """List activities, scope-aware, with the follow-up window filters.

        ``status`` is one of ``open``/``overdue``/``today``/``upcoming``/
        ``completed`` - resolved here to SQL on ``due_at``/``completed_at``.
        ``day_start``/``day_end`` bound the ``today`` window; ``completed_since``
        bounds ``completed`` (e.g. last 30 days).
        """
        stmt = select(ErpCrmActivityModel).where(ErpCrmActivityModel.tenant_id == tenant_id)
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        if entity_type is not None:
            stmt = stmt.where(ErpCrmActivityModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ErpCrmActivityModel.entity_id == entity_id)
        if kind is not None:
            stmt = stmt.where(ErpCrmActivityModel.kind == kind)
        if assignee_id is not None:
            stmt = stmt.where(ErpCrmActivityModel.owner_id == assignee_id)
        if status is not None:
            stmt = stmt.where(_activity_status_filter(status, day_start, day_end, completed_since))
        stmt = stmt.order_by(ErpCrmActivityModel.due_at.asc().nulls_last())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_activity_from_orm(model) for model in result.scalars().all()]

    async def count_activities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        entity_type: CrmEntityType | None = None,
        entity_id: uuid.UUID | None = None,
        kind: ActivityKind | None = None,
        status: str | None = None,
        assignee_id: uuid.UUID | None = None,
        day_start: datetime | None = None,
        day_end: datetime | None = None,
        completed_since: datetime | None = None,
    ) -> int:
        """Total rows matching :meth:`list_activities` filters (pagination meta)."""
        stmt = (
            select(func.count())
            .select_from(ErpCrmActivityModel)
            .where(ErpCrmActivityModel.tenant_id == tenant_id)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        if entity_type is not None:
            stmt = stmt.where(ErpCrmActivityModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ErpCrmActivityModel.entity_id == entity_id)
        if kind is not None:
            stmt = stmt.where(ErpCrmActivityModel.kind == kind)
        if assignee_id is not None:
            stmt = stmt.where(ErpCrmActivityModel.owner_id == assignee_id)
        if status is not None:
            stmt = stmt.where(_activity_status_filter(status, day_start, day_end, completed_since))
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Activity | None:
        """PATCH the editable activity fields (never completion - use complete_activity)."""
        _assert_known_fields(changes, _ACTIVITY_EDITABLE_FIELDS)
        stmt = select(ErpCrmActivityModel).where(
            ErpCrmActivityModel.tenant_id == tenant_id,
            ErpCrmActivityModel.id == activity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        for field, value in changes.items():
            setattr(model, field, value)
        await self.session.flush()
        await self.session.refresh(model)
        return _activity_from_orm(model)

    async def complete_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        completed_by: uuid.UUID,
    ) -> Activity | None:
        """Mark an activity completed (sets ``completed_at`` + ``completed_by``)."""
        stmt = select(ErpCrmActivityModel).where(
            ErpCrmActivityModel.tenant_id == tenant_id,
            ErpCrmActivityModel.id == activity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        model.completed_at = datetime.now(UTC)
        model.completed_by = completed_by
        await self.session.flush()
        await self.session.refresh(model)
        return _activity_from_orm(model)

    async def delete_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Activity | None:
        """Hard-delete an activity row (operational record, no soft-delete)."""
        stmt = select(ErpCrmActivityModel).where(
            ErpCrmActivityModel.tenant_id == tenant_id,
            ErpCrmActivityModel.id == activity_id,
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        removed = _activity_from_orm(model)
        await self.session.delete(model)
        await self.session.flush()
        return removed

    # ------------------------------------------------------------------
    # CRM workspace - notes
    # ------------------------------------------------------------------

    async def create_note(self, note: Note) -> Note:
        model = _note_to_orm(note)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _note_from_orm(model)

    async def get_note(self, note_id: uuid.UUID, *, tenant_id: uuid.UUID) -> Note | None:
        stmt = select(ErpCrmNoteModel).where(
            ErpCrmNoteModel.tenant_id == tenant_id,
            ErpCrmNoteModel.id == note_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return _note_from_orm(model) if model is not None else None

    async def list_notes(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType | None = None,
        entity_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Note]:
        stmt = select(ErpCrmNoteModel).where(ErpCrmNoteModel.tenant_id == tenant_id)
        if entity_type is not None:
            stmt = stmt.where(ErpCrmNoteModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ErpCrmNoteModel.entity_id == entity_id)
        stmt = stmt.order_by(ErpCrmNoteModel.created_at.desc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_note_from_orm(model) for model in result.scalars().all()]

    async def count_notes(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> int:
        """Total rows matching :meth:`list_notes` filters (pagination meta)."""
        stmt = (
            select(func.count())
            .select_from(ErpCrmNoteModel)
            .where(ErpCrmNoteModel.tenant_id == tenant_id)
        )
        if entity_type is not None:
            stmt = stmt.where(ErpCrmNoteModel.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(ErpCrmNoteModel.entity_id == entity_id)
        return int((await self.session.execute(stmt)).scalar_one())

    async def update_note(
        self,
        note_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Note | None:
        _assert_known_fields(changes, _NOTE_EDITABLE_FIELDS)
        stmt = select(ErpCrmNoteModel).where(
            ErpCrmNoteModel.tenant_id == tenant_id,
            ErpCrmNoteModel.id == note_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        for field, value in changes.items():
            setattr(model, field, value)
        await self.session.flush()
        await self.session.refresh(model)
        return _note_from_orm(model)

    async def delete_note(self, note_id: uuid.UUID, *, tenant_id: uuid.UUID) -> Note | None:
        stmt = select(ErpCrmNoteModel).where(
            ErpCrmNoteModel.tenant_id == tenant_id,
            ErpCrmNoteModel.id == note_id,
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        removed = _note_from_orm(model)
        await self.session.delete(model)
        await self.session.flush()
        return removed

    # ------------------------------------------------------------------
    # CRM workspace - timeline (DB-layer UNION of the three sources)
    # ------------------------------------------------------------------

    async def get_timeline(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[TimelineItem], int]:
        """Merged relationship timeline for one entity.

        The three sources (activities, notes, timeline events) are merged with
        a SQL ``UNION ALL`` BEFORE ordering and pagination - never three
        independently paged lists combined in application code.
        """
        union = _timeline_union(tenant_id, entity_type, entity_id)
        merged = union.subquery()
        count_stmt = select(func.count()).select_from(merged)
        total = int((await self.session.execute(count_stmt)).scalar_one())
        stmt = select(merged).order_by(merged.c.occurred_at.desc(), merged.c.id.desc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_timeline_item_from_row(row) for row in result.mappings().all()], total  # type: ignore[arg-type]

    async def get_global_timeline(
        self,
        *,
        tenant_id: uuid.UUID,
        offset: int = 0,
        limit: int = 10,
    ) -> list[TimelineItem]:
        """Recent CRM activity across all entities - dashboard feed."""
        union = _global_timeline_union(tenant_id)
        merged = union.subquery()
        stmt = select(merged).order_by(merged.c.occurred_at.desc(), merged.c.id.desc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        return [_timeline_item_from_row(row) for row in result.mappings().all()]  # type: ignore[arg-type]

    async def record_timeline_event(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        event_type: CrmTimelineEventType,
        title: str,
        actor_id: uuid.UUID | None = None,
        payload: dict[str, object] | None = None,
    ) -> TimelineEvent:
        """Persist one curated timeline event in the same transaction as the action."""
        event = TimelineEvent(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            title=title,
            actor_id=actor_id,
            payload=payload,
        )
        model = _timeline_event_to_orm(event)
        self.session.add(model)
        await self.session.flush()
        await self.session.refresh(model)
        return _timeline_event_from_orm(model)

    # ------------------------------------------------------------------
    # CRM workspace - overview aggregates (real data only)
    # ------------------------------------------------------------------

    async def lead_status_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> list[tuple[LeadStatus, int]]:
        stmt = (
            select(ErpCrmLeadModel.status, func.count())
            .where(ErpCrmLeadModel.tenant_id == tenant_id)
            .group_by(ErpCrmLeadModel.status)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        return [(status, count) for status, count in (await self.session.execute(stmt)).all()]

    async def lead_source_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> list[tuple[str | None, int]]:
        stmt = (
            select(ErpCrmLeadModel.source, func.count())
            .where(ErpCrmLeadModel.tenant_id == tenant_id)
            .group_by(ErpCrmLeadModel.source)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        return [(source, count) for source, count in (await self.session.execute(stmt)).all()]

    async def opportunity_funnel(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> list[tuple[OpportunityStage, str | None, int, Decimal]]:
        """Per-stage count + per-currency value for every pipeline stage."""
        stmt = (
            select(
                ErpCrmOpportunityModel.stage,
                ErpCrmOpportunityModel.currency_code,
                func.count(),
                func.coalesce(func.sum(ErpCrmOpportunityModel.amount), 0),
            )
            .where(ErpCrmOpportunityModel.tenant_id == tenant_id)
            .group_by(ErpCrmOpportunityModel.stage, ErpCrmOpportunityModel.currency_code)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        return [
            (stage, currency, count, amount)
            for stage, currency, count, amount in (await self.session.execute(stmt)).all()
        ]

    async def won_lost_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> list[tuple[OpportunityStage, int]]:
        stmt = (
            select(ErpCrmOpportunityModel.stage, func.count())
            .where(
                ErpCrmOpportunityModel.tenant_id == tenant_id,
                ErpCrmOpportunityModel.stage.in_((OpportunityStage.WON, OpportunityStage.LOST)),
            )
            .group_by(ErpCrmOpportunityModel.stage)
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        return [(stage, count) for stage, count in (await self.session.execute(stmt)).all()]

    async def customer_counts(self, *, tenant_id: uuid.UUID) -> tuple[int, int]:
        total = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(ErpCrmCustomerModel)
                    .where(ErpCrmCustomerModel.tenant_id == tenant_id)
                )
            ).scalar_one()
        )
        active = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(ErpCrmCustomerModel)
                    .where(
                        ErpCrmCustomerModel.tenant_id == tenant_id,
                        ErpCrmCustomerModel.is_active.is_(True),
                    )
                )
            ).scalar_one()
        )
        return total, active

    async def activity_window_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        today_start: datetime,
        today_end: datetime,
        completed_since: datetime,
    ) -> dict[str, int]:
        """Follow-up window counts: today / overdue / upcoming / completed_30d."""
        base = (
            select(func.count())
            .select_from(ErpCrmActivityModel)
            .where(
                ErpCrmActivityModel.tenant_id == tenant_id,
                ErpCrmActivityModel.completed_at.is_(None),
            )
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmActivityModel.owner_id,
            team=ErpCrmActivityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            base = base.where(scoped)

        today, overdue, upcoming, completed_30d = await self.parallel(
            tenant_id,
            lambda repo: repo._scoped_count(base.where(ErpCrmActivityModel.due_at >= today_start)),
            lambda repo: repo._scoped_count(base.where(ErpCrmActivityModel.due_at < today_start)),
            lambda repo: repo._scoped_count(base.where(ErpCrmActivityModel.due_at >= today_end)),
            lambda repo: repo._count_completed_activities(
                tenant_id=tenant_id, completed_since=completed_since
            ),
        )
        return {
            "today": today,
            "overdue": overdue,
            "upcoming": upcoming,
            "completed_30d": completed_30d,
        }

    async def _scoped_count(self, stmt: Select[Any]) -> int:
        return int((await self.session.execute(stmt)).scalar_one())

    async def _count_completed_activities(
        self, *, tenant_id: uuid.UUID, completed_since: datetime
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(ErpCrmActivityModel)
            .where(
                ErpCrmActivityModel.tenant_id == tenant_id,
                ErpCrmActivityModel.completed_at.is_not(None),
                ErpCrmActivityModel.completed_at >= completed_since,
            )
        )
        return int((await self.session.execute(stmt)).scalar_one())

    async def recent_won_opportunities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        limit: int = 5,
    ) -> list[Opportunity]:
        stmt = (
            select(ErpCrmOpportunityModel)
            .where(
                ErpCrmOpportunityModel.tenant_id == tenant_id,
                ErpCrmOpportunityModel.stage == OpportunityStage.WON,
            )
            .order_by(ErpCrmOpportunityModel.won_at.desc().nulls_last())
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt.limit(limit))
        return [_opportunity_from_orm(model) for model in result.scalars().all()]

    async def top_opportunities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        limit: int = 5,
    ) -> list[Opportunity]:
        """Open (non-terminal) opportunities by value, highest first."""
        stmt = (
            select(ErpCrmOpportunityModel)
            .where(
                ErpCrmOpportunityModel.tenant_id == tenant_id,
                ErpCrmOpportunityModel.stage.not_in((OpportunityStage.WON, OpportunityStage.LOST)),
                ErpCrmOpportunityModel.amount.is_not(None),
            )
            .order_by(ErpCrmOpportunityModel.amount.desc().nulls_last())
        )
        scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if scoped is not None:
            stmt = stmt.where(scoped)
        result = await self.session.execute(stmt.limit(limit))
        return [_opportunity_from_orm(model) for model in result.scalars().all()]

    # ------------------------------------------------------------------
    # CRM workspace - server-side search
    # ------------------------------------------------------------------

    async def search(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        query: str,
        entity_type: CrmEntityType | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[CrmSearchHit], int]:
        """Search leads, opportunities, customers, and contacts server-side."""
        like = f"%{query}%"

        lead_stmt = select(
            literal("lead").label("entity_type"),
            ErpCrmLeadModel.id.label("entity_id"),
            func.coalesce(
                func.nullif(ErpCrmLeadModel.company, ""),
                func.concat_ws(" ", ErpCrmLeadModel.first_name, ErpCrmLeadModel.last_name),
                ErpCrmLeadModel.email,
            ).label("title"),
            ErpCrmLeadModel.email.label("subtitle"),
        ).where(
            ErpCrmLeadModel.tenant_id == tenant_id,
            _lead_search_predicate(ErpCrmLeadModel, like),
        )
        lead_scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmLeadModel.owner_id,
            team=ErpCrmLeadModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if lead_scoped is not None:
            lead_stmt = lead_stmt.where(lead_scoped)

        opp_stmt = select(
            literal("opportunity").label("entity_type"),
            ErpCrmOpportunityModel.id.label("entity_id"),
            ErpCrmOpportunityModel.name.label("title"),
            cast(func.coalesce(ErpCrmOpportunityModel.amount, 0), String).label("subtitle"),
        ).where(
            ErpCrmOpportunityModel.tenant_id == tenant_id,
            ErpCrmOpportunityModel.name.ilike(like),
        )
        opp_scoped = _scope_filter(
            scope=scope,
            owner=ErpCrmOpportunityModel.owner_id,
            team=ErpCrmOpportunityModel.team_id,
            user_id=user_id,
            team_id=team_id,
        )
        if opp_scoped is not None:
            opp_stmt = opp_stmt.where(opp_scoped)

        customer_stmt = select(
            literal("customer").label("entity_type"),
            ErpCrmCustomerModel.id.label("entity_id"),
            ErpCrmCustomerModel.name.label("title"),
            func.coalesce(ErpCrmCustomerModel.customer_code, "").label("subtitle"),
        ).where(
            ErpCrmCustomerModel.tenant_id == tenant_id,
            _customer_search_predicate(ErpCrmCustomerModel, like),
        )

        contact_stmt = select(
            literal("contact").label("entity_type"),
            ErpCrmContactModel.id.label("entity_id"),
            func.concat_ws(" ", ErpCrmContactModel.first_name, ErpCrmContactModel.last_name).label(
                "title"
            ),
            func.coalesce(ErpCrmContactModel.email, "").label("subtitle"),
        ).where(
            ErpCrmContactModel.tenant_id == tenant_id,
            _contact_search_predicate(ErpCrmContactModel, like),
        )

        selects: list[tuple[CrmEntityType, Any]] = [
            (CrmEntityType.LEAD, lead_stmt),
            (CrmEntityType.OPPORTUNITY, opp_stmt),
            (CrmEntityType.CUSTOMER, customer_stmt),
            (CrmEntityType.CONTACT, contact_stmt),
        ]
        if entity_type is not None:
            selects = [(kind, stmt) for kind, stmt in selects if kind == entity_type]

        union: Any = selects[0][1].union_all(*(stmt for _, stmt in selects[1:]))

        count_stmt = select(func.count()).select_from(union.subquery())
        total = int((await self.session.execute(count_stmt)).scalar_one())
        merged = union.subquery()
        stmt = select(merged).order_by(merged.c.title.asc())
        result = await self.session.execute(stmt.offset(offset).limit(limit))
        hits = [
            CrmSearchHit(
                tenant_id=tenant_id,
                entity_type=CrmEntityType(row["entity_type"]),
                entity_id=row["entity_id"],
                title=row["title"] or "",
                subtitle=str(row["subtitle"]) if row["subtitle"] else None,
            )
            for row in result.mappings().all()
        ]
        return hits, total


# ---------------------------------------------------------------------------
# CRM workspace - ORM <-> domain mappers
# ---------------------------------------------------------------------------


def _contact_to_orm(contact: Contact) -> ErpCrmContactModel:
    kwargs: dict[str, object] = {
        "tenant_id": contact.tenant_id,
        "customer_id": contact.customer_id,
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "email": contact.email,
        "phone": contact.phone,
        "job_title": contact.job_title,
        "is_primary": contact.is_primary,
        "is_active": contact.is_active,
    }
    if contact.id is not None:
        kwargs["id"] = contact.id
    return ErpCrmContactModel(**kwargs)


def _contact_from_orm(model: ErpCrmContactModel) -> Contact:
    return Contact(
        id=model.id,
        tenant_id=model.tenant_id,
        customer_id=model.customer_id,
        first_name=model.first_name,
        last_name=model.last_name,
        email=model.email,
        phone=model.phone,
        job_title=model.job_title,
        is_primary=model.is_primary,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _activity_to_orm(activity: Activity) -> ErpCrmActivityModel:
    kwargs: dict[str, object] = {
        "tenant_id": activity.tenant_id,
        "kind": activity.kind,
        "entity_type": activity.entity_type,
        "entity_id": activity.entity_id,
        "subject": activity.subject,
        "description": activity.description,
        "due_at": activity.due_at,
        "completed_at": activity.completed_at,
        "completed_by": activity.completed_by,
        "notes": activity.notes,
        "owner_id": activity.owner_id,
        "team_id": activity.team_id,
        "transcript_text": activity.transcript_text,
    }
    if activity.id is not None:
        kwargs["id"] = activity.id
    return ErpCrmActivityModel(**kwargs)


def _activity_from_orm(model: ErpCrmActivityModel) -> Activity:
    return Activity(
        id=model.id,
        tenant_id=model.tenant_id,
        kind=model.kind,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        subject=model.subject,
        description=model.description,
        due_at=model.due_at,
        completed_at=model.completed_at,
        completed_by=model.completed_by,
        notes=model.notes,
        owner_id=model.owner_id,
        team_id=model.team_id,
        transcript_text=model.transcript_text,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _note_to_orm(note: Note) -> ErpCrmNoteModel:
    kwargs: dict[str, object] = {
        "tenant_id": note.tenant_id,
        "entity_type": note.entity_type,
        "entity_id": note.entity_id,
        "body": note.body,
        "author_id": note.author_id,
    }
    if note.id is not None:
        kwargs["id"] = note.id
    return ErpCrmNoteModel(**kwargs)


def _note_from_orm(model: ErpCrmNoteModel) -> Note:
    return Note(
        id=model.id,
        tenant_id=model.tenant_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        body=model.body,
        author_id=model.author_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _timeline_event_to_orm(event: TimelineEvent) -> ErpCrmTimelineEventModel:
    kwargs: dict[str, object] = {
        "tenant_id": event.tenant_id,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "title": event.title,
        "actor_id": event.actor_id,
    }
    if event.payload is not None:
        kwargs["payload"] = event.payload
    if event.id is not None:
        kwargs["id"] = event.id
    return ErpCrmTimelineEventModel(**kwargs)


def _timeline_event_from_orm(model: ErpCrmTimelineEventModel) -> TimelineEvent:
    return TimelineEvent(
        id=model.id,
        tenant_id=model.tenant_id,
        entity_type=model.entity_type,
        entity_id=model.entity_id,
        event_type=model.event_type,
        title=model.title,
        actor_id=model.actor_id,
        payload=model.payload,
        created_at=model.created_at,
    )


def _timeline_item_from_row(row: Mapping[str, Any]) -> TimelineItem:
    return TimelineItem(
        source=str(row["source"]),
        id=uuid.UUID(str(row["id"])),
        tenant_id=uuid.UUID(str(row["tenant_id"])),
        entity_type=CrmEntityType(str(row["entity_type"])),
        entity_id=uuid.UUID(str(row["entity_id"])),
        kind=str(row["kind"]) if row["kind"] is not None else None,
        title=str(row["title"]) if row["title"] is not None else None,
        body=str(row["body"]) if row["body"] is not None else None,
        actor_id=uuid.UUID(str(row["actor_id"])) if row["actor_id"] is not None else None,
        occurred_at=row["occurred_at"],
    )


# ---------------------------------------------------------------------------
# CRM workspace - timeline UNION + status/search predicates
# ---------------------------------------------------------------------------


def _timeline_union(
    tenant_id: uuid.UUID,
    entity_type: CrmEntityType,
    entity_id: uuid.UUID,
) -> Any:
    """One SQL ``UNION ALL`` over activities, notes, and timeline events.

    Every branch emits the same nine columns, so the merged result can be
    ordered and paged as a single set at the database layer.
    """
    activities = select(
        literal("activity").label("source"),
        ErpCrmActivityModel.id.label("id"),
        ErpCrmActivityModel.tenant_id.label("tenant_id"),
        cast(ErpCrmActivityModel.entity_type, String).label("entity_type"),
        ErpCrmActivityModel.entity_id.label("entity_id"),
        cast(ErpCrmActivityModel.kind, String).label("kind"),
        ErpCrmActivityModel.subject.label("title"),
        func.coalesce(ErpCrmActivityModel.notes, ErpCrmActivityModel.description).label("body"),
        ErpCrmActivityModel.completed_by.label("actor_id"),
        ErpCrmActivityModel.created_at.label("occurred_at"),
    ).where(
        ErpCrmActivityModel.tenant_id == tenant_id,
        ErpCrmActivityModel.entity_type == entity_type,
        ErpCrmActivityModel.entity_id == entity_id,
    )
    notes = select(
        literal("note").label("source"),
        ErpCrmNoteModel.id.label("id"),
        ErpCrmNoteModel.tenant_id.label("tenant_id"),
        cast(ErpCrmNoteModel.entity_type, String).label("entity_type"),
        ErpCrmNoteModel.entity_id.label("entity_id"),
        cast(None, String).label("kind"),
        cast(None, String).label("title"),
        ErpCrmNoteModel.body.label("body"),
        ErpCrmNoteModel.author_id.label("actor_id"),
        ErpCrmNoteModel.created_at.label("occurred_at"),
    ).where(
        ErpCrmNoteModel.tenant_id == tenant_id,
        ErpCrmNoteModel.entity_type == entity_type,
        ErpCrmNoteModel.entity_id == entity_id,
    )
    events = select(
        literal("event").label("source"),
        ErpCrmTimelineEventModel.id.label("id"),
        ErpCrmTimelineEventModel.tenant_id.label("tenant_id"),
        cast(ErpCrmTimelineEventModel.entity_type, String).label("entity_type"),
        ErpCrmTimelineEventModel.entity_id.label("entity_id"),
        cast(ErpCrmTimelineEventModel.event_type, String).label("kind"),
        ErpCrmTimelineEventModel.title.label("title"),
        cast(None, String).label("body"),
        ErpCrmTimelineEventModel.actor_id.label("actor_id"),
        ErpCrmTimelineEventModel.created_at.label("occurred_at"),
    ).where(
        ErpCrmTimelineEventModel.tenant_id == tenant_id,
        ErpCrmTimelineEventModel.entity_type == entity_type,
        ErpCrmTimelineEventModel.entity_id == entity_id,
    )
    return activities.union_all(notes, events)


def _global_timeline_union(
    tenant_id: uuid.UUID,
) -> Any:
    """UNION ALL over all CRM activity sources for the dashboard feed.

    Unlike :func:`_timeline_union`, this has no entity filters - it returns
    recent activity across the entire tenant, ordered by ``occurred_at DESC``.
    """
    activities = select(
        literal("activity").label("source"),
        ErpCrmActivityModel.id.label("id"),
        ErpCrmActivityModel.tenant_id.label("tenant_id"),
        cast(ErpCrmActivityModel.entity_type, String).label("entity_type"),
        ErpCrmActivityModel.entity_id.label("entity_id"),
        cast(ErpCrmActivityModel.kind, String).label("kind"),
        ErpCrmActivityModel.subject.label("title"),
        func.coalesce(ErpCrmActivityModel.notes, ErpCrmActivityModel.description).label("body"),
        ErpCrmActivityModel.completed_by.label("actor_id"),
        ErpCrmActivityModel.created_at.label("occurred_at"),
    ).where(ErpCrmActivityModel.tenant_id == tenant_id)
    notes = select(
        literal("note").label("source"),
        ErpCrmNoteModel.id.label("id"),
        ErpCrmNoteModel.tenant_id.label("tenant_id"),
        cast(ErpCrmNoteModel.entity_type, String).label("entity_type"),
        ErpCrmNoteModel.entity_id.label("entity_id"),
        cast(None, String).label("kind"),
        cast(None, String).label("title"),
        ErpCrmNoteModel.body.label("body"),
        ErpCrmNoteModel.author_id.label("actor_id"),
        ErpCrmNoteModel.created_at.label("occurred_at"),
    ).where(ErpCrmNoteModel.tenant_id == tenant_id)
    events = select(
        literal("event").label("source"),
        ErpCrmTimelineEventModel.id.label("id"),
        ErpCrmTimelineEventModel.tenant_id.label("tenant_id"),
        cast(ErpCrmTimelineEventModel.entity_type, String).label("entity_type"),
        ErpCrmTimelineEventModel.entity_id.label("entity_id"),
        cast(ErpCrmTimelineEventModel.event_type, String).label("kind"),
        ErpCrmTimelineEventModel.title.label("title"),
        cast(None, String).label("body"),
        ErpCrmTimelineEventModel.actor_id.label("actor_id"),
        ErpCrmTimelineEventModel.created_at.label("occurred_at"),
    ).where(ErpCrmTimelineEventModel.tenant_id == tenant_id)
    return activities.union_all(notes, events)


def _activity_status_filter(
    status: str,
    day_start: datetime | None,
    day_end: datetime | None,
    completed_since: datetime | None,
) -> ColumnElement[bool]:
    """Translate a follow-up window label into a SQL predicate on the activity."""
    if status == "completed":
        if completed_since is not None:
            return ErpCrmActivityModel.completed_at >= completed_since
        return ErpCrmActivityModel.completed_at.is_not(None)
    open_rows = ErpCrmActivityModel.completed_at.is_(None)
    if status == "overdue" and day_start is not None:
        return open_rows & (ErpCrmActivityModel.due_at < day_start)
    if status == "today" and day_start is not None and day_end is not None:
        return (
            open_rows
            & (ErpCrmActivityModel.due_at >= day_start)
            & (ErpCrmActivityModel.due_at < day_end)
        )
    if status == "upcoming" and day_end is not None:
        return open_rows & (ErpCrmActivityModel.due_at >= day_end)
    return open_rows


def _lead_search_predicate(model: type[ErpCrmLeadModel], like: str) -> ColumnElement[bool]:
    return or_(
        model.first_name.ilike(like),
        model.last_name.ilike(like),
        model.email.ilike(like),
        model.company.ilike(like),
        model.phone.ilike(like),
    )


def _customer_search_predicate(model: type[ErpCrmCustomerModel], like: str) -> ColumnElement[bool]:
    return or_(
        model.name.ilike(like),
        model.email.ilike(like),
        model.phone.ilike(like),
        model.customer_code.ilike(like),
    )


def _contact_search_predicate(model: type[ErpCrmContactModel], like: str) -> ColumnElement[bool]:
    return or_(
        model.first_name.ilike(like),
        model.last_name.ilike(like),
        model.email.ilike(like),
        model.phone.ilike(like),
        model.job_title.ilike(like),
    )
