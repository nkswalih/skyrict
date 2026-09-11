"""Finance chat reconciliation suite (SKY-82 / FIN-AI-003 A3).

For every canonical finance question, the chat answer must reconcile to the
dashboard report that backs it: same endpoint, same figures, exact citation.
This runs the FULL delegator path (matcher -> history guard -> intent executor
-> HttpFinanceGateway) against a MockTransport serving canned core payloads, so
any drift between "what the user is told" and "what the report says" fails in
CI without needing a live core/database.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from ai_agent.features.finance.gateway import HttpFinanceGateway
from ai_agent.features.finance_intents.schemas import INTENT_META
from ai_agent.features.supervisor.delegates import FinanceDelegator

if TYPE_CHECKING:
    from ai_agent.features.supervisor.schemas import Citation

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()

# Canned core payloads - the "report run" the chat must reconcile to.
# Money serialized as exact Decimal strings, like core does.
_PNL = {
    "from_date": "2026-08-01",
    "to_date": "2026-08-31",
    "revenue": [],
    "expenses": [],
    "total_revenue": "120000.0000",
    "total_expenses": "80000.0000",
    "net_income": "40000.0000",
}

_AR = {
    "as_of": "2026-08-31",
    "total_ar": "9000.0000",
    "buckets": [
        {"bucket": "current", "count": 5, "amount": "4000.0000", "share": "0.4444"},
        {"bucket": ">90", "count": 2, "amount": "5000.0000", "share": "0.5556"},
    ],
}

_TB = {
    "as_of": "2026-08-31",
    "rows": [
        {
            "code": "1000",
            "name": "Cash",
            "account_type": "asset",
            "debit": "42000.0000",
            "credit": "0.0000",
        },
        {
            "code": "2000",
            "name": "Accounts Payable",
            "account_type": "liability",
            "debit": "0.0000",
            "credit": "21000.0000",
        },
        {
            "code": "4000",
            "name": "Revenue",
            "account_type": "revenue",
            "debit": "0.0000",
            "credit": "21000.0000",
        },
    ],
    "total_debit": "42000.0000",
    "total_credit": "42000.0000",
}

_CF = {
    "positions": [
        {
            "month": "2026-09",
            "opening": "10000.0000",
            "inflows": "15000.0000",
            "outflows": "9000.0000",
            "closing": "16000.0000",
        },
    ],
}

# Six invoices across six distinct months satisfy the history guard.
_INVOICES = [
    {
        "id": f"00000000-0000-0000-0000-0000000000{index:02d}",
        "invoice_number": f"INV-{index:04d}",
        "customer_name": "Acme Foods",
        "invoice_date": f"2026-{month:02d}-15",
        "due_date": f"2026-{month:02d}-28",
        "status": "issued",
        "total": "100.0000",
    }
    for index, month in enumerate(range(1, 7), start=1)
]

# (question, intent, expected figures the chat must surface verbatim)
CANONICAL: list[tuple[str, str, tuple[str, ...]]] = [
    ("What is our net income this quarter?", "net_income", ("40000", "120000", "80000")),
    ("Show total revenue for the period", "net_income", ("120000", "80000")),
    ("What is our AR aging?", "ar_aging", ("9000", "current 4000", ">90 5000")),
    (
        "What is our payables balance?",
        "trial_balance",
        ("total credits 42000", "Accounts Payable"),
    ),
    (
        "How much cash are we receiving next month?",
        "cashflow_projection",
        ("closing 16000", "inflow 15000"),
    ),
]


class NoLlmRouter:
    """Fails the test if the LLM is ever reached - these answers are deterministic."""

    async def complete(self, request: Any) -> Any:
        raise AssertionError(
            f"LLM must not be reached for reconcile-able questions: {request.user_prompt}"
        )


def _envelope(data: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    return {"success": True, "data": data}


def _list_envelope(data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "meta": {"total": len(data), "page": 1, "page_size": 100},
    }


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/api/v1/finance/invoices"):
        return httpx.Response(200, json=_list_envelope(_INVOICES))
    if request.url.path.endswith("/reports/profit-and-loss"):
        return httpx.Response(200, json=_envelope(_PNL))
    if request.url.path.endswith("/reports/ar-aging"):
        return httpx.Response(200, json=_envelope(_AR))
    if request.url.path.endswith("/reports/trial-balance"):
        return httpx.Response(200, json=_envelope(_TB))
    if request.url.path.endswith("/automation/cashflow-projection"):
        return httpx.Response(200, json=_envelope(_CF))
    raise AssertionError(f"Unexpected finance path: {request.url}")


def _make_delegator() -> FinanceDelegator:
    gateway = HttpFinanceGateway(
        base_url="https://core.internal",
        bearer_token="user-token-123",
        tenant_slug="acme-corp",
    )
    gateway._create_client = lambda: httpx.AsyncClient(  # type: ignore[method-assign]
        timeout=5, transport=httpx.MockTransport(_handler)
    )

    async def factory() -> HttpFinanceGateway:
        return gateway

    return FinanceDelegator(llm_router=NoLlmRouter(), finance_gateway_factory=factory)


async def _ask(delegator: FinanceDelegator, question: str) -> tuple[str, list[Citation]]:
    citations: list[Citation] = []
    text = "".join(
        [
            delta
            async for delta in delegator.stream(
                query=question,
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                citations=citations,
            )
        ]
    )
    return text, citations


class TestReconciliation:
    @pytest.mark.parametrize(
        ("question", "intent", "expected"),
        [(question, intent, expected) for question, intent, expected in CANONICAL],
    )
    async def test_chat_answer_reconciles_to_report(
        self, question: str, intent: str, expected: tuple[str, ...]
    ) -> None:
        text, citations = await _ask(_make_delegator(), question)

        for figure in expected:
            assert figure in text, f"{question!r}: expected {figure!r} in {text!r}"

        assert len(citations) == 1
        assert citations[0].module == "finance"
        assert citations[0].source_ref == INTENT_META[intent].endpoint
        assert citations[0].title == INTENT_META[intent].title
