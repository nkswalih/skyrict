"""Finance intent catalogue (SKY-82 / FIN-AI-003 A3) - whitelisted Q&A intents.

A closed intent set is how the chat answers reconcile *exactly* to the finance
dashboard reports: every intent maps 1:1 to one existing core report endpoint,
and the intent executor calls exactly the gateway method that backs that
report. The reconciliation suite (Phase 2) then proves ``chat answer == report
run`` for the same question.

Guardrails live here as metadata:
  * ``INTENT_META`` records each intent's canonical endpoint + title (the
    citation anchor and parity anchor).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FinanceIntentId = Literal[
    "net_income",
    "ar_aging",
    "invoice_summary",
    "trial_balance",
    "cashflow_projection",
]

FINANCE_INTENT_IDS: frozenset[str] = frozenset(
    {"net_income", "ar_aging", "invoice_summary", "trial_balance", "cashflow_projection"}
)


@dataclass(frozen=True, slots=True)
class IntentMeta:
    """One intent's report anchor: its answer must reconcile to this endpoint.

    ``requires_history`` marks intents that surface *period/balance money
    figures*; they abstain when the tenant is under 3 months of invoicing
    history (A3 guardrail). Snapshot catalog reads (e.g. invoice counts) set it
    ``False`` so they answer regardless.
    """

    endpoint: str
    title: str
    requires_history: bool


INTENT_META: dict[str, IntentMeta] = {
    "net_income": IntentMeta(
        endpoint="/api/v1/finance/reports/profit-and-loss",
        title="Profit & Loss",
        requires_history=True,
    ),
    "ar_aging": IntentMeta(
        endpoint="/api/v1/finance/reports/ar-aging",
        title="Accounts Receivable Aging",
        requires_history=True,
    ),
    "invoice_summary": IntentMeta(
        endpoint="/api/v1/finance/invoices",
        title="Invoices",
        requires_history=False,
    ),
    "trial_balance": IntentMeta(
        endpoint="/api/v1/finance/reports/trial-balance",
        title="Trial Balance",
        requires_history=True,
    ),
    "cashflow_projection": IntentMeta(
        endpoint="/api/v1/finance/automation/cashflow-projection",
        title="Cash Flow Projection",
        requires_history=True,
    ),
}


@dataclass(frozen=True, slots=True)
class FinanceIntentResult:
    """A grounded, citation-backed answer for one matched intent.

    ``endpoint`` is the report anchor the answer reconciles to; ``rows`` is the
    machine-checkable set of figures actually surfaced to the user (what the
    reconciliation suite asserts against the same report run on the fixtures);
    ``filters`` records the period/as-of anchors used for the read.
    """

    intent: str
    answer: str
    endpoint: str
    title: str
    rows: tuple[dict[str, object], ...]
    filters: dict[str, str]
