"""CRM ports - persistence contract for the CRM feature.

Declares what the repository must offer so the future service depends on a
Protocol (hexagonal "ports") rather than the concrete SQLAlchemy
implementation. The repository lives in the same feature package, so there is
no import-linter violation.

Owner/team/all scoping: every read takes an explicit ``scope`` (a
:class:`DataScope` resolved ONCE per request by ``core.db.rbac`` - never a
role name) plus the caller's ``user_id`` / ``team_id``. The repository
translates that into a SQL filter; the service can only pass narrower ids, it
can never broaden the scope.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
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
        OpportunityStage,
    )


class CrmRepositoryPort(Protocol):
    """Persistence contract for leads, opportunities, and customers."""

    # --- Transaction control ---
    async def commit(self) -> None:
        """Commit the current transaction (write handlers, before the response)."""

    # --- Document sequences (wired at the composition root) ---
    async def next_customer_sequence(self, tenant_id: uuid.UUID) -> int: ...

    # --- Leads ---
    async def create_lead(self, lead: Lead) -> Lead: ...

    async def get_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Lead | None: ...

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
    ) -> Sequence[Lead]: ...

    async def count_leads(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        status: LeadStatus | None = None,
        source: str | None = None,
    ) -> int: ...

    async def find_leads_by_email(self, email: str, *, tenant_id: uuid.UUID) -> Sequence[Lead]: ...

    async def update_lead_status(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        status: LeadStatus,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Lead | None: ...

    async def update_lead(
        self,
        lead_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Lead | None: ...

    # --- Opportunities ---
    async def create_opportunity(self, opportunity: Opportunity) -> Opportunity: ...

    async def get_opportunity(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Opportunity | None: ...

    async def get_opportunity_by_lead(
        self, lead_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Opportunity | None: ...

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
    ) -> Sequence[Opportunity]: ...

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
    ) -> int: ...

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
    ) -> Opportunity | None: ...

    async def update_opportunity(
        self,
        opportunity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Opportunity | None: ...

    # --- Customers ---
    async def create_customer(self, customer: Customer) -> Customer: ...

    async def get_customer(
        self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer | None: ...

    async def get_customer_by_code(self, code: str, *, tenant_id: uuid.UUID) -> Customer | None: ...

    async def get_customer_by_source_opportunity(
        self, opportunity_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer | None: ...

    async def list_customers(
        self,
        *,
        tenant_id: uuid.UUID,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Customer]: ...

    async def count_customers(
        self,
        *,
        tenant_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> int: ...

    async def update_customer(
        self,
        customer_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Customer | None: ...

    async def deactivate_customer(
        self, customer_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Customer | None: ...


class CrmTimelinePort(Protocol):
    """Persistence contract for the curated CRM timeline (business events).

    Distinct from the security/compliance ``audit_logs`` trail and from the
    async ``crm.*`` domain events. Writers call this transactionally inside
    the same request as the business action.
    """

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
    ) -> TimelineEvent: ...


class CrmWorkspaceRepositoryPort(CrmRepositoryPort, Protocol):
    """Persistence contract for the CRM workspace surface.

    Contacts, activities, notes, the merged timeline, overview aggregates, and
    server-side search - plus the anchor probes from :class:`CrmRepositoryPort`
    the workspace service uses to validate that an entity exists in the tenant.
    """

    # --- Contacts (tenant-scoped, like customers) ---
    async def create_contact(self, contact: Contact) -> Contact: ...

    async def get_contact(
        self, contact_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Contact | None: ...

    async def list_contacts(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        include_inactive: bool = False,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Contact]: ...

    async def count_contacts(
        self,
        *,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID | None = None,
        include_inactive: bool = False,
    ) -> int: ...

    async def update_contact(
        self,
        contact_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Contact | None: ...

    async def deactivate_contact(
        self, contact_id: uuid.UUID, *, tenant_id: uuid.UUID
    ) -> Contact | None: ...

    # --- Activities (owner/team-scoped) ---
    async def create_activity(self, activity: Activity) -> Activity: ...

    async def get_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Activity | None: ...

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
    ) -> Sequence[Activity]: ...

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
    ) -> int: ...

    async def update_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        changes: dict[str, object],
    ) -> Activity | None: ...

    async def complete_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        completed_by: uuid.UUID,
    ) -> Activity | None: ...

    async def delete_activity(
        self,
        activity_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Activity | None: ...

    # --- Notes (tenant-scoped) ---
    async def create_note(self, note: Note) -> Note: ...

    async def get_note(self, note_id: uuid.UUID, *, tenant_id: uuid.UUID) -> Note | None: ...

    async def list_notes(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType | None = None,
        entity_id: uuid.UUID | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> Sequence[Note]: ...

    async def count_notes(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType | None = None,
        entity_id: uuid.UUID | None = None,
    ) -> int: ...

    async def update_note(
        self,
        note_id: uuid.UUID,
        *,
        tenant_id: uuid.UUID,
        changes: dict[str, object],
    ) -> Note | None: ...

    async def delete_note(self, note_id: uuid.UUID, *, tenant_id: uuid.UUID) -> Note | None: ...

    # --- Timeline (DB-layer UNION of activities + notes + events) ---
    async def get_timeline(
        self,
        *,
        tenant_id: uuid.UUID,
        entity_type: CrmEntityType,
        entity_id: uuid.UUID,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[Sequence[TimelineItem], int]: ...

    # --- Overview aggregates (real data only) ---
    async def lead_status_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Sequence[tuple[LeadStatus, int]]: ...

    async def lead_source_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Sequence[tuple[str | None, int]]: ...

    async def opportunity_funnel(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Sequence[tuple[OpportunityStage, str | None, int, Decimal]]: ...

    async def won_lost_counts(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
    ) -> Sequence[tuple[OpportunityStage, int]]: ...

    async def customer_counts(self, *, tenant_id: uuid.UUID) -> tuple[int, int]: ...

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
    ) -> dict[str, int]: ...

    async def recent_won_opportunities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        limit: int = 5,
    ) -> Sequence[Opportunity]: ...

    async def top_opportunities(
        self,
        *,
        tenant_id: uuid.UUID,
        scope: DataScope,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        limit: int = 5,
    ) -> Sequence[Opportunity]: ...

    # --- Search (server-side) ---
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
    ) -> tuple[Sequence[CrmSearchHit], int]: ...

    # --- Global timeline (dashboard feed) ---
    async def get_global_timeline(
        self,
        *,
        tenant_id: uuid.UUID,
        offset: int = 0,
        limit: int = 10,
    ) -> Sequence[TimelineItem]: ...

    # --- Timeline event recording ---
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
    ) -> TimelineEvent: ...
