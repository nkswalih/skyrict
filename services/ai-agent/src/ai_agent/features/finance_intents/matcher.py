"""Finance intent matcher (SKY-82 / FIN-AI-003 A3).

Maps a free-form question to a whitelisted :data:`FinanceIntentId` using a
closed keyword set, mirroring the ``nl_query``/CRM matcher patterns. Only
questions inside the whitelist are answered deterministically; anything else
falls through to the delegator's existing LLM path. Priority matters - the
first intent whose keywords appear in the question wins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_agent.features.finance_intents.schemas import FinanceIntentId

_INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("trial_balance", ("trial balance", "payable", "payables")),
    (
        "ar_aging",
        ("ar aging", "receivable", "receivables", "owed", "owing", "aging", "outstanding balance"),
    ),
    (
        "net_income",
        (
            "net income",
            "profit and loss",
            "profit & loss",
            "p&l",
            "profitability",
            "earnings",
            "revenue",
            "expense",
        ),
    ),
    (
        "cashflow_projection",
        ("cash", "cash flow", "cashflow", "inflow", "outflow", "liquidity", "projected cash"),
    ),
    ("invoice_summary", ("invoice", "invoices", "bill", "bills", "outstanding")),
)


def match_finance_intent(query: str) -> FinanceIntentId | None:
    """Return the first whitelisted intent matching ``query``, else ``None``."""
    lowered = query.casefold()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent  # type: ignore[return-value]
    return None
