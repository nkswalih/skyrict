"""Sales Coach — the SKY-90 coaching suggestion agent (module contract).

Module contract (see runtime.py): the module exposes ``build_graph(deps)``
returning an UNCOMPILED ``StateGraph``; the runtime compiles it with the
tenant-scoped checkpointer and drives invoke/resume. The registry seed
(0020) wires ``sales_coach -> ai_agent.features.sales_coach.graph`` with
allowlist ``["analyze_rep_activity", "create_coaching_suggestion"]``.

Flow::

    analyze_rep_activity (read gate: requires erp.crm.read)
      -> generate_coaching (LLM: produces coaching suggestions from activity data)
      -> create_suggestion (interrupt: requires erp.crm.coaching.approve for manager approval)

The read gate is real: ``analyze_rep_activity`` refuses to run without
``erp.crm.read`` on the caller's ``ToolContext``. The write gate is the
runtime's: an approved interrupt requires ``erp.crm.coaching.approve`` at
ledger-open AND resume, then the approved branch persists an
``ai_coaching_suggestions`` row through the INJECTED suggestion repository
(runtime-composed, RLS session) and audits ``ai.coaching.suggestion.created``;
denied is a clean no-op.

Security notes:
  - The CRM gateway forwards the caller's JWT + tenant slug, so core
    enforces ``erp.crm.read``, tenant isolation, and owner/team row-scoping.
  - Coaching suggestions are ONLY visible to managers via the role-gated
    API layer — the agent does not enforce visibility; the API does.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, TypedDict

import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ai_agent.core.audit_events import AI_COACHING_SUGGESTION_CREATED
from ai_agent.graphs.security import PERM_CRM_COACHING_APPROVE, PERM_CRM_READ
from skyrict_common.exceptions import PermissionDeniedError

if TYPE_CHECKING:
    from ai_agent.features.crm.gateway import CrmGatewayPort
    from ai_agent.features.sales_coach.ports import CoachingSuggestionPort
    from ai_agent.graphs.runtime import AgentDeps

logger = structlog.get_logger("ai_agent.sales_coach.graph")

__all__ = ["build_graph"]


class SalesCoachState(TypedDict, total=False):
    """Run-local state for the Sales Coach agent."""

    rep_user_id: str
    activity_data: dict[str, Any]
    coaching_suggestions: list[dict[str, Any]]
    suggestion_id: str
    applied: bool
    outcome: str


@dataclass
class SalesCoachDeps:
    """Extended deps for the Sales Coach — CRM gateway + suggestion port.

    The graph builder receives this alongside the standard ``AgentDeps``.
    """

    crm_gateway: CrmGatewayPort
    suggestion_repo: CoachingSuggestionPort
    llm_router: Any  # LlmRouter — Any to avoid circular import at module level


def build_graph(
    deps: AgentDeps, extra: SalesCoachDeps | None = None
) -> StateGraph[SalesCoachState]:
    """Build the Sales Coach's uncompiled state graph (runtime compiles it).

    Nodes are bound to ``deps`` here via ``functools.partial`` — LangGraph
    does not inject extra kwargs into plain-function nodes (verified against
    the installed 0.6.x runtime), so the graph hands each node exactly the
    state it declares.
    """
    builder = StateGraph(SalesCoachState)
    builder.add_node(
        "analyze_rep_activity",
        partial(_analyze_activity_node, deps=deps, extra=extra),
    )
    builder.add_node(
        "generate_coaching",
        partial(_generate_coaching_node, extra=extra),
    )
    builder.add_node(
        "create_suggestion",
        partial(_create_suggestion_node, deps=deps, extra=extra),
    )
    builder.add_edge(START, "analyze_rep_activity")
    builder.add_edge("analyze_rep_activity", "generate_coaching")
    builder.add_edge("generate_coaching", "create_suggestion")
    builder.add_edge("create_suggestion", END)
    return builder


def _analyze_activity_node(
    state: SalesCoachState,
    deps: AgentDeps,
    extra: SalesCoachDeps | None,
) -> dict[str, object]:
    """Real read gate — refuses to run without erp.crm.read."""
    if not deps.tool_context.permits(PERM_CRM_READ):
        raise PermissionDeniedError(f"permission required to analyze rep activity: {PERM_CRM_READ}")
    # The actual CRM data fetch is async and happens in the LLM node
    # via the injected gateway. This node just validates the permission gate.
    return {}


async def _generate_coaching_node(
    state: SalesCoachState,
    extra: SalesCoachDeps | None,
) -> dict[str, object]:
    """Use the LLM to generate coaching suggestions from CRM activity data.

    If no LLM provider is available, returns a deterministic summary.
    """
    if extra is None or extra.llm_router is None:
        return {"coaching_suggestions": []}

    # Fetch live CRM data via the gateway.
    rep_user_id = state.get("rep_user_id", "")
    if not rep_user_id:
        return {"coaching_suggestions": []}

    try:
        from ai_agent.features.sales_coach.tools import analyze_rep_activity

        activity_data = await analyze_rep_activity(
            crm_gateway=extra.crm_gateway,
            rep_user_id=rep_user_id,
        )
    except Exception:
        logger.warning("sales_coach.activity_fetch_failed", exc_info=True)
        return {"coaching_suggestions": []}

    if not activity_data.get("opportunities") and not activity_data.get("activities"):
        return {"coaching_suggestions": []}

    # LLM call to generate coaching suggestions.
    system_prompt = _COACHING_SYSTEM_PROMPT
    user_prompt = (
        f"Analyze the following sales rep activity and generate actionable "
        f"coaching suggestions.\n\n"
        f"Rep activity data:\n{json.dumps(activity_data, default=str, indent=2)[:4000]}\n\n"
        f"Return a JSON array of suggestion objects with keys: "
        f"'suggestion_type' (follow_up|deal_strategy|pipeline_review|general), "
        f"'title' (short string), 'body' (detailed coaching advice), "
        f"'evidence' (array of objects with 'type', 'id', 'description'). "
        f"Generate 1-3 suggestions. Only include genuinely actionable suggestions."
    )

    if not extra.llm_router.has_providers:
        return {"coaching_suggestions": _deterministic_suggestions(activity_data)}

    try:
        from ai_agent.core.providers.base import LlmRequest

        completion = await extra.llm_router.complete(
            LlmRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=1024,
                temperature=0.2,
            )
        )
        text = (completion.text or "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        suggestions = json.loads(text)
        if isinstance(suggestions, list):
            valid = [
                s
                for s in suggestions
                if isinstance(s, dict)
                and "title" in s
                and "body" in s
                and s.get("suggestion_type")
                in ("follow_up", "deal_strategy", "pipeline_review", "general")
            ]
            return {"coaching_suggestions": valid[:3]}  # cap at 3
    except Exception:
        logger.warning("sales_coach.llm_generation_failed", exc_info=True)

    return {"coaching_suggestions": _deterministic_suggestions(activity_data)}


async def _create_suggestion_node(
    state: SalesCoachState,
    deps: AgentDeps,
    extra: SalesCoachDeps | None,
) -> dict[str, object]:
    """HITL gate: pause for manager review, then persist on approval.

    ``interrupt()`` raises ``GraphInterrupt`` on the first pass; the runtime
    opens the ledger row from its returned value. On resume it returns the
    decision dict, the node runs ONCE, and the checkpoint advances.
    """
    suggestions = state.get("coaching_suggestions", [])
    if not suggestions or extra is None:
        return {"applied": False, "outcome": "no_suggestions"}

    # Use the first suggestion for the interrupt payload.
    first = suggestions[0]
    decision = interrupt(
        {
            "tool": "create_coaching_suggestion",
            "required_permission": PERM_CRM_COACHING_APPROVE,
            "payload": {
                "rep_user_id": state.get("rep_user_id", ""),
                "suggestion_type": first.get("suggestion_type", "general"),
                "title": first.get("title", ""),
                "body": first.get("body", ""),
                "count": len(suggestions),
            },
        }
    )
    if not isinstance(decision, dict) or decision.get("decision") != "approved":
        return {"applied": False, "outcome": "denied"}

    # Persist all suggestions on approval.
    try:
        rep_id = uuid.UUID(state.get("rep_user_id", ""))
        suggestion_ids: list[str] = []
        for s in suggestions:
            sid = await extra.suggestion_repo.create_suggestion(
                tenant_id=deps.tenant_id,
                rep_user_id=rep_id,
                opportunity_id=None,
                lead_id=None,
                suggestion_type=s.get("suggestion_type", "general"),
                title=s.get("title", ""),
                body=s.get("body", ""),
                evidence=s.get("evidence", []),
            )
            suggestion_ids.append(str(sid))

        await deps.audit.log(
            action=AI_COACHING_SUGGESTION_CREATED,
            tenant_id=deps.tenant_id,
            user_id=deps.user_id,
            input_payload={
                "suggestion_ids": suggestion_ids,
                "rep_user_id": state.get("rep_user_id", ""),
                "count": len(suggestion_ids),
            },
        )
    except Exception:
        logger.exception("sales_coach.persist_failed")
        return {"applied": False, "outcome": "write_failed"}

    return {"applied": True, "outcome": "applied", "suggestion_id": suggestion_ids[0]}


def _deterministic_suggestions(activity_data: dict[str, Any]) -> list[dict[str, object]]:
    """Provider-free coaching suggestions based on activity patterns (dev/demo)."""
    suggestions: list[dict[str, object]] = []
    opps = activity_data.get("opportunities", [])

    # Suggest follow-up on stalled deals.
    stalled = [
        o
        for o in opps
        if o.get("stage") in ("proposal", "negotiation")
        and o.get("expected_close_date") is not None
    ]
    if stalled:
        suggestions.append(
            {
                "suggestion_type": "follow_up",
                "title": f"Follow up on {len(stalled)} stalled deal(s)",
                "body": (
                    f"You have {len(stalled)} deal(s) in proposal/negotiation stage. "
                    "Consider reaching out to re-engage and address any remaining objections."
                ),
                "evidence": [
                    {"type": "opportunity", "id": o.get("id"), "description": o.get("display_name")}
                    for o in stalled[:3]
                ],
            }
        )

    # Suggest pipeline review if many opportunities.
    if len(opps) > 5:
        suggestions.append(
            {
                "suggestion_type": "pipeline_review",
                "title": "Schedule a pipeline review",
                "body": (
                    f"You currently have {len(opps)} open opportunities. "
                    "Consider a focused pipeline review to prioritize high-probability deals."
                ),
                "evidence": [
                    {"type": "pipeline", "id": "all", "description": f"{len(opps)} opportunities"}
                ],
            }
        )

    return suggestions


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_COACHING_SYSTEM_PROMPT = """\
You are the Sales Coach for Skyrict. You analyze sales rep activity data \
(opportunities, activities, notes) and generate actionable coaching suggestions.

Rules:
- Generate 1-3 coaching suggestions based on the activity patterns.
- Each suggestion must reference specific evidence from the data.
- Suggestions must be actionable (not generic advice).
- Categories: follow_up (stale opportunities), deal_strategy (probability \
improvement), pipeline_review (portfolio health), general (misc coaching).
- Keep suggestions concise but specific.

Return ONLY a JSON array of suggestion objects. Each object must have:
- suggestion_type: one of follow_up, deal_strategy, pipeline_review, general
- title: short descriptive title
- body: detailed coaching advice (2-3 sentences)
- evidence: array of objects with type, id, and description fields
""".strip()
