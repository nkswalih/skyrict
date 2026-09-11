"""Unit tests for the Sales Coach agent (SKY-90).

Tests the tools (analyze_rep_activity), graph node functions, deterministic
fallback suggestions, and the coaching system prompt behavior. All tests are
pure — no database, no LLM providers, no network.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

from ai_agent.features.sales_coach.graph import (
    SalesCoachDeps,
    SalesCoachState,
    _deterministic_suggestions,
    _generate_coaching_node,
)
from ai_agent.features.sales_coach.tools import analyze_rep_activity

NOW = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)
REP_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeOpp:
    id: uuid.UUID
    stage: str
    probability: int
    has_amount: bool
    created_at: datetime
    owner_id: uuid.UUID | None
    last_stage_change_at: datetime
    expected_close_date: date | None
    amount: Any = None
    currency: str | None = None
    display_name: str | None = None


@dataclass
class _FakeActivity:
    id: uuid.UUID
    kind: str
    completed_at: datetime | None
    created_at: datetime


@dataclass
class _FakeLead:
    id: uuid.UUID
    status: str
    source: str | None
    created_at: datetime
    owner_id: uuid.UUID | None
    has_name: bool
    has_email: bool
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    phone: str | None = None
    company: str | None = None
    display_name: str | None = None


class FakeCrmGateway:
    """Minimal CRM gateway fake for Sales Coach tool tests."""

    def __init__(
        self,
        *,
        opportunities: list[_FakeOpp] | None = None,
        leads: list[_FakeLead] | None = None,
        activities: list[_FakeActivity] | None = None,
    ) -> None:
        self._opps = opportunities or []
        self._leads = leads or []
        self._activities = activities or []
        self._list_opps_call_count = 0

    async def list_opportunities(self, *, page: int = 1) -> list[_FakeOpp]:
        self._list_opps_call_count += 1
        return self._opps

    async def list_leads(self, *, page: int = 1) -> list[_FakeLead]:
        return self._leads

    async def list_activities_for_entity(
        self, *, entity_type: str, entity_id: uuid.UUID
    ) -> list[_FakeActivity]:
        return [a for a in self._activities if a.id == entity_id]


# ---------------------------------------------------------------------------
# Tests — analyze_rep_activity tool
# ---------------------------------------------------------------------------


class TestAnalyzeRepActivity:
    """Tests for the CRM activity analysis tool."""

    async def test_returns_empty_when_no_opps(self) -> None:
        gateway = FakeCrmGateway()
        result = await analyze_rep_activity(crm_gateway=gateway, rep_user_id=str(REP_ID))
        assert result["opportunities"] == []
        assert result["activities"] == []

    async def test_filters_opps_by_owner(self) -> None:
        opp = _FakeOpp(
            id=uuid.uuid4(),
            stage="proposal",
            probability=60,
            has_amount=True,
            created_at=NOW - timedelta(days=10),
            owner_id=REP_ID,
            last_stage_change_at=NOW - timedelta(days=5),
            expected_close_date=NOW.date() + timedelta(days=7),
            amount=10000,
            currency="USD",
            display_name="Acme Deal",
        )
        other_opp = _FakeOpp(
            id=uuid.uuid4(),
            stage="lead",
            probability=10,
            has_amount=False,
            created_at=NOW - timedelta(days=2),
            owner_id=uuid.uuid4(),  # different rep
            last_stage_change_at=NOW - timedelta(days=1),
            expected_close_date=None,
        )
        gateway = FakeCrmGateway(opportunities=[opp, other_opp])
        result = await analyze_rep_activity(crm_gateway=gateway, rep_user_id=str(REP_ID))
        assert len(result["opportunities"]) == 1
        assert result["opportunities"][0]["display_name"] == "Acme Deal"

    async def test_includes_activities(self) -> None:
        opp_id = uuid.uuid4()
        opp = _FakeOpp(
            id=opp_id,
            stage="negotiation",
            probability=80,
            has_amount=True,
            created_at=NOW - timedelta(days=20),
            owner_id=REP_ID,
            last_stage_change_at=NOW - timedelta(days=3),
            expected_close_date=NOW.date() + timedelta(days=3),
        )
        activity = _FakeActivity(
            id=opp_id,
            kind="call",
            completed_at=NOW - timedelta(days=1),
            created_at=NOW - timedelta(days=1),
        )
        gateway = FakeCrmGateway(opportunities=[opp], activities=[activity])
        result = await analyze_rep_activity(crm_gateway=gateway, rep_user_id=str(REP_ID))
        assert result["activity_count"] == 1
        assert result["activities"][0]["kind"] == "call"

    async def test_sorts_activities_by_recency(self) -> None:
        opp_id = uuid.uuid4()
        opp = _FakeOpp(
            id=opp_id,
            stage="lead",
            probability=10,
            has_amount=False,
            created_at=NOW - timedelta(days=30),
            owner_id=REP_ID,
            last_stage_change_at=NOW - timedelta(days=30),
            expected_close_date=None,
        )
        old_activity = _FakeActivity(
            id=opp_id,
            kind="email",
            completed_at=NOW - timedelta(days=10),
            created_at=NOW - timedelta(days=10),
        )
        new_activity = _FakeActivity(
            id=opp_id,
            kind="call",
            completed_at=NOW - timedelta(days=1),
            created_at=NOW - timedelta(days=1),
        )
        gateway = FakeCrmGateway(
            opportunities=[opp],
            activities=[old_activity, new_activity],
        )
        result = await analyze_rep_activity(crm_gateway=gateway, rep_user_id=str(REP_ID))
        assert result["activities"][0]["kind"] == "call"
        assert result["activities"][1]["kind"] == "email"


# ---------------------------------------------------------------------------
# Tests — deterministic coaching suggestions
# ---------------------------------------------------------------------------


class TestDeterministicSuggestions:
    """Tests for the provider-free fallback suggestion generator."""

    def test_empty_data_returns_empty(self) -> None:
        result = _deterministic_suggestions({"opportunities": [], "activities": []})
        assert result == []

    def test_stalled_deals_suggest_follow_up(self) -> None:
        data = {
            "opportunities": [
                {
                    "id": "o1",
                    "stage": "proposal",
                    "expected_close_date": "2026-09-15",
                    "display_name": "Deal 1",
                },
                {
                    "id": "o2",
                    "stage": "negotiation",
                    "expected_close_date": "2026-09-20",
                    "display_name": "Deal 2",
                },
            ],
            "activities": [],
        }
        result = _deterministic_suggestions(data)
        assert len(result) >= 1
        assert result[0]["suggestion_type"] == "follow_up"
        assert "stalled" in result[0]["title"].lower() or "follow" in result[0]["title"].lower()

    def test_many_opps_suggest_pipeline_review(self) -> None:
        opps = [{"id": f"o{i}", "stage": "lead", "expected_close_date": None} for i in range(8)]
        data = {"opportunities": opps, "activities": []}
        result = _deterministic_suggestions(data)
        types = [s["suggestion_type"] for s in result]
        assert "pipeline_review" in types

    def test_suggestions_have_required_fields(self) -> None:
        data = {
            "opportunities": [
                {"id": "o1", "stage": "proposal", "expected_close_date": "2026-09-15"},
            ],
            "activities": [],
        }
        result = _deterministic_suggestions(data)
        for suggestion in result:
            assert "suggestion_type" in suggestion
            assert "title" in suggestion
            assert "body" in suggestion
            assert "evidence" in suggestion


# ---------------------------------------------------------------------------
# Tests — generate coaching node (LLM-free path)
# ---------------------------------------------------------------------------


class TestGenerateCoachingNode:
    """Tests for the LLM coaching generation node (deterministic fallback)."""

    async def test_returns_empty_for_no_rep_id(self) -> None:
        state: SalesCoachState = {}
        result = await _generate_coaching_node(state, extra=None)
        assert result["coaching_suggestions"] == []

    async def test_returns_empty_for_none_deps(self) -> None:
        state: SalesCoachState = {"rep_user_id": str(REP_ID)}
        result = await _generate_coaching_node(state, extra=None)
        assert result["coaching_suggestions"] == []

    async def test_deterministic_fallback_no_providers(self) -> None:
        """When no LLM providers are configured, falls back to deterministic."""
        gateway = FakeCrmGateway(
            opportunities=[
                _FakeOpp(
                    id=uuid.uuid4(),
                    stage="proposal",
                    probability=60,
                    has_amount=True,
                    created_at=NOW - timedelta(days=10),
                    owner_id=REP_ID,
                    last_stage_change_at=NOW - timedelta(days=5),
                    expected_close_date=NOW.date() + timedelta(days=3),
                    display_name="Stalled Deal",
                )
            ]
        )
        mock_llm = AsyncMock()
        mock_llm.has_providers = False

        extra = SalesCoachDeps(
            crm_gateway=gateway,  # type: ignore[arg-type]
            suggestion_repo=AsyncMock(),  # type: ignore[arg-type]
            llm_router=mock_llm,
        )
        state: SalesCoachState = {"rep_user_id": str(REP_ID)}
        result = await _generate_coaching_node(state, extra=extra)
        suggestions = result["coaching_suggestions"]
        assert len(suggestions) >= 1
        assert suggestions[0]["suggestion_type"] == "follow_up"
