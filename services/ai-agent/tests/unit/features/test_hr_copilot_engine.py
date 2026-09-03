"""Unit tests for the HR Copilot engine.

Exercised with a scripted LLM router double and an in-memory gateway double -
no network or database. Focus:
- the aggregate context is grounded into the prompt;
- individual employee rows and L2 attrition signals are grounded ONLY when the
  gateway supplied them (i.e. core granted the caller's role access); when the
  gateway returns ``None``/``[]`` the prompt stays aggregate-only;
- the guardrail against inventing/compensation is always present;
- a missing context part degrades to an explicit "unavailable" instruction.
"""

from __future__ import annotations

import uuid
from datetime import date

from ai_agent.core.providers.base import LlmCompletion, LlmRequest
from ai_agent.features.hr_copilot.engine import HrCopilotEngine
from ai_agent.features.hr_copilot.gateway import (
    AttritionRiskRef,
    HrEmployeeRef,
    HrLeavePolicyCtx,
    HrOverviewCtx,
    HrTenureCtx,
)


class FakeLlmRouter:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest) -> LlmCompletion:
        self.requests.append(request)
        return LlmCompletion(text=self.text, model_used="fake-model", latency_ms=1)


_MISSING = object()  # distinguishes "not provided" from an explicit None
_DEFAULT_EMPTY = object()  # employees default
_DEFAULT_NONE = None  # attrition default: core denied the L2 tier


class FakeGateway:
    """In-memory ``HrGatewayPort`` double - scriptable per context part."""

    def __init__(
        self,
        *,
        overview: object,
        tenure: object,
        policy: object,
        employees: object = _DEFAULT_EMPTY,
        attrition: object = _DEFAULT_EMPTY,
    ) -> None:
        self.overview = overview
        self.tenure = tenure
        self.policy = policy
        self.employees = [] if employees is _DEFAULT_EMPTY else employees
        # ``None`` represents core denying the L2 individual tier (403).
        self.attrition = _DEFAULT_NONE if attrition is _DEFAULT_EMPTY else attrition
        self.calls: list[str] = []

    async def get_overview(self) -> HrOverviewCtx | None:
        self.calls.append("overview")
        return self.overview if self.overview is not _MISSING else None  # type: ignore[return-value]

    async def get_tenure(self) -> HrTenureCtx | None:
        self.calls.append("tenure")
        return self.tenure if self.tenure is not _MISSING else None  # type: ignore[return-value]

    async def get_leave_policy(self) -> HrLeavePolicyCtx | None:
        self.calls.append("policy")
        return self.policy if self.policy is not _MISSING else None  # type: ignore[return-value]

    async def list_employees(self) -> list[HrEmployeeRef]:
        self.calls.append("employees")
        return list(self.employees)

    async def get_attrition(self) -> list[AttritionRiskRef] | None:
        self.calls.append("attrition")
        return self.attrition


def _overview() -> HrOverviewCtx:
    return HrOverviewCtx(
        total_headcount=120,
        departments=(("Engineering", 40), ("Sales", 25)),
        tenure_bands=(("1-3", 70), ("3-5", 30)),
        narrative="Headcount grew 4% MoM.",
    )


def _policy() -> HrLeavePolicyCtx:
    return HrLeavePolicyCtx(
        casual_days_per_year=12,
        sick_days_per_year=8,
        effective_from="2026-01-01",
    )


def _employee(index: int = 1) -> HrEmployeeRef:
    return HrEmployeeRef(
        id=uuid.UUID(f"{index:08d}-0000-0000-0000-000000000000"),
        employee_number=f"E{index:03d}",
        first_name="Asha",
        last_name=f"Kumar{index}",
        job_title="Engineer",
        hire_date=date(2022, 5, 1),
        employment_status="active",
    )


def _risk(index: int = 1) -> AttritionRiskRef:
    return AttritionRiskRef(
        employee_id=uuid.UUID(f"{index + 10:08d}-0000-0000-0000-000000000000"),
        employee_number=f"E{index:03d}",
        name=f"Employee {index}",
        department_name="Engineering",
        risk_band="high",
        score=0.85,
        confidence=0.9,
        factors=("long tenure",),
    )


