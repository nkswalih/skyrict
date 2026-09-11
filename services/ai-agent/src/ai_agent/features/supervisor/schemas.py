"""Supervisor public types (SKY-60) - routing decisions, events, citations.

The Agents shell streams an :class:`SupervisorEvent` sequence per turn:

  ``ClassificationEvent`` → (per module agent) ``AgentStartEvent`` →
  ``TokenEvent``* → ``CitationsEvent`` → ``DoneEvent``

Cross-module questions fan out to several agents sequentially, each with its
own attribution. Abstentions (low confidence, unprovisioned module) are
ordinary events, never errors - the shell always renders text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AGENT_INVENTORY = "inventory_monitor"
AGENT_HR = "hr_copilot"
AGENT_CRM = "crm_assistant"
AGENT_FINANCE = "finance_assistant"
AGENT_SALES_COACH = "sales_coach"
AGENT_AUDIT_GUARDIAN = "audit_guardian"

AgentKey = Literal[
    "inventory_monitor",
    "hr_copilot",
    "crm_assistant",
    "finance_assistant",
    "sales_coach",
    "audit_guardian",
]

AGENT_DISPLAY_NAMES: dict[str, str] = {
    AGENT_INVENTORY: "Inventory Monitor",
    AGENT_HR: "HR Copilot",
    AGENT_CRM: "CRM Assistant",
    AGENT_FINANCE: "Finance Assistant",
    AGENT_SALES_COACH: "Sales Coach",
    AGENT_AUDIT_GUARDIAN: "Audit Guardian",
    "supervisor": "Supervisor",
}


@dataclass(frozen=True, slots=True)
class Citation:
    """One knowledge-base source the answer was grounded on (RAG)."""

    source_ref: str
    module: str
    title: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class RouteDecision:
    """The classifier's routing outcome for one question."""

    agents: tuple[str, ...]
    confidence: float
    abstain: bool
    reason: str


@dataclass(frozen=True, slots=True)
class ClassificationEvent:
    """Emitted first: how the turn was routed (or why it abstained)."""

    agents: tuple[str, ...]
    confidence: float
    abstain: bool
    reason: str


@dataclass(frozen=True, slots=True)
class AgentStartEvent:
    """One module agent begins its segment."""

    agent: str
    display_name: str


@dataclass(frozen=True, slots=True)
class TokenEvent:
    """One token delta for the current segment's agent."""

    agent: str
    delta: str


@dataclass(frozen=True, slots=True)
class CitationsEvent:
    """Segment's grounding citations (empty when none)."""

    agent: str
    citations: tuple[Citation, ...]


@dataclass(frozen=True, slots=True)
class DoneEvent:
    """Turn complete - the agents that contributed, in order."""

    agents: tuple[str, ...]


SupervisorEvent = ClassificationEvent | AgentStartEvent | TokenEvent | CitationsEvent | DoneEvent
