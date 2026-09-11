"""Unit tests for the CRM AI orchestration service (SKY-61).

Tests wire mock gateway, repo, and audit to verify the service orchestrates
the deterministic engines correctly and persists/audits every action.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from ai_agent.features.crm.deal_health import DealHealth
from ai_agent.features.crm.gateway import (
    ActivityRef,
    LeadRef,
    OpportunityRef,
)
from ai_agent.features.crm.scoring import LeadScore
from ai_agent.features.crm.service import CrmAiService
from ai_agent.models.ai_follow_up_suggestion import AiFollowUpSuggestionModel

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
LEAD_ID = uuid.uuid4()
OPP_ID = uuid.uuid4()
NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


# ---- stubs -----------------------------------------------------------------


class FakeLead:
    def __init__(self) -> None:
        self.id = LEAD_ID
        self.status = "new"
        self.source = "website"
        self.created_at = NOW - timedelta(days=30)
        self.owner_id = USER_ID
        self.has_name = True
        self.has_email = True
        self.display_name = "Beta Corp"


class FakeOpp:
    def __init__(self) -> None:
        self.id = OPP_ID
        self.stage = "negotiation"
        self.probability = 60
        self.has_amount = True
        self.created_at = NOW - timedelta(days=20)
        self.owner_id = USER_ID
        self.last_stage_change_at = NOW - timedelta(days=10)
        self.expected_close_date = (NOW + timedelta(days=5)).date()
        self.display_name = "Acme Renewal"


class FakeGateway:
    def __init__(self) -> None:
        self._leads: dict[uuid.UUID, Any] = {LEAD_ID: FakeLead()}
        self._opps: dict[uuid.UUID, Any] = {OPP_ID: FakeOpp()}
        self._site_opps: list[Any] = []
        self._activities: list[ActivityRef] = [
            ActivityRef(
                id=uuid.uuid4(),
                kind="call",
                completed_at=NOW - timedelta(days=10),
                created_at=NOW - timedelta(days=10),
            ),
        ]

    async def get_lead(self, *, lead_id: uuid.UUID) -> LeadRef:
        return self._leads[lead_id]  # type: ignore[return-value]

    async def get_opportunity(self, *, opportunity_id: uuid.UUID) -> OpportunityRef:
        return self._opps[opportunity_id]  # type: ignore[return-value]

    async def list_activities_for_entity(
        self, *, entity_type: str, entity_id: uuid.UUID
    ) -> list[ActivityRef]:
        return self._activities

    async def list_leads(self, *, page: int = 1) -> list[LeadRef]:
        return []

    async def list_opportunities(self, *, page: int = 1) -> list[OpportunityRef]:
        return self._site_opps


class FakeRepo:
    def __init__(self) -> None:
        self._saved_leads: list[Any] = []
        self._saved_deals: list[Any] = []
        self._follow_ups: list[AiFollowUpSuggestionModel] = []
        self._pending_count = 0

    async def save_lead_score(self, row: Any) -> None:
        self._saved_leads.append(row)

    async def save_deal_health(self, row: Any) -> None:
        self._saved_deals.append(row)

    async def list_pending_for_user(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[AiFollowUpSuggestionModel]:
        return [f for f in self._follow_ups if f.user_id == user_id and f.status == "pending"]

    async def get_for_apply(
        self, *, tenant_id: uuid.UUID, suggestion_id: uuid.UUID
    ) -> AiFollowUpSuggestionModel | None:
        for f in self._follow_ups:
            if f.id == suggestion_id:
                return f
        return None

    async def mark_applied(
        self, *, row: AiFollowUpSuggestionModel, applied_by: uuid.UUID, activity_id: uuid.UUID
    ) -> None:
        row.status = "sent"
        row.applied_by = applied_by
        row.activity_id = activity_id

    async def mark_dismissed(self, *, row: AiFollowUpSuggestionModel) -> None:
        row.status = "dismissed"


class FakeAudit:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def log(
        self,
        *,
        action: str,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        input_payload: dict[str, Any] | None = None,
        output_payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        self.calls.append({"action": action, "tenant_id": tenant_id, "user_id": user_id})
        return None


# ---- helpers ---------------------------------------------------------------


def _make_service(
    gateway: Any = None,
    repo: Any = None,
    audit: Any = None,
) -> CrmAiService:
    return CrmAiService(
        gateway=gateway or FakeGateway(),
        repo=repo or FakeRepo(),
        audit=audit or FakeAudit(),
    )


def _make_suggestion(
    *,
    status: str = "pending",
    entity_type: str = "lead",
    user_id: uuid.UUID = USER_ID,
) -> AiFollowUpSuggestionModel:
    return AiFollowUpSuggestionModel(
        tenant_id=TENANT_ID,
        entity_type=entity_type,
        entity_id=LEAD_ID,
        user_id=user_id,
        suggestion_type="email",
        draft_content="Hi Beta Corp, just checking in.",
        reasoning="No activity for 14 days.",
        confidence=0.6,
        expires_at=NOW + timedelta(days=7),
        status=status,
    )


# ---- tests -----------------------------------------------------------------


class TestComputeLeadScore:
    async def test_persists_and_audits(self) -> None:
        service = _make_service()
        result = await service.compute_lead_score(
            tenant_id=TENANT_ID,
            lead_id=LEAD_ID,
            user_id=USER_ID,
        )
        assert isinstance(result, LeadScore)
        assert result.score >= 0
        assert len(service._repo._saved_leads) == 1  # type: ignore[attr-defined]
        audit = service._audit  # type: ignore[attr-defined]
        assert len(audit.calls) == 1
        assert audit.calls[0]["action"] == "ai.crm.lead.scored"


class TestComputeDealHealth:
    async def test_persists_and_audits(self) -> None:
        service = _make_service()
        result = await service.compute_deal_health(
            tenant_id=TENANT_ID,
            opportunity_id=OPP_ID,
            user_id=USER_ID,
        )
        assert isinstance(result, DealHealth)
        assert result.health in ("green", "yellow", "red")
        assert len(service._repo._saved_deals) == 1  # type: ignore[attr-defined]
        audit = service._audit  # type: ignore[attr-defined]
        assert audit.calls[0]["action"] == "ai.crm.deal.health"


class TestSweepDealHealth:
    async def test_sweeps_only_horizon_deals_and_counts_bands(self) -> None:
        gateway = FakeGateway()
        base = datetime.now(UTC)
        gateway._activities = [
            ActivityRef(
                id=uuid.uuid4(),
                kind="call",
                completed_at=base - timedelta(days=2),
                created_at=base - timedelta(days=2),
            ),
        ]
        gateway._site_opps = [
            FakeOpp(),
            FakeOpp(),
            FakeOpp(),
            FakeOpp(),
        ]
        gateway._site_opps[0].id = uuid.uuid4()
        gateway._site_opps[0].created_at = base - timedelta(days=30)
        gateway._site_opps[0].last_stage_change_at = base - timedelta(days=5)
        gateway._site_opps[0].expected_close_date = (base + timedelta(days=5)).date()
        gateway._site_opps[1].id = uuid.uuid4()
        gateway._site_opps[1].expected_close_date = (base + timedelta(days=10)).date()
        gateway._site_opps[1].probability = 10  # low prob -> yellow
        gateway._site_opps[2].id = uuid.uuid4()
        gateway._site_opps[2].expected_close_date = (base + timedelta(days=400)).date()
        gateway._site_opps[3].id = uuid.uuid4()
        gateway._site_opps[3].expected_close_date = (base - timedelta(days=5)).date()
        for opp in gateway._site_opps:
            gateway._opps[opp.id] = opp

        repo = FakeRepo()
        service = _make_service(gateway=gateway, repo=repo)
        result = await service.sweep_deal_health(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )

        assert result.assessed == 2
        assert result.healthy == 1
        assert result.at_risk == 1
        assert result.critical == 0
        # Far-away and past deals are outside the horizon and must be skipped.
        assert len(repo._saved_deals) == 2
        audit = service._audit  # type: ignore[attr-defined]
        assert [call["action"] for call in audit.calls] == ["ai.crm.deal.health"] * 2


class TestListPendingFollowUps:
    async def test_delegates_to_repo(self) -> None:
        repo = FakeRepo()
        suggestion = _make_suggestion()
        repo._follow_ups.append(suggestion)
        service = _make_service(repo=repo)
        result = await service.list_pending_follow_ups(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
        )
        assert len(result) == 1
        assert result[0].id == suggestion.id


class TestApplyFollowUp:
    async def test_marks_applied_and_audits(self) -> None:
        repo = FakeRepo()
        suggestion = _make_suggestion()
        repo._follow_ups.append(suggestion)
        service = _make_service(repo=repo)
        activity_id = uuid.uuid4()
        result = await service.apply_follow_up(
            tenant_id=TENANT_ID,
            suggestion_id=suggestion.id,
            user_id=USER_ID,
            activity_id=activity_id,
        )
        assert result.status == "sent"
        assert result.activity_id == activity_id
        assert result.applied_by == USER_ID
        audit = service._audit  # type: ignore[attr-defined]
        assert audit.calls[0]["action"] == "ai.crm.follow_up.applied"

    async def test_raises_on_not_found(self) -> None:
        service = _make_service()
        with pytest.raises(ValueError, match="not found"):
            await service.apply_follow_up(
                tenant_id=TENANT_ID,
                suggestion_id=uuid.uuid4(),
                user_id=USER_ID,
                activity_id=uuid.uuid4(),
            )

    async def test_raises_on_wrong_status(self) -> None:
        repo = FakeRepo()
        suggestion = _make_suggestion(status="dismissed")
        repo._follow_ups.append(suggestion)
        service = _make_service(repo=repo)
        with pytest.raises(ValueError, match="dismissed"):
            await service.apply_follow_up(
                tenant_id=TENANT_ID,
                suggestion_id=suggestion.id,
                user_id=USER_ID,
                activity_id=uuid.uuid4(),
            )

    async def test_raises_on_wrong_user(self) -> None:
        repo = FakeRepo()
        suggestion = _make_suggestion(user_id=uuid.uuid4())
        repo._follow_ups.append(suggestion)
        service = _make_service(repo=repo)
        with pytest.raises(ValueError, match="another user"):
            await service.apply_follow_up(
                tenant_id=TENANT_ID,
                suggestion_id=suggestion.id,
                user_id=USER_ID,
                activity_id=uuid.uuid4(),
            )


class TestDismissFollowUp:
    async def test_marks_dismissed_and_audits(self) -> None:
        repo = FakeRepo()
        suggestion = _make_suggestion()
        repo._follow_ups.append(suggestion)
        service = _make_service(repo=repo)
        result = await service.dismiss_follow_up(
            tenant_id=TENANT_ID,
            suggestion_id=suggestion.id,
            user_id=USER_ID,
        )
        assert result.status == "dismissed"
        audit = service._audit  # type: ignore[attr-defined]
        assert audit.calls[0]["action"] == "ai.crm.follow_up.dismissed"

    async def test_raises_on_not_found(self) -> None:
        service = _make_service()
        with pytest.raises(ValueError, match="not found"):
            await service.dismiss_follow_up(
                tenant_id=TENANT_ID,
                suggestion_id=uuid.uuid4(),
                user_id=USER_ID,
            )