def _make_engine(
    llm_text: str,
    *,
    overview: object = _MISSING,
    tenure: object = _MISSING,
    policy: object = _MISSING,
    employees: object = _DEFAULT_EMPTY,
    attrition: object = _DEFAULT_EMPTY,
) -> tuple[HrCopilotEngine, FakeLlmRouter, FakeGateway]:
    router = FakeLlmRouter(llm_text)
    gateway = FakeGateway(
        overview=_overview() if overview is _MISSING else overview,
        tenure=HrTenureCtx(narrative="Tenure concentrated at 1-3 years.")
        if tenure is _MISSING
        else tenure,
        policy=_policy() if policy is _MISSING else policy,
        employees=employees,
        attrition=attrition,
    )
    engine = HrCopilotEngine(
        llm_router=router,  # type: ignore[arg-type]
        gateway_factory=gateway,  # type: ignore[arg-type]
    )
    return engine, router, gateway


class TestGrounding:
    async def test_aggregate_context_grounded_into_prompt(self) -> None:
        engine, router, gateway = _make_engine("Here is the answer.")

        result = await engine.ask("How big is our headcount?")

        assert result.answer == "Here is the answer."
        assert result.model_used == "fake-model"
        system = router.requests[0].system_prompt
        assert "Current headcount: 120" in system
        assert "Engineering (40)" in system
        assert "1-3 (70)" in system
        assert "casual leave 12 days/year" in system
        assert "Tenure narrative: Tenure concentrated at 1-3 years." in system
        # The user message carries only the question (no PII prompt data).
        assert router.requests[0].user_prompt == "How big is our headcount?"
        assert gateway.calls == ["overview", "tenure", "policy", "employees", "attrition"]
        # Default fakes: no employees and core denied the L2 tier.
        assert "Employees (permitted tier)" not in system
        assert "Attrition risk by employee" not in system
        assert result.context_used == {
            "overview": True,
            "tenure": True,
            "leave_policy": True,
        }

    async def test_individual_employees_grounded_when_granted(self) -> None:
        engine, router, _ = _make_engine("ok", employees=[_employee(1), _employee(2)])

        await engine.ask("Who is in engineering?")

        system = router.requests[0].system_prompt
        assert "Employees (permitted tier):" in system
        assert "Asha Kumar1 (E001)" in system
        assert "Asha Kumar2 (E002)" in system
        assert "Engineer" in system

    async def test_attrition_granted_grounded_into_prompt(self) -> None:
        engine, router, _ = _make_engine("ok", attrition=[_risk(1)])

        await engine.ask("Who is at attrition risk?")

        system = router.requests[0].system_prompt
        assert "Attrition risk by employee:" in system
        assert "high (score 0.85" in system
        assert "long tenure" in system

    async def test_attrition_denied_keeps_prompt_aggregate_only(self) -> None:
        # Core returned a 403 (attrition default ``None``): the per-person
        # signals must NOT appear in the prompt.
        engine, router, gateway = _make_engine(
            "ok", attrition=None, employees=[]
        )

        await engine.ask("Who is at attrition risk?")

        system = router.requests[0].system_prompt
        assert "Attrition risk by employee" not in system
        assert "Employees (permitted tier)" not in system
        assert gateway.attrition is None

    async def test_pii_refusal_guardrail_always_in_system_prompt(self) -> None:
        engine, router, _ = _make_engine("Ignore me")

        await engine.ask("What is Kumar's salary?")

        system = router.requests[0].system_prompt
        # The guardrail against inventing/disclosing data not in context, and the
        # compensation rule, are always present even for individual-denied calls.
        assert "Never reveal, guess, or discuss data that is NOT in CONTEXT" in system
        assert "Compensation/pay is never in CONTEXT" in system

    async def test_missing_context_instructs_not_to_invent(self) -> None:
        engine, router, _ = _make_engine(
            "ok", overview=None, tenure=None, policy=None, employees=[], attrition=None
        )

        result = await engine.ask("what is our headcount?")

        system = router.requests[0].system_prompt
        assert "unavailable" in system
        assert "do not guess" in system
        # No context was sourced - nothing to leak to the prompt.
        assert result.context_used is None
