"""Per-agent context budget manager (SKY-90).

Bounded context is what makes the weekly compaction viable: each agent may
assemble a limited number of tokens of recalled + live context, so the
compaction job can freely fold old episodic memory without unbounded recall
growth. This manager:

- carries the per-agent token budget (overridable in tests),
- estimates token cost of a text cheaply (4 chars/token),
- trims an ordered list of context parts to fit the budget, keeping the
  most important parts first and truncating the tail with an explicit
  marker so the LLM knows content was elided.

It is a pure utility - no I/O, no repository import (import-linter
contract) - usable by any delegator or memory recall path.
"""

from __future__ import annotations

from collections.abc import Mapping

# Rough chars-per-token estimate used for budgeting (fine for cutting, not
# for precise billing; actual model tokenizers differ by a constant-ish
# factor for the short context strings assembled here).
_CHARS_PER_TOKEN = 4
_ELISION_MARKER = "\n… (context trimmed to fit budget)"

# Default per-agent token budgets in characters-equivalent tokens. These
# bound how much recalled + live context one agent turn may consume.
_DEFAULT_BUDGETS: dict[str, int] = {
    "supervisor": 6000,
    "crm_assistant": 4000,
    "inventory_monitor": 4000,
    "finance_assistant": 4000,
    "hr_copilot": 4000,
    "sales_coach": 3000,
    "audit_guardian": 3000,
}
_DEFAULT_BUDGET = 3000


class ContextBudgetManager:
    """Trim agent context to per-agent token budgets."""

    def __init__(self, budgets: Mapping[str, int] | None = None) -> None:
        self._budgets = dict(_DEFAULT_BUDGETS if budgets is None else budgets)
        self._default = self._budgets.get("supervisor", _DEFAULT_BUDGET)

    def budget_for(self, agent: str) -> int:
        """The token budget for ``agent`` (falls back to the default)."""
        return self._budgets.get(agent, self._default)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Cheap token estimate for a string (chars / 4)."""
        return max(len(text) // _CHARS_PER_TOKEN, 1)

    def fits(self, *, agent: str, text: str) -> bool:
        """True when ``text`` fits the agent's budget."""
        return self.estimate_tokens(text) <= self.budget_for(agent)

    def trim_to_budget(self, *, agent: str, parts: list[str]) -> str:
        """Join ``parts`` (most important first) truncated to the budget.

        Parts are kept whole while they fit; the first part that would
        overflow is truncated to the remaining budget and an explicit
        elision marker appended. Later parts are dropped entirely - the
        marker signals the LLM that context was trimmed.
        """
        budget = self.budget_for(agent)
        marker_chars = len(_ELISION_MARKER)
        used = 0
        kept: list[str] = []
        for part in parts:
            cost = self.estimate_tokens(part)
            if used + cost <= budget:
                kept.append(part)
                used += cost
                continue
            # Truncate this overflow part to the remaining room, reserving
            # space for the elision marker so the result honestly fits.
            remaining_chars = (budget - used) * _CHARS_PER_TOKEN - marker_chars
            if remaining_chars > _CHARS_PER_TOKEN and part:
                kept.append(part[:remaining_chars] + _ELISION_MARKER)
            used = budget
            break
        return "\n".join(kept)
