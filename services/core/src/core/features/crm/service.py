"""CRM service - leads, opportunities, customers (CRM-BE-002 / sales-crm.md).

The service owns the business rules; the repository only persists. Rules
implemented here (docs/modules/sales-crm.md §2, §4):

- **Lead state machine**: ``new|contacted -> qualified | disqualified``.
  ``qualified`` is terminal for the lead - it promotes to an opportunity
  (qualify is the money moment, not a lead status); ``disqualified`` is the
  dead end.
- **Opportunity pipeline**: ``prospecting -> qualified -> proposal ->
  negotiation`` then ``won | lost``. Only forward, one stage per call; the
  terminal stages are immutable. ``won`` promotes the opportunity to a
  customer (code ``CUST-{year}-{seq:05d}``).
- **Idempotency (spec §10.2)**: qualify/promote probe first
  (``get_opportunity_by_lead`` / ``get_customer_by_source_opportunity``) and
  short-circuit a replay; the DB UNIQUE anchors
  (``uq_erp_crm_opportunities_tenant_lead`` etc.) are the backstop that turns
  a lost race into a successful replay instead of a duplicate row.
- **Soft dedupe**: a new lead whose email matches an existing NON-disqualified
  lead in the tenant is refused (the DB has no unique email constraint - the
  service decides).
- **Ownership**: leads/opportunities are owner/team-scoped. The service only
  ever passes the request-resolved ``DataScope`` + the caller's ids through to
  the repository; it can never broaden visibility.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from core.audit_events import (
    CRM_CUSTOMER_CREATED,
    CRM_CUSTOMER_DEACTIVATED,
    CRM_CUSTOMER_UPDATED,
    CRM_LEAD_CREATED,
    CRM_LEAD_STATUS_CHANGED,
    CRM_LEAD_UPDATED,
    CRM_OPPORTUNITY_CREATED,
    CRM_OPPORTUNITY_LOST,
    CRM_OPPORTUNITY_STAGE_CHANGED,
    CRM_OPPORTUNITY_UPDATED,
    CRM_OPPORTUNITY_WON,
)
from core.core.exceptions import IllegalStateTransitionError
from core.core.tenant_context import TenantContext
from core.domain.entities import Customer, Lead, Opportunity
from core.domain.value_objects import (
    CrmEntityType,
    CrmTimelineEventType,
    DataScope,
    LeadStatus,
    Money,
    OpportunityStage,
)
from core.events.producers.crm_events import (
    emit_customer_created,
    emit_lead_created,
    emit_lead_status_changed,
    emit_opportunity_lost,
    emit_opportunity_stage_changed,
    emit_opportunity_won,
)
from skyrict_common.exceptions import NotFoundError, ValidationError

if TYPE_CHECKING:
    from core.features.audit.service import AuditService
    from core.features.crm.ports import CrmRepositoryPort, CrmTimelinePort

_CUST_CODE_PREFIX = "CUST"


def _promote_from_lead(lead: Lead) -> str:
    """A sensible default opportunity name for a qualified lead."""
    if lead.company:
        return lead.company
    if lead.first_name or lead.last_name:
        return " ".join(part for part in (lead.first_name, lead.last_name) if part)
    return "Qualified lead"


class CrmService:
    """Implements the CRM business rules over :class:`CrmRepositoryPort`."""

    def __init__(
        self,
        repository: CrmRepositoryPort,
        audit: AuditService,
        timeline: CrmTimelinePort,
    ) -> None:
        self._repo = repository
        self._audit_service = audit
        self._timeline = timeline

    # ------------------------------------------------------------------
    # Leads
    # ------------------------------------------------------------------

    async def create_lead(
        self,
        *,
        tenant_id: uuid.UUID,
        source: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        company: str | None = None,
        owner_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
    ) -> Lead:
        """Create a NEW lead - refuses an active duplicate by email (soft dedupe)."""
        if not any((email, phone, company, first_name, last_name)):
            raise ValidationError(
                "A lead needs at least one contact channel (email, phone, company, or name)"
            )
        if email:
            existing = await self._repo.find_leads_by_email(email, tenant_id=tenant_id)
            if any(lead.status != LeadStatus.DISQUALIFIED for lead in existing):
                raise ValidationError(f"A lead with email '{email}' already exists")

        lead = Lead(
            tenant_id=tenant_id,
            status=LeadStatus.NEW,
            source=source,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=phone,
            company=company,
            owner_id=owner_id,
            team_id=team_id,
        )
        created = await self._repo.create_lead(lead)
        assert created.id is not None
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_LEAD_CREATED,
            target=f"lead:{created.id}",
            details={"source": source, "email": email},
        )
        await emit_lead_created(lead_id=created.id, tenant_id=tenant_id, source=source, email=email)
        await self._record_timeline(
            tenant_id=tenant_id,
            entity_type=CrmEntityType.LEAD,
            entity_id=created.id,
            event_type=CrmTimelineEventType.LEAD_CREATED,
            title="Lead created",
            payload={"source": source, "email": email},
        )
        await self._repo.commit()
        return created

    async def get_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Lead:
        lead = await self._repo.get_lead(
            lead_id, tenant_id=tenant_id, scope=scope, user_id=user_id, team_id=team_id
        )
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        return lead

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
        return list(
            await self._repo.list_leads(
                tenant_id=tenant_id,
                scope=scope,
                user_id=user_id,
                team_id=team_id,
                status=status,
                source=source,
                offset=offset,
                limit=limit,
            )
        )

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
        """Total rows matching :meth:`list_leads` filters (pagination meta)."""
        return await self._repo.count_leads(
            tenant_id=tenant_id,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
            status=status,
            source=source,
        )

    async def update_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Lead:
        """PATCH editable lead fields (never ``status`` - use qualify/disqualify)."""
        if not changes:
            return await self.get_lead(
                lead_id, tenant_id=tenant_id, scope=scope, user_id=user_id, team_id=team_id
            )
        if changes.get("email"):
            existing = await self._repo.find_leads_by_email(
                str(changes["email"]), tenant_id=tenant_id
            )
            if any(
                lead.id != lead_id and lead.status != LeadStatus.DISQUALIFIED for lead in existing
            ):
                raise ValidationError(f"A lead with email '{changes['email']}' already exists")

        updated = await self._repo.update_lead(
            lead_id,
            tenant_id=tenant_id,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
            changes=changes,
        )
        if updated is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_LEAD_UPDATED,
            target=f"lead:{lead_id}",
            details=changes,
        )
        await self._repo.commit()
        return updated

    async def qualify_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        amount: Money | None = None,
        probability: int | None = None,
        expected_close_date: date | None = None,
    ) -> Opportunity:
        """``new|contacted -> qualified`` and promote to a NEW opportunity.

        Idempotent: a replay returns the opportunity created on first qualify.
        """
        if probability is not None and not 0 <= probability <= 100:
            raise ValidationError("Probability must be between 0 and 100")

        existing = await self._repo.get_opportunity_by_lead(lead_id, tenant_id=tenant_id)
        if existing is not None:
            return existing

        lead = await self._repo.get_lead(
            lead_id, tenant_id=tenant_id, scope=scope, user_id=user_id, team_id=team_id
        )
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        if lead.status not in (LeadStatus.NEW, LeadStatus.CONTACTED):
            raise IllegalStateTransitionError(f"Cannot qualify a lead in status '{lead.status}'")

        updated_lead = await self._repo.update_lead_status(
            lead_id,
            tenant_id=tenant_id,
            status=LeadStatus.QUALIFIED,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
        )
        if updated_lead is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_LEAD_STATUS_CHANGED,
            target=f"lead:{lead_id}",
            details={"from_status": lead.status.value, "to_status": LeadStatus.QUALIFIED.value},
        )
        await emit_lead_status_changed(
            lead_id=lead_id,
            tenant_id=tenant_id,
            from_status=lead.status.value,
            to_status=LeadStatus.QUALIFIED.value,
        )

        opportunity = Opportunity(
            tenant_id=tenant_id,
            name=_promote_from_lead(lead),
            lead_id=lead_id,
            stage=OpportunityStage.PROSPECTING,
            amount=amount,
            probability=probability if probability is not None else 0,
            expected_close_date=expected_close_date,
            owner_id=lead.owner_id,
            team_id=lead.team_id,
        )
        try:
            created = await self._repo.create_opportunity(opportunity)
        except ValueError:
            # Lost the UNIQUE (tenant_id, lead_id) race - the other caller won;
            # the replay probe resolves it.
            raced = await self._repo.get_opportunity_by_lead(lead_id, tenant_id=tenant_id)
            if raced is None:
                raise IllegalStateTransitionError(
                    "Failed to qualify lead: concurrent qualification outcome lost"
                ) from None
            return raced
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_OPPORTUNITY_CREATED,
            target=f"opportunity:{created.id}",
            details={"lead_id": str(lead_id), "name": created.name},
        )
        await self._record_timeline(
            tenant_id=tenant_id,
            entity_type=CrmEntityType.LEAD,
            entity_id=lead_id,
            event_type=CrmTimelineEventType.LEAD_QUALIFIED,
            title="Lead qualified",
            payload={"opportunity_id": str(created.id), "name": created.name},
        )
        await self._repo.commit()
        return created

    async def disqualify_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Lead:
        """``new|contacted -> disqualified`` (dead end)."""
        lead = await self._repo.get_lead(
            lead_id, tenant_id=tenant_id, scope=scope, user_id=user_id, team_id=team_id
        )
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        if lead.status not in (LeadStatus.NEW, LeadStatus.CONTACTED):
            raise IllegalStateTransitionError(f"Cannot disqualify a lead in status '{lead.status}'")

        updated = await self._repo.update_lead_status(
            lead_id,
            tenant_id=tenant_id,
            status=LeadStatus.DISQUALIFIED,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
        )
        if updated is None:
            raise NotFoundError(f"Lead {lead_id} not found")
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_LEAD_STATUS_CHANGED,
            target=f"lead:{lead_id}",
            details={"from_status": lead.status.value, "to_status": LeadStatus.DISQUALIFIED.value},
        )
        await emit_lead_status_changed(
            lead_id=lead_id,
            tenant_id=tenant_id,
            from_status=lead.status.value,
            to_status=LeadStatus.DISQUALIFIED.value,
        )
        await self._record_timeline(
            tenant_id=tenant_id,
            entity_type=CrmEntityType.LEAD,
            entity_id=lead_id,
            event_type=CrmTimelineEventType.LEAD_DISQUALIFIED,
            title="Lead disqualified",
        )
        await self._repo.commit()
        return updated

    # ------------------------------------------------------------------
    # Opportunities
    # ------------------------------------------------------------------

    async def create_opportunity(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        lead_id: uuid.UUID | None = None,
        amount: Money | None = None,
        probability: int = 0,
        expected_close_date: date | None = None,
        owner_id: uuid.UUID | None = None,
        team_id: uuid.UUID | None = None,
    ) -> Opportunity:
        if not name.strip():
            raise ValidationError("Opportunity name is required")
        if not 0 <= probability <= 100:
            raise ValidationError("Probability must be between 0 and 100")
        opportunity = Opportunity(
            tenant_id=tenant_id,
            name=name.strip(),
            lead_id=lead_id,
            stage=OpportunityStage.PROSPECTING,
            amount=amount,
            probability=probability,
            expected_close_date=expected_close_date,
            owner_id=owner_id,
            team_id=team_id,
        )
        created = await self._repo.create_opportunity(opportunity)
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_OPPORTUNITY_CREATED,
            target=f"opportunity:{created.id}",
            details={"name": created.name, "lead_id": str(lead_id) if lead_id else None},
        )
        await self._repo.commit()
        return created

    async def get_opportunity(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Opportunity:
        opportunity = await self._repo.get_opportunity(
            opportunity_id,
            tenant_id=tenant_id,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
        )
        if opportunity is None:
            raise NotFoundError(f"Opportunity {opportunity_id} not found")
        return opportunity

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
        return list(
            await self._repo.list_opportunities(
                tenant_id=tenant_id,
                scope=scope,
                user_id=user_id,
                team_id=team_id,
                stage=stage,
                from_close_date=from_close_date,
                to_close_date=to_close_date,
                offset=offset,
                limit=limit,
            )
        )

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
        return await self._repo.count_opportunities(
            tenant_id=tenant_id,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
            stage=stage,
            from_close_date=from_close_date,
            to_close_date=to_close_date,
        )

    async def update_opportunity(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Opportunity:
        """PATCH editable fields (never ``stage`` - use change_stage)."""
        if "probability" in changes and changes["probability"] is not None:
            probability = changes["probability"]
            if not isinstance(probability, int) or not 0 <= probability <= 100:
                raise ValidationError("Probability must be between 0 and 100")
        _normalize_amount_changes(changes)
        if not changes:
            return await self.get_opportunity(
                opportunity_id,
                tenant_id=tenant_id,
                scope=scope,
                user_id=user_id,
                team_id=team_id,
            )
        updated = await self._repo.update_opportunity(
            opportunity_id,
            tenant_id=tenant_id,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
            changes=changes,
        )
        if updated is None:
            raise NotFoundError(f"Opportunity {opportunity_id} not found")
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_OPPORTUNITY_UPDATED,
            target=f"opportunity:{opportunity_id}",
            details=_audit_details_from_changes(changes),
        )
        await self._repo.commit()
        return updated

    async def change_stage(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        stage: OpportunityStage,
        lost_reason: str | None = None,
    ) -> tuple[Opportunity, Customer | None]:
        """Advance the pipeline by ONE stage (or terminate won/lost).

        Returns ``(opportunity, customer)``; ``customer`` is set exactly on the
        ``won`` transition (the promotion result). Idempotent: a replay of
        ``won`` returns the existing promoted customer.
        """
        opportunity = await self._repo.get_opportunity(
            opportunity_id,
            tenant_id=tenant_id,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
        )
        if opportunity is None:
            raise NotFoundError(f"Opportunity {opportunity_id} not found")
        if opportunity.stage in (OpportunityStage.WON, OpportunityStage.LOST):
            raise IllegalStateTransitionError(
                f"Opportunity already terminated in stage '{opportunity.stage}'"
            )
        if stage == opportunity.stage:
            raise ValidationError(f"Opportunity is already in stage '{stage}'")
        if not _is_forward(stage, opportunity.stage):
            raise IllegalStateTransitionError(
                f"Cannot move opportunity from '{opportunity.stage}' to '{stage}'"
            )

        won = stage is OpportunityStage.WON
        lost = stage is OpportunityStage.LOST

        if won:
            customer = await self._promote_to_customer(
                opportunity, tenant_id=tenant_id, actor_user_id=user_id
            )
        else:
            customer = None

        now = datetime.now(UTC)
        updated = await self._repo.update_opportunity_stage(
            opportunity_id,
            tenant_id=tenant_id,
            stage=stage,
            scope=scope,
            user_id=user_id,
            team_id=team_id,
            won_at=now if won else None,
            lost_at=now if lost else None,
            lost_reason=lost_reason if lost else None,
        )
        if updated is None:
            raise NotFoundError(f"Opportunity {opportunity_id} not found")

        if won:
            await self._audit(
                tenant_id=tenant_id,
                action=CRM_OPPORTUNITY_WON,
                target=f"opportunity:{opportunity_id}",
                details={"from_stage": opportunity.stage.value},
            )
            await emit_opportunity_won(
                opportunity_id=opportunity_id,
                tenant_id=tenant_id,
                from_stage=opportunity.stage.value,
                amount=str(updated.amount.amount) if updated.amount else None,
            )
        elif lost:
            await self._audit(
                tenant_id=tenant_id,
                action=CRM_OPPORTUNITY_LOST,
                target=f"opportunity:{opportunity_id}",
                details={"from_stage": opportunity.stage.value, "lost_reason": lost_reason},
            )
            await emit_opportunity_lost(
                opportunity_id=opportunity_id,
                tenant_id=tenant_id,
                from_stage=opportunity.stage.value,
                lost_reason=lost_reason,
            )
        else:
            await self._audit(
                tenant_id=tenant_id,
                action=CRM_OPPORTUNITY_STAGE_CHANGED,
                target=f"opportunity:{opportunity_id}",
                details={"from_stage": opportunity.stage.value, "to_stage": stage.value},
            )
            await emit_opportunity_stage_changed(
                opportunity_id=opportunity_id,
                tenant_id=tenant_id,
                from_stage=opportunity.stage.value,
                to_stage=stage.value,
            )

        if won:
            event_type = CrmTimelineEventType.OPPORTUNITY_WON
            timeline_title = "Opportunity won"
            payload: dict[str, object] = {"from_stage": opportunity.stage.value}
            if updated.amount is not None:
                payload["amount"] = str(updated.amount.amount)
                payload["currency"] = updated.amount.currency
        elif lost:
            event_type = CrmTimelineEventType.OPPORTUNITY_LOST
            timeline_title = "Opportunity lost"
            payload = {"from_stage": opportunity.stage.value, "lost_reason": lost_reason}
        else:
            event_type = CrmTimelineEventType.OPPORTUNITY_STAGE_CHANGED
            timeline_title = f"Opportunity moved to {stage.value}"
            payload = {"from_stage": opportunity.stage.value, "to_stage": stage.value}
        await self._record_timeline(
            tenant_id=tenant_id,
            entity_type=CrmEntityType.OPPORTUNITY,
            entity_id=opportunity_id,
            event_type=event_type,
            title=timeline_title,
            payload=payload,
        )
        await self._repo.commit()
        return updated, customer

    async def _promote_to_customer(
        self,
        opportunity: Opportunity,
        *,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
    ) -> Customer | None:
        """Create the customer for a won opportunity (idempotent)."""
        assert opportunity.id is not None
        existing = await self._repo.get_customer_by_source_opportunity(
            opportunity.id, tenant_id=tenant_id
        )
        if existing is not None:
            return existing

        seq = await self._repo.next_customer_sequence(tenant_id)
        customer_code = f"{_CUST_CODE_PREFIX}-{datetime.now(UTC).year}-{seq:05d}"
        customer = Customer(
            tenant_id=tenant_id,
            customer_code=customer_code,
            name=opportunity.name,
            source_opportunity_id=opportunity.id,
        )
        try:
            created = await self._repo.create_customer(customer)
        except ValueError:
            # Lost the UNIQUE (tenant_id, source_opportunity_id) race.
            raced = await self._repo.get_customer_by_source_opportunity(
                opportunity.id, tenant_id=tenant_id
            )
            if raced is None:
                raise IllegalStateTransitionError(
                    "Failed to promote opportunity: concurrent promotion outcome lost"
                ) from None
            return raced
        assert created.id is not None
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_CUSTOMER_CREATED,
            target=f"customer:{created.id}",
            details={"customer_code": customer_code, "opportunity_id": str(opportunity.id)},
        )
        await emit_customer_created(
            customer_id=created.id,
            customer_code=customer_code,
            tenant_id=tenant_id,
            name=created.name,
        )
        await self._record_timeline(
            tenant_id=tenant_id,
            entity_type=CrmEntityType.CUSTOMER,
            entity_id=created.id,
            event_type=CrmTimelineEventType.CUSTOMER_CREATED,
            title="Customer created",
            payload={"customer_code": customer_code, "opportunity_id": str(opportunity.id)},
        )
        return created

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    async def create_customer(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        credit_limit: Money | None = None,
    ) -> Customer:
        if not name.strip():
            raise ValidationError("Customer name is required")
        seq = await self._repo.next_customer_sequence(tenant_id)
        customer_code = f"{_CUST_CODE_PREFIX}-{datetime.now(UTC).year}-{seq:05d}"
        customer = Customer(
            tenant_id=tenant_id,
            customer_code=customer_code,
            name=name.strip(),
            email=email,
            phone=phone,
            credit_limit=credit_limit,
        )
        created = await self._repo.create_customer(customer)
        assert created.id is not None
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_CUSTOMER_CREATED,
            target=f"customer:{created.id}",
            details={"customer_code": customer_code},
        )
        await emit_customer_created(
            customer_id=created.id,
            customer_code=customer_code,
            tenant_id=tenant_id,
            name=created.name,
        )
        await self._record_timeline(
            tenant_id=tenant_id,
            entity_type=CrmEntityType.CUSTOMER,
            entity_id=created.id,
            event_type=CrmTimelineEventType.CUSTOMER_CREATED,
            title="Customer created",
            payload={"customer_code": customer_code},
        )
        await self._repo.commit()
        return created

    async def get_customer(self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID) -> Customer:
        customer = await self._repo.get_customer(customer_id, tenant_id=tenant_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found")
        return customer

    async def list_customers(
        self,
        *,
        tenant_id: uuid.UUID,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Customer]:
        return list(
            await self._repo.list_customers(
                tenant_id=tenant_id,
                include_inactive=include_inactive,
                offset=offset,
                limit=limit,
            )
        )

    async def count_customers(
        self,
        *,
        tenant_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> int:
        """Total rows matching :meth:`list_customers` filters (pagination meta)."""
        return await self._repo.count_customers(
            tenant_id=tenant_id,
            include_inactive=include_inactive,
        )

    async def update_customer(
        self,
        customer_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Customer:
        _normalize_credit_limit_changes(changes)
        if not changes:
            return await self.get_customer(customer_id, tenant_id=tenant_id)
        updated = await self._repo.update_customer(
            customer_id, tenant_id=tenant_id, changes=changes
        )
        if updated is None:
            raise NotFoundError(f"Customer {customer_id} not found")
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_CUSTOMER_UPDATED,
            target=f"customer:{customer_id}",
            details=_audit_details_from_changes(changes),
        )
        await self._repo.commit()
        return updated

    async def deactivate_customer(
        self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer:
        updated = await self._repo.deactivate_customer(customer_id, tenant_id=tenant_id)
        if updated is None:
            raise NotFoundError(f"Customer {customer_id} not found")
        await self._audit(
            tenant_id=tenant_id,
            action=CRM_CUSTOMER_DEACTIVATED,
            target=f"customer:{customer_id}",
            details={},
        )
        await self._repo.commit()
        return updated

    # ------------------------------------------------------------------
    # Internal audit helper
    # ------------------------------------------------------------------

    async def _record_timeline(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        event_type: CrmTimelineEventType,
        title: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Append a business event to the curated timeline (same transaction)."""
        await self._timeline.record_timeline_event(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            title=title,
            actor_id=uuid.UUID(TenantContext.get_user_id())
            if TenantContext.get_user_id()
            else None,
            payload=payload,
        )

    async def _audit(
        self,
        *,
        tenant_id: uuid.UUID,
        action: str,
        target: str,
        details: dict[str, Any] | None,
    ) -> None:
        await self._audit_service.log(
            action=action,
            target=target,
            user_id=TenantContext.get_user_id(),
            tenant_id=str(tenant_id),
            details=details,
        )


