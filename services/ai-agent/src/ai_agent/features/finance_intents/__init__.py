"""Whitelisted finance Q&A intents (SKY-82 / FIN-AI-003 A3).

Each intent maps 1:1 to an existing core finance report endpoint so chat
answers reconcile to the dashboard reports (see ``schemas.INTENT_META``).
Exposes ``match_finance_intent`` (``matcher``) and ``run_finance_intent``
(``executor``) to the supervisor's ``FinanceDelegator``.
"""

from ai_agent.features.finance_intents.executor import run_finance_intent
from ai_agent.features.finance_intents.matcher import match_finance_intent
from ai_agent.features.finance_intents.schemas import FinanceIntentResult

__all__ = [
    "FinanceIntentResult",
    "match_finance_intent",
    "run_finance_intent",
]
