"""HR Copilot agent (spec §9, feature 5).

Registered in ``agent_registry`` as
``{name: "hr_copilot", module: "ai_agent.features.hr_copilot.engine",
enabled: true}``.

Data tiers: aggregate (L1) HR reads and the tenant's leave policy are always
available. Standard employee rows (``erp.hr.read``) and L2 per-employee AI
signals (``erp.hr.ai.individual``) are surfaced only to the extent core grants
them to the caller's role - the gateway forwards the caller's scoped identity
and core denies non-holders. Compensation is never part of the context. All
exchanges pass through the LLM redaction gate inside ``LlmRouter``.
"""

from __future__ import annotations

from ai_agent.features.hr_copilot.engine import HrCopilotEngine, HrCopilotResult
from ai_agent.features.hr_copilot.gateway import (
    AttritionRiskRef,
    HrEmployeeRef,
    HrGatewayPort,
    HrLeavePolicyCtx,
    HrOverviewCtx,
    HrTenureCtx,
    HttpHrGateway,
)
from ai_agent.features.hr_copilot.service import HrCopilotService

__all__ = [
    "AttritionRiskRef",
    "HrCopilotEngine",
    "HrCopilotResult",
    "HrCopilotService",
    "HrEmployeeRef",
    "HrGatewayPort",
    "HrLeavePolicyCtx",
    "HrOverviewCtx",
    "HrTenureCtx",
    "HttpHrGateway",
]