def _is_forward(stage: OpportunityStage, current: OpportunityStage) -> bool:
    """True when ``stage`` is a legal one-step successor of ``current``.

    ``won``/``lost`` may terminate any non-terminal stage; the pipeline moves
    strictly forward one stage at a time.
    """
    pipeline = (
        OpportunityStage.PROSPECTING,
        OpportunityStage.QUALIFIED,
        OpportunityStage.PROPOSAL,
        OpportunityStage.NEGOTIATION,
    )
    if stage in (OpportunityStage.WON, OpportunityStage.LOST):
        return current in pipeline
    if stage not in pipeline or current not in pipeline:
        return False
    return pipeline.index(stage) == pipeline.index(current) + 1


def _normalize_amount_changes(changes: dict[str, object]) -> None:
    """Translate a schema ``amount`` + ``currency`` pair into a :class:`Money`.

    A bare ``amount`` keeps the default currency; an explicit ``None`` amount
    clears the money (the repository clears the currency alongside); a bare
    ``currency`` without an amount is refused (the DB CHECK forbids a currency
    without an amount).
    """
    if "amount" in changes:
        amount = changes["amount"]
        if amount is None:
            changes.pop("currency", None)
            return
        currency = str(changes.pop("currency", "USD"))
        changes["amount"] = Money(Decimal(str(amount)), currency)
    elif "currency" in changes:
        raise ValidationError("A currency change must accompany an amount")


def _audit_details_from_changes(changes: dict[str, object]) -> dict[str, object]:
    """Serialize normalized PATCH changes for the JSONB audit trail.

    The normalization step replaces the API's ``amount``/``currency`` pair with
    a single :class:`Money` value object, which is not JSON-serializable -
    flatten it back to the pair so audit ``details`` is always plain JSON.
    """
    details: dict[str, object] = {}
    for key, value in changes.items():
        if isinstance(value, Money):
            details[key] = str(value.amount)
            details["currency"] = value.currency
        else:
            details[key] = value
    return details


def _normalize_credit_limit_changes(changes: dict[str, object]) -> None:
    """Translate a schema ``credit_limit`` + ``currency`` pair into :class:`Money`."""
    if "credit_limit" in changes:
        limit = changes["credit_limit"]
        if limit is None:
            changes.pop("currency", None)
            return
        currency = str(changes.pop("currency", "USD"))
        changes["credit_limit"] = Money(Decimal(str(limit)), currency)
    elif "currency" in changes:
        raise ValidationError("A currency change must accompany a credit limit")
