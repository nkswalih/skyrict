"""HR Copilot engine - assemble context and draft the answer.

Flow (spec §9, feature 5):
  1. CONTEXT - fetch the tenant's L1 aggregate overview/tenure, leave policy,
     and (permission-gated) individual context through the gateway. Failures
     degrade to ``None``/``[]`` so the engine always has something to answer
     from.
  2. GROUND - build a guardrailed system prompt embedding that context.
     Individual employee rows and per-employee AI signals are placed in the
     prompt ONLY when core granted them to the caller's role
     (     ``erp.hr.read`` for standard rows; ``erp.hr.ai.individual`` + the AI-read
     tier for L2 signals). If core denied them (403), the gateway returns
     ``None``/``[]`` and the prompt stays aggregate-only - there is no per-person
     data to leak.
  3. DRAFT - call the LLM once through ``LlmRouter`` (which runs the PII
     redaction gate over the user message before any provider sees it).

Data residency: aggregate counts, band labels, policy figures, and any
permitted per-person records may travel to cloud providers
(``require_local_only=False``) - identical to the inventory NL parser. The
redaction gate is the backstop for any stray PII. Compensation is never in
context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from ai_agent.core.providers import LlmRequest

if TYPE_CHECKING:
    from ai_agent.core.llm_router import LlmRouter
    from ai_agent.features.hr_copilot.gateway import (
        AttritionRiskRef,
        HrEmployeeRef,
        HrGatewayPort,
        HrLeavePolicyCtx,
        HrOverviewCtx,
        HrTenureCtx,
    )

logger = structlog.get_logger("ai_agent.hr_copilot_engine")

_COPILOT_SYSTEM_PROMPT = (
    "You are the SkyRICT HR Copilot, a helpful assistant for HR managers and "
    "department heads. Answer the user's question about their organisation "
    "using ONLY the CONTEXT provided below.\n"
    "\n"
    "Data tiers in CONTEXT:\n"
    "- AGGREGATE headcount, tenure-band, and leave-policy information (always "
    "present).\n"
    "- INDIVIDUAL employee rows and per-employee attrition signals - these are "
    "present ONLY when the caller's role is permitted to see them (owner/exec "
    "holding ``erp.hr.ai.individual`` for AI signals; ``erp.hr.read`` for "
    "standard employee rows). If they are absent from CONTEXT, the caller is "
    "not permitted and you must not surface them.\n"
    "\n"
    "Hard rules:\n"
    "1. Never reveal, guess, or discuss data that is NOT in CONTEXT. If a "
    "specific person or figure is not in CONTEXT (or CONTEXT contains no "
    "per-person records), state that it is not available to you rather than "
    "inventing it.\n"
    "2. Compensation/pay is never in CONTEXT and never relevant - do not "
    "discuss or guess salaries or pay.\n"
    "3. When CONTEXT includes individual records, treat them as the caller's "
    "permitted view: answer about those people/facts only, exactly as given.\n"
    "4. Keep answers concise and factual.\n"
)


@dataclass(frozen=True, slots=True)
class HrCopilotResult:
    """Everything the Copilot chat returns plus what the audit log needs."""

    answer: str
    model_used: str | None
    latency_ms: int
    context_used: dict[str, object] | None


class HrCopilotEngine:
    """Ground one Copilot message in aggregate HR context and draft an answer."""

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        gateway_factory: HrGatewayPort | None,
    ) -> None:
        self._llm_router = llm_router
        # A callable gateway (bound per request). Fake-friendly: may be None
        # for tests that exercise only the LLM path.
        self._gateway = gateway_factory

    async def ask(self, message: str) -> HrCopilotResult:
        started = time.perf_counter()

        overview = await self._gateway.get_overview() if self._gateway is not None else None
        tenure = await self._gateway.get_tenure() if self._gateway is not None else None
        policy = await self._gateway.get_leave_policy() if self._gateway is not None else None
        employees = await self._gateway.list_employees() if self._gateway is not None else []
        attrition = await self._gateway.get_attrition() if self._gateway is not None else None

        context = _build_context(
            overview=overview,
            tenure=tenure,
            policy=policy,
            employees=employees,
            attrition=attrition,
        )

        completion = await self._llm_router.complete(
            LlmRequest(
                system_prompt=_COPILOT_SYSTEM_PROMPT + "\n\nCONTEXT:\n" + context,
                user_prompt=message.strip(),
                max_tokens=512,
                temperature=0.2,
            )
        )

        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "hr_copilot.completed",
            latency_ms=latency_ms,
            model_used=completion.model_used,
        )
        return HrCopilotResult(
            answer=completion.text,
            model_used=completion.model_used,
            latency_ms=latency_ms,
            context_used=_context_summary(
                overview=overview,
                tenure=tenure,
                policy=policy,
                employees=employees,
                attrition=attrition,
            ),
        )


def _build_context(
    *,
    overview: HrOverviewCtx | None,
    tenure: HrTenureCtx | None,
    policy: HrLeavePolicyCtx | None,
    employees: list[HrEmployeeRef],
    attrition: list[AttritionRiskRef] | None,
) -> str:
    """Render the available context into a readable prompt block.

    Aggregate + policy context is always included. Individual employee rows and
    per-employee AI signals are included ONLY when core granted them (employee
    rows to ``erp.hr.read`` holders; attrition signals to the L2
    ``erp.hr.ai.individual`` tier). Each section is bounded so the prompt cannot
    balloon with a large tenant.
    """
    lines: list[str] = []
    if overview is not None:
        headcount = overview.total_headcount or 0
        lines.append(f"- Current headcount: {headcount}")
        if overview.departments:
            depts = ", ".join(f"{name} ({count})" for name, count in overview.departments)
            lines.append(f"- Headcount by department: {depts}.")
        if overview.tenure_bands:
            bands = ", ".join(f"{band} ({count})" for band, count in overview.tenure_bands)
            lines.append(f"- Tenure bands: {bands}.")
        if overview.narrative:
            lines.append(f"- Overview narrative: {overview.narrative}")
    if tenure is not None and tenure.narrative:
        lines.append(f"- Tenure narrative: {tenure.narrative}")
    if policy is not None:
        policy_parts: list[str] = []
        if policy.casual_days_per_year is not None:
            policy_parts.append(f"casual leave {policy.casual_days_per_year} days/year")
        if policy.sick_days_per_year is not None:
            policy_parts.append(f"sick leave {policy.sick_days_per_year} days/year")
        if policy.effective_from:
            policy_parts.append(f"effective from {policy.effective_from}")
        if policy_parts:
            lines.append("- Leave policy: " + "; ".join(policy_parts) + ".")

    if attrition is not None:
        if attrition:
            lines.append("- Attrition risk by employee:")
            for risk in attrition[:_CONTEXT_EMPLOYEE_LIMIT]:
                factors = "; ".join(risk.factors) if risk.factors else "no factors listed"
                lines.append(
                    f"  - {risk.name or risk.employee_number or risk.employee_id}: "
                    f"{risk.risk_band} (score {risk.score:.2f}, confidence {risk.confidence:.2f}), "
                    f"dept={risk.department_name or 'n/a'}; {factors}"
                )
            if len(attrition) > _CONTEXT_EMPLOYEE_LIMIT:
                lines.append(
                    f"  - ... and {len(attrition) - _CONTEXT_EMPLOYEE_LIMIT} more employee(s)."
                )
        else:
            lines.append("- No per-employee attrition risk rows are scored yet.")

    if employees:
        lines.append("- Employees (permitted tier):")
        for employee in employees[:_CONTEXT_EMPLOYEE_LIMIT]:
            lines.append(
                f"  - {employee.first_name} {employee.last_name} "
                f"({employee.employee_number}): {employee.job_title}, "
                f"status={employee.employment_status}"
            )
        if len(employees) > _CONTEXT_EMPLOYEE_LIMIT:
            lines.append(
                f"  - ... and {len(employees) - _CONTEXT_EMPLOYEE_LIMIT} more employee(s)."
            )

    if not lines:
        lines.append(
            "No aggregate HR context is currently available for this tenant. "
            "Answer only that context is unavailable; do not guess figures."
        )
    return "\n".join(lines)


def _context_summary(
    *,
    overview: HrOverviewCtx | None,
    tenure: HrTenureCtx | None,
    policy: HrLeavePolicyCtx | None,
    employees: list[HrEmployeeRef],
    attrition: list[AttritionRiskRef] | None,
) -> dict[str, object] | None:
    """Which context parts were available - for the audit log / response."""
    summary: dict[str, object] = {}
    if overview is not None:
        summary["overview"] = True
    if tenure is not None:
        summary["tenure"] = True
    if policy is not None:
        summary["leave_policy"] = True
    if employees:
        summary["employees"] = len(employees)
    # ``None`` means grant denied; only report when the L2 tier actually granted.
    if attrition is not None:
        summary["attrition_individual"] = True
    return summary or None


# Bound how many per-person records are placed in the prompt for a large tenant.
_CONTEXT_EMPLOYEE_LIMIT = 50
