"""Sales Coach tools — read-only CRM access for activity analysis (SKY-90).

The Sales Coach agent's single tool reads CRM data (opportunities, activities,
leads) for a specific sales rep. Permission enforcement happens in the graph's
``_analyze_activity_node`` gate (``erp.crm.read``), not in this module — the
runtime's ``ToolContext`` authorizes before any handler runs.

The CRM gateway forwards the caller's JWT + tenant slug, so core enforces
``erp.crm.read``, tenant isolation, and owner/team row-scoping on every read.
The agent therefore receives exactly the records the acting user may view in
the CRM UI — a proxy, never a bypass.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from ai_agent.features.crm.gateway import CrmGatewayPort

logger = structlog.get_logger("ai_agent.sales_coach.tools")

# Cap on activities fetched per rep to avoid overwhelming the LLM context.
_MAX_ACTIVITIES = 50
_MAX_OPPORTUNITIES = 20


async def analyze_rep_activity(
    *,
    crm_gateway: CrmGatewayPort,
    rep_user_id: str,
) -> dict[str, object]:
    """Read-only CRM query: fetch opportunities and activities for a rep.

    Returns a JSON-safe dict the LLM node can consume as context. The gateway
    forwards the caller's JWT + tenant slug, so core enforces ``erp.crm.read``
    and owner/team row-scoping on every read.
    """
    rep_id = uuid.UUID(rep_user_id)

    # Gather opportunities owned by this rep.
    try:
        all_opps = await crm_gateway.list_opportunities()
    except Exception:
        logger.warning("sales_coach.opps_fetch_failed", rep_user_id=rep_user_id)
        all_opps = []
    rep_opps = [opp for opp in all_opps if opp.owner_id == rep_id][:_MAX_OPPORTUNITIES]

    # Gather activities for each opportunity (bounded).
    activities: list[dict[str, object]] = []
    for opp in rep_opps:
        try:
            entity_activities = await crm_gateway.list_activities_for_entity(
                entity_type="opportunity", entity_id=opp.id
            )
            for act in entity_activities[:10]:  # cap per opportunity
                activities.append(
                    {
                        "id": str(act.id),
                        "kind": act.kind,
                        "completed_at": (
                            act.completed_at.isoformat() if act.completed_at else None
                        ),
                        "created_at": act.created_at.isoformat(),
                        "opportunity_id": str(opp.id),
                    }
                )
        except Exception:  # nosec B112 - best-effort per opportunity
            continue

    # Also gather activities for leads owned by this rep.
    try:
        all_leads = await crm_gateway.list_leads()
    except Exception:
        all_leads = []
    rep_leads = [lead for lead in all_leads if lead.owner_id == rep_id][:_MAX_OPPORTUNITIES]
    for lead in rep_leads:
        try:
            entity_activities = await crm_gateway.list_activities_for_entity(
                entity_type="lead", entity_id=lead.id
            )
            for act in entity_activities[:5]:
                activities.append(
                    {
                        "id": str(act.id),
                        "kind": act.kind,
                        "completed_at": (
                            act.completed_at.isoformat() if act.completed_at else None
                        ),
                        "created_at": act.created_at.isoformat(),
                        "lead_id": str(lead.id),
                    }
                )
        except Exception:  # nosec B112 - best-effort per lead
            continue

    # Sort activities by recency (newest first).
    activities.sort(key=lambda a: str(a.get("created_at", "")), reverse=True)

    return {
        "rep_user_id": rep_user_id,
        "opportunities": [
            {
                "id": str(opp.id),
                "stage": opp.stage,
                "probability": opp.probability,
                "amount": str(opp.amount) if opp.amount is not None else None,
                "currency": opp.currency,
                "display_name": opp.display_name,
                "expected_close_date": (
                    opp.expected_close_date.isoformat() if opp.expected_close_date else None
                ),
                "last_stage_change_at": opp.last_stage_change_at.isoformat(),
                "created_at": opp.created_at.isoformat(),
            }
            for opp in rep_opps
        ],
        "leads": [
            {
                "id": str(lead.id),
                "status": lead.status,
                "source": lead.source,
                "display_name": lead.display_name,
                "created_at": lead.created_at.isoformat(),
            }
            for lead in rep_leads
        ],
        "activities": activities[:_MAX_ACTIVITIES],
        "activity_count": len(activities),
    }
