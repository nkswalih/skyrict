"""Supervisor feature - intent classification + delegation to module agents.

The supervisor is the routing layer behind the Agents shell chat (SKY-60):
classify a question into module agents, then stream each agent's answer with
attribution and grounding citations. This package is pure orchestration -
persistence (registry rows) is injected by the graph layer
(:mod:`ai_agent.graphs.supervisor`), keeping the feature free of
``ai_agent.db``/``ai_agent.models`` imports (import-linter).
"""

from ai_agent.features.supervisor.schemas import (
    AGENT_AUDIT_GUARDIAN,
    AGENT_CRM,
    AGENT_FINANCE,
    AGENT_HR,
    AGENT_INVENTORY,
    AGENT_SALES_COACH,
    AgentKey,
    AgentStartEvent,
    Citation,
    CitationsEvent,
    ClassificationEvent,
    DoneEvent,
    RouteDecision,
    SupervisorEvent,
    TokenEvent,
)
from ai_agent.features.supervisor.service import SupervisorService

__all__ = [
    "AGENT_AUDIT_GUARDIAN",
    "AGENT_CRM",
    "AGENT_FINANCE",
    "AGENT_HR",
    "AGENT_INVENTORY",
    "AGENT_SALES_COACH",
    "AgentKey",
    "AgentStartEvent",
    "Citation",
    "CitationsEvent",
    "ClassificationEvent",
    "DoneEvent",
    "RouteDecision",
    "SupervisorEvent",
    "SupervisorService",
    "TokenEvent",
]
