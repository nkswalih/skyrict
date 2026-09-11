"""Reconciliation eval registry for finance chat intents (SKY-82 / FIN-AI-003 A3).

Plain data - no network, no pytest assertions. CI can import ``cases`` and
``count()`` to drive the deployed scorer harness. Each case is a dict with:

    id          unique case identifier (A3-xxx)
    question    the canonical user question
    intent      the whitelisted intent that must match (see finance_intents)
    endpoint    the core report the answer must reconcile to
    expected    figures the answer must contain verbatim

These are the same cases the unit reconciliation suite runs; this registry lets
a deployed scorer re-check them against a live core after deployment.
"""

from __future__ import annotations

cases: list[dict[str, object]] = [
    {
        "id": "A3-001",
        "question": "What is our net income this quarter?",
        "intent": "net_income",
        "endpoint": "/api/v1/finance/reports/profit-and-loss",
        "expected": ["40000", "120000", "80000"],
    },
    {
        "id": "A3-002",
        "question": "Show total revenue for the period",
        "intent": "net_income",
        "endpoint": "/api/v1/finance/reports/profit-and-loss",
        "expected": ["120000", "80000"],
    },
    {
        "id": "A3-003",
        "question": "What is our AR aging?",
        "intent": "ar_aging",
        "endpoint": "/api/v1/finance/reports/ar-aging",
        "expected": ["9000", "current 4000", ">90 5000"],
    },
    {
        "id": "A3-004",
        "question": "What is our payables balance?",
        "intent": "trial_balance",
        "endpoint": "/api/v1/finance/reports/trial-balance",
        "expected": ["total credits 42000", "Accounts Payable"],
    },
    {
        "id": "A3-005",
        "question": "How much cash are we receiving next month?",
        "intent": "cashflow_projection",
        "endpoint": "/api/v1/finance/automation/cashflow-projection",
        "expected": ["closing 16000", "inflow 15000"],
    },
]


def count() -> int:
    """Return the number of eval cases in this registry."""
    return len(cases)
